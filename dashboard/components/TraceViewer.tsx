"use client";
import React, { useState, useEffect, useCallback } from "react";
import { api } from "./ApiClient";

// ═══════════════════════════════════════════════════════════
// DESIGN TOKENS — must match GovernorDashboard.jsx
// ═══════════════════════════════════════════════════════════
const C = {
  bg0:"#080e1a", bg1:"#0e1e30", bg2:"#162840", bg3:"#1d3452",
  line:"#1a2e44", line2:"#243d58",
  p1:"#dde8f5", p2:"#7a9dbd", p3:"#3d5e7a", muted:"#3d5e7a",
  text:"#dde8f5", subdued:"#5a7a96",
  green:"#22c55e", greenDim:"rgba(34,197,94,0.12)",
  amber:"#f59e0b", amberDim:"rgba(245,158,11,0.12)",
  red:"#ef4444",   redDim:"rgba(239,68,68,0.12)",
  accent:"#e8412a", accentDim:"rgba(232,65,42,0.12)",
  cyan:"#38bdf8",  cyanDim:"rgba(56,189,248,0.10)",
  violet:"#a78bfa", violetDim:"rgba(167,139,250,0.10)",
};
const mono = "'IBM Plex Mono', monospace";
const sans = "'DM Sans', sans-serif";

// ═══════════════════════════════════════════════════════════
// SPAN KIND COLORS + ICONS
// ═══════════════════════════════════════════════════════════
const KIND_META: Record<string, { color: string; icon: string; bg: string }> = {
  agent:      { color: C.accent,  icon: "🤖", bg: C.accentDim },
  llm:        { color: C.violet,  icon: "🧠", bg: C.violetDim },
  tool:       { color: C.amber,   icon: "🔧", bg: C.amberDim },
  governance: { color: C.red,     icon: "🛡️", bg: C.redDim },
  retrieval:  { color: C.cyan,    icon: "🔍", bg: C.cyanDim },
  chain:      { color: C.green,   icon: "🔗", bg: C.greenDim },
  custom:     { color: C.p2,      icon: "◆",  bg: "rgba(122,157,189,0.08)" },
};

const DECISION_COLOR: Record<string, string> = {
  allow: C.green, block: C.red, review: C.amber,
};

// ═══════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════
interface Span {
  id: number;
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  kind: string;
  name: string;
  status: string;
  start_time: string;
  end_time: string | null;
  duration_ms: number | null;
  agent_id: string | null;
  session_id: string | null;
  attributes: Record<string, any> | null;
  input: string | null;
  output: string | null;
  events: Array<Record<string, any>> | null;
  created_at: string;
}

interface GovernanceDecision {
  id: number;
  created_at: string;
  tool: string;
  decision: string;
  risk_score: number;
  explanation: string;
  policy_ids: string[];
  agent_id: string | null;
  trace_id: string | null;
  span_id: string | null;
}

interface TraceListItem {
  trace_id: string;
  agent_id: string | null;
  session_id: string | null;
  span_count: number;
  governance_count: number;
  root_span_name: string | null;
  start_time: string;
  end_time: string | null;
  total_duration_ms: number | null;
  has_errors: boolean;
  has_blocks: boolean;
}

interface TraceDetail {
  trace_id: string;
  agent_id: string | null;
  session_id: string | null;
  spans: Span[];
  governance_decisions: GovernanceDecision[];
  span_count: number;
  governance_count: number;
  start_time: string | null;
  end_time: string | null;
  total_duration_ms: number | null;
  has_errors: boolean;
  has_blocks: boolean;
}

// ═══════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════
function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });
}

function truncate(s: string | null, len: number): string {
  if (!s) return "";
  return s.length > len ? s.slice(0, len) + "…" : s;
}

// Build a tree from flat span list
interface SpanNode {
  span: Span;
  children: SpanNode[];
  depth: number;
}

function buildSpanTree(spans: Span[]): SpanNode[] {
  const map = new Map<string, SpanNode>();
  const roots: SpanNode[] = [];

  for (const s of spans) {
    map.set(s.span_id, { span: s, children: [], depth: 0 });
  }

  for (const s of spans) {
    const node = map.get(s.span_id)!;
    if (s.parent_span_id && map.has(s.parent_span_id)) {
      const parent = map.get(s.parent_span_id)!;
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }

  function setDepth(node: SpanNode, d: number) {
    node.depth = d;
    node.children.sort((a, b) =>
      new Date(a.span.start_time).getTime() - new Date(b.span.start_time).getTime()
    );
    for (const c of node.children) setDepth(c, d + 1);
  }
  roots.sort((a, b) =>
    new Date(a.span.start_time).getTime() - new Date(b.span.start_time).getTime()
  );
  for (const r of roots) setDepth(r, 0);

  return roots;
}

function flattenTree(nodes: SpanNode[]): SpanNode[] {
  const result: SpanNode[] = [];
  function walk(ns: SpanNode[]) {
    for (const n of ns) {
      result.push(n);
      walk(n.children);
    }
  }
  walk(nodes);
  return result;
}

// ═══════════════════════════════════════════════════════════
// SPAN ROW COMPONENT
// ═══════════════════════════════════════════════════════════
function SpanRow({
  node,
  selected,
  onClick,
}: {
  node: SpanNode;
  selected: boolean;
  onClick: () => void;
}) {
  const s = node.span;
  const meta = KIND_META[s.kind] || KIND_META.custom;
  const isGov = s.kind === "governance";
  const govAttrs = isGov && s.attributes ? s.attributes : null;
  const govDecision = govAttrs?.["governor.decision"];
  const govRisk = govAttrs?.["governor.risk_score"];

  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 10px",
        paddingLeft: 10 + node.depth * 20,
        background: selected ? C.bg3 : "transparent",
        borderLeft: selected ? `3px solid ${meta.color}` : "3px solid transparent",
        cursor: "pointer",
        transition: "all 0.1s",
        borderBottom: `1px solid ${C.line}`,
        minHeight: 36,
      }}
    >
      {/* Tree connector */}
      {node.depth > 0 && (
        <span style={{ color: C.line2, fontFamily: mono, fontSize: 14, userSelect: "none" }}>
          {"└"}
        </span>
      )}

      {/* Kind badge */}
      <span
        style={{
          fontFamily: mono,
          fontSize: 12,
          letterSpacing: 1,
          padding: "2px 6px",
          background: meta.bg,
          color: meta.color,
          border: `1px solid ${meta.color}`,
          textTransform: "uppercase",
          flexShrink: 0,
          whiteSpace: "nowrap",
        }}
      >
        {meta.icon} {s.kind}
      </span>

      {/* Span name */}
      <span
        style={{
          fontFamily: mono,
          fontSize: 14,
          color: C.p1,
          flex: 1,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {s.name}
      </span>

      {/* Governance decision badge */}
      {isGov && govDecision && (
        <span
          style={{
            fontFamily: mono,
            fontSize: 12,
            padding: "1px 6px",
            letterSpacing: 1,
            textTransform: "uppercase",
            background:
              govDecision === "block"
                ? C.redDim
                : govDecision === "review"
                ? C.amberDim
                : C.greenDim,
            color: DECISION_COLOR[govDecision] || C.p2,
            border: `1px solid ${DECISION_COLOR[govDecision] || C.p3}`,
          }}
        >
          {govDecision}
          {govRisk != null && ` · ${govRisk}`}
        </span>
      )}

      {/* Status */}
      {s.status === "error" && (
        <span style={{ fontFamily: mono, fontSize: 12, color: C.red }}>ERROR</span>
      )}

      {/* Duration */}
      <span
        style={{
          fontFamily: mono,
          fontSize: 13,
          color: C.p3,
          flexShrink: 0,
          minWidth: 52,
          textAlign: "right",
        }}
      >
        {fmtMs(s.duration_ms)}
      </span>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// SPAN DETAIL PANEL
// ═══════════════════════════════════════════════════════════
function SpanDetail({ span }: { span: Span }) {
  const meta = KIND_META[span.kind] || KIND_META.custom;
  const isGov = span.kind === "governance";
  const govTrace = isGov && span.attributes?.["governor.trace"];

  return (
    <div style={{ padding: 14, overflow: "auto", maxHeight: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span
          style={{
            fontFamily: mono,
            fontSize: 13,
            padding: "2px 8px",
            background: meta.bg,
            color: meta.color,
            border: `1px solid ${meta.color}`,
            textTransform: "uppercase",
            letterSpacing: 1,
          }}
        >
          {meta.icon} {span.kind}
        </span>
        <span style={{ fontFamily: mono, fontSize: 15, color: C.p1, fontWeight: 700 }}>
          {span.name}
        </span>
      </div>

      {/* Metadata grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "120px 1fr",
          gap: "4px 10px",
          marginBottom: 14,
          fontFamily: mono,
          fontSize: 14,
        }}
      >
        <span style={{ color: C.p3 }}>SPAN ID</span>
        <span style={{ color: C.p2 }}>{span.span_id}</span>
        {span.parent_span_id && (
          <>
            <span style={{ color: C.p3 }}>PARENT</span>
            <span style={{ color: C.p2 }}>{span.parent_span_id}</span>
          </>
        )}
        <span style={{ color: C.p3 }}>STATUS</span>
        <span style={{ color: span.status === "error" ? C.red : C.green }}>
          {span.status.toUpperCase()}
        </span>
        <span style={{ color: C.p3 }}>START</span>
        <span style={{ color: C.p2 }}>{fmtDate(span.start_time)}</span>
        {span.end_time && (
          <>
            <span style={{ color: C.p3 }}>END</span>
            <span style={{ color: C.p2 }}>{fmtDate(span.end_time)}</span>
          </>
        )}
        <span style={{ color: C.p3 }}>DURATION</span>
        <span style={{ color: C.p1, fontWeight: 700 }}>{fmtMs(span.duration_ms)}</span>
        {span.agent_id && (
          <>
            <span style={{ color: C.p3 }}>AGENT</span>
            <span style={{ color: C.p2 }}>{span.agent_id}</span>
          </>
        )}
      </div>

      {/* Governance pipeline trace (for governance spans) */}
      {govTrace && Array.isArray(govTrace) && (
        <div style={{ marginBottom: 14 }}>
          <div
            style={{
              fontFamily: mono,
              fontSize: 12,
              letterSpacing: 1.5,
              color: C.p3,
              textTransform: "uppercase",
              marginBottom: 6,
            }}
          >
            GOVERNANCE PIPELINE
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            {govTrace.map((step: any, i: number) => {
              const oc = step.outcome;
              const clr =
                oc === "block" ? C.red : oc === "review" ? C.amber : C.green;
              return (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "4px 8px",
                    background: C.bg0,
                    border: `1px solid ${C.line}`,
                    fontFamily: mono,
                    fontSize: 13,
                  }}
                >
                  <span style={{ color: C.p3, width: 16 }}>L{step.layer}</span>
                  <span style={{ color: C.p1, flex: 1 }}>{step.name}</span>
                  <span
                    style={{
                      color: clr,
                      textTransform: "uppercase",
                      letterSpacing: 1,
                      fontSize: 12,
                      fontWeight: 700,
                    }}
                  >
                    {oc}
                  </span>
                  {step.risk > 0 && (
                    <span style={{ color: C.red, fontSize: 12 }}>RISK {step.risk}</span>
                  )}
                  <span style={{ color: C.p3, fontSize: 12 }}>{fmtMs(step.duration_ms)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Governance attributes */}
      {isGov && span.attributes && (
        <div style={{ marginBottom: 14 }}>
          <div
            style={{
              fontFamily: mono,
              fontSize: 12,
              letterSpacing: 1.5,
              color: C.p3,
              textTransform: "uppercase",
              marginBottom: 6,
            }}
          >
            GOVERNANCE RESULT
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "140px 1fr",
              gap: "3px 10px",
              fontFamily: mono,
              fontSize: 14,
            }}
          >
            <span style={{ color: C.p3 }}>DECISION</span>
            <span
              style={{
                color:
                  DECISION_COLOR[span.attributes["governor.decision"]] || C.p1,
                fontWeight: 700,
              }}
            >
              {String(span.attributes["governor.decision"] || "").toUpperCase()}
            </span>
            <span style={{ color: C.p3 }}>RISK SCORE</span>
            <span style={{ color: C.p1 }}>
              {span.attributes["governor.risk_score"]}
            </span>
            <span style={{ color: C.p3 }}>TOOL</span>
            <span style={{ color: C.p2 }}>
              {span.attributes["governor.tool"]}
            </span>
            {span.attributes["governor.policy_ids"]?.length > 0 && (
              <>
                <span style={{ color: C.p3 }}>MATCHED POLICIES</span>
                <span style={{ color: C.amber }}>
                  {span.attributes["governor.policy_ids"].join(", ")}
                </span>
              </>
            )}
            {span.attributes["governor.chain_pattern"] && (
              <>
                <span style={{ color: C.p3 }}>CHAIN PATTERN</span>
                <span style={{ color: C.red }}>
                  {span.attributes["governor.chain_pattern"]}
                </span>
              </>
            )}
          </div>
        </div>
      )}

      {/* Input / Output */}
      {span.input && (
        <div style={{ marginBottom: 12 }}>
          <div
            style={{
              fontFamily: mono,
              fontSize: 12,
              letterSpacing: 1.5,
              color: C.p3,
              textTransform: "uppercase",
              marginBottom: 4,
            }}
          >
            INPUT
          </div>
          <pre
            style={{
              fontFamily: mono,
              fontSize: 13,
              color: C.p2,
              background: C.bg0,
              border: `1px solid ${C.line}`,
              padding: 8,
              overflow: "auto",
              maxHeight: 200,
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
            }}
          >
            {tryFormatJson(span.input)}
          </pre>
        </div>
      )}
      {span.output && (
        <div style={{ marginBottom: 12 }}>
          <div
            style={{
              fontFamily: mono,
              fontSize: 12,
              letterSpacing: 1.5,
              color: C.p3,
              textTransform: "uppercase",
              marginBottom: 4,
            }}
          >
            OUTPUT
          </div>
          <pre
            style={{
              fontFamily: mono,
              fontSize: 13,
              color: C.p2,
              background: C.bg0,
              border: `1px solid ${C.line}`,
              padding: 8,
              overflow: "auto",
              maxHeight: 200,
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
            }}
          >
            {tryFormatJson(span.output)}
          </pre>
        </div>
      )}

      {/* Generic attributes */}
      {span.attributes && !isGov && Object.keys(span.attributes).length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div
            style={{
              fontFamily: mono,
              fontSize: 12,
              letterSpacing: 1.5,
              color: C.p3,
              textTransform: "uppercase",
              marginBottom: 4,
            }}
          >
            ATTRIBUTES
          </div>
          <pre
            style={{
              fontFamily: mono,
              fontSize: 13,
              color: C.p2,
              background: C.bg0,
              border: `1px solid ${C.line}`,
              padding: 8,
              overflow: "auto",
              maxHeight: 200,
              whiteSpace: "pre-wrap",
            }}
          >
            {JSON.stringify(span.attributes, null, 2)}
          </pre>
        </div>
      )}

      {/* Events */}
      {span.events && span.events.length > 0 && (
        <div>
          <div
            style={{
              fontFamily: mono,
              fontSize: 12,
              letterSpacing: 1.5,
              color: C.p3,
              textTransform: "uppercase",
              marginBottom: 4,
            }}
          >
            EVENTS ({span.events.length})
          </div>
          {span.events.map((ev: any, i: number) => (
            <div
              key={i}
              style={{
                fontFamily: mono,
                fontSize: 13,
                color: C.p2,
                padding: "3px 8px",
                background: C.bg0,
                border: `1px solid ${C.line}`,
                marginBottom: 2,
              }}
            >
              <span style={{ color: C.p3, marginRight: 8 }}>
                {ev.time ? fmtTime(ev.time) : `#${i + 1}`}
              </span>
              <span style={{ color: C.p1 }}>{ev.name || "event"}</span>
              {ev.attrs && (
                <span style={{ color: C.p3, marginLeft: 8 }}>
                  {JSON.stringify(ev.attrs)}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function tryFormatJson(s: string): string {
  try {
    return JSON.stringify(JSON.parse(s), null, 2);
  } catch {
    return s;
  }
}

// ═══════════════════════════════════════════════════════════
// MAIN: TRACE VIEWER COMPONENT
// ═══════════════════════════════════════════════════════════
export default function TraceViewer() {
  const [traces, setTraces] = useState<TraceListItem[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<TraceDetail | null>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState({ agent_id: "", has_blocks: "" });

  // Fetch trace list
  const fetchTraces = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {};
      if (filter.agent_id) params.agent_id = filter.agent_id;
      if (filter.has_blocks === "true") params.has_blocks = "true";
      if (filter.has_blocks === "false") params.has_blocks = "false";

      const token = localStorage.getItem("ocg_token");
      const res = await api.get("/traces", {
        params,
        headers: { Authorization: `Bearer ${token}` },
      });
      setTraces(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || "Failed to load traces");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  // Fetch single trace detail
  const fetchTraceDetail = useCallback(async (traceId: string) => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem("ocg_token");
      const res = await api.get(`/traces/${traceId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setSelectedTrace(res.data);
      setSelectedSpanId(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || "Failed to load trace");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTraces();
  }, [fetchTraces]);

  // Current selected span
  const selectedSpan =
    selectedTrace && selectedSpanId
      ? selectedTrace.spans.find((s) => s.span_id === selectedSpanId) || null
      : null;

  // ═══════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 0 }}>
      {/* Header bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "10px 14px",
          borderBottom: `1px solid ${C.line}`,
          flexShrink: 0,
        }}
      >
        {selectedTrace ? (
          <>
            <button
              onClick={() => {
                setSelectedTrace(null);
                setSelectedSpanId(null);
              }}
              style={{
                fontFamily: mono,
                fontSize: 13,
                letterSpacing: 1,
                padding: "4px 10px",
                background: "transparent",
                border: `1px solid ${C.line2}`,
                color: C.p2,
                cursor: "pointer",
              }}
            >
              ← BACK
            </button>
            <span style={{ fontFamily: mono, fontSize: 15, color: C.p1, fontWeight: 700 }}>
              TRACE
            </span>
            <span style={{ fontFamily: mono, fontSize: 14, color: C.accent }}>
              {selectedTrace.trace_id}
            </span>
            <span style={{ fontFamily: mono, fontSize: 13, color: C.p3 }}>
              {selectedTrace.span_count} spans
              {selectedTrace.governance_count > 0 &&
                ` · ${selectedTrace.governance_count} governance`}
              {selectedTrace.total_duration_ms != null &&
                ` · ${fmtMs(selectedTrace.total_duration_ms)}`}
            </span>
            {selectedTrace.has_blocks && (
              <span
                style={{
                  fontFamily: mono,
                  fontSize: 12,
                  padding: "1px 6px",
                  background: C.redDim,
                  color: C.red,
                  border: `1px solid ${C.red}`,
                  letterSpacing: 1,
                }}
              >
                HAS BLOCKS
              </span>
            )}
          </>
        ) : (
          <>
            <span
              style={{
                fontFamily: mono,
                fontSize: 15,
                color: C.p1,
                fontWeight: 700,
                letterSpacing: 1,
              }}
            >
              AGENT TRACES
            </span>
            <input
              value={filter.agent_id}
              onChange={(e) => setFilter((f) => ({ ...f, agent_id: e.target.value }))}
              placeholder="Filter: agent_id"
              style={{
                fontFamily: mono,
                fontSize: 14,
                background: C.bg0,
                border: `1px solid ${C.line2}`,
                color: C.text,
                padding: "4px 8px",
                outline: "none",
                width: 160,
              }}
            />
            <select
              value={filter.has_blocks}
              onChange={(e) => setFilter((f) => ({ ...f, has_blocks: e.target.value }))}
              style={{
                fontFamily: mono,
                fontSize: 14,
                background: C.bg0,
                border: `1px solid ${C.line2}`,
                color: C.text,
                padding: "4px 8px",
                outline: "none",
              }}
            >
              <option value="">All traces</option>
              <option value="true">Has blocks</option>
              <option value="false">No blocks</option>
            </select>
            <button
              onClick={fetchTraces}
              style={{
                fontFamily: mono,
                fontSize: 13,
                letterSpacing: 1,
                padding: "4px 10px",
                background: C.accentDim,
                border: `1px solid ${C.accent}`,
                color: C.accent,
                cursor: "pointer",
              }}
            >
              REFRESH
            </button>
            <span style={{ fontFamily: mono, fontSize: 13, color: C.p3, marginLeft: "auto" }}>
              {traces.length} traces
            </span>
          </>
        )}
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            fontFamily: mono,
            fontSize: 14,
            color: C.red,
            padding: "10px 14px",
            background: C.redDim,
            borderBottom: `1px solid ${C.line}`,
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <span>{error}</span>
          {error.toLowerCase().includes("token") && (
            <span style={{ fontSize: 13, color: C.amber }}>
              — Try logging out and back in to refresh your session.
            </span>
          )}
          <button
            onClick={fetchTraces}
            style={{
              marginLeft: "auto",
              fontFamily: mono,
              fontSize: 12,
              padding: "4px 12px",
              border: `1px solid ${C.line2}`,
              color: C.p2,
              background: "transparent",
              cursor: "pointer",
            }}
          >
            ↻ RETRY
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div
          style={{
            fontFamily: mono,
            fontSize: 14,
            color: C.p3,
            padding: "6px 14px",
            borderBottom: `1px solid ${C.line}`,
          }}
        >
          Loading…
        </div>
      )}

      {/* ═══ TRACE LIST VIEW ═══ */}
      {!selectedTrace && !loading && (
        <div style={{ flex: 1, overflow: "auto" }}>
          {traces.length === 0 ? (
            <div
              style={{
                fontFamily: mono,
                fontSize: 14,
                color: C.p3,
                padding: 30,
                textAlign: "center",
              }}
            >
              No traces found. Agents send trace spans via POST /traces/ingest.
              <br />
              <span style={{ fontSize: 13, color: C.muted }}>
                Governance decisions with trace_id in context are auto-correlated.
              </span>
            </div>
          ) : (
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontFamily: mono,
                fontSize: 14,
              }}
            >
              <thead>
                <tr style={{ borderBottom: `1px solid ${C.line2}` }}>
                  {["TRACE", "AGENT", "ROOT SPAN", "SPANS", "GOV", "DURATION", "STATUS", "TIME"].map(
                    (h) => (
                      <th
                        key={h}
                        style={{
                          padding: "6px 10px",
                          textAlign: "left",
                          fontFamily: mono,
                          fontSize: 12,
                          letterSpacing: 1.5,
                          color: C.p3,
                          textTransform: "uppercase",
                          fontWeight: 400,
                        }}
                      >
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody>
                {traces.map((t) => (
                  <tr
                    key={t.trace_id}
                    onClick={() => fetchTraceDetail(t.trace_id)}
                    style={{
                      borderBottom: `1px solid ${C.line}`,
                      cursor: "pointer",
                      transition: "background 0.1s",
                    }}
                    onMouseEnter={(e) =>
                      (e.currentTarget.style.background = C.bg2)
                    }
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.background = "transparent")
                    }
                  >
                    <td style={{ padding: "6px 10px", color: C.accent }}>
                      {truncate(t.trace_id, 20)}
                    </td>
                    <td style={{ padding: "6px 10px", color: C.p2 }}>
                      {t.agent_id || "—"}
                    </td>
                    <td style={{ padding: "6px 10px", color: C.p1 }}>
                      {truncate(t.root_span_name, 30) || "—"}
                    </td>
                    <td style={{ padding: "6px 10px", color: C.p1 }}>{t.span_count}</td>
                    <td
                      style={{
                        padding: "6px 10px",
                        color: t.governance_count > 0 ? C.amber : C.p3,
                      }}
                    >
                      {t.governance_count}
                    </td>
                    <td style={{ padding: "6px 10px", color: C.p2 }}>
                      {fmtMs(t.total_duration_ms)}
                    </td>
                    <td style={{ padding: "6px 10px" }}>
                      <span style={{ display: "flex", gap: 4 }}>
                        {t.has_blocks && (
                          <span
                            style={{
                              fontSize: 11,
                              padding: "1px 4px",
                              background: C.redDim,
                              color: C.red,
                              border: `1px solid ${C.red}`,
                            }}
                          >
                            BLOCK
                          </span>
                        )}
                        {t.has_errors && (
                          <span
                            style={{
                              fontSize: 11,
                              padding: "1px 4px",
                              background: C.amberDim,
                              color: C.amber,
                              border: `1px solid ${C.amber}`,
                            }}
                          >
                            ERROR
                          </span>
                        )}
                        {!t.has_blocks && !t.has_errors && (
                          <span style={{ fontSize: 11, color: C.green }}>OK</span>
                        )}
                      </span>
                    </td>
                    <td style={{ padding: "6px 10px", color: C.p3 }}>
                      {fmtDate(t.start_time)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ═══ TRACE DETAIL VIEW ═══ */}
      {selectedTrace && (
        <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
          {/* Span tree (left) */}
          <div
            style={{
              width: selectedSpan ? "50%" : "100%",
              borderRight: selectedSpan ? `1px solid ${C.line}` : "none",
              overflow: "auto",
              transition: "width 0.15s",
            }}
          >
            {flattenTree(buildSpanTree(selectedTrace.spans)).map((node) => (
              <SpanRow
                key={node.span.span_id}
                node={node}
                selected={selectedSpanId === node.span.span_id}
                onClick={() =>
                  setSelectedSpanId((prev) =>
                    prev === node.span.span_id ? null : node.span.span_id
                  )
                }
              />
            ))}

            {/* Unlinked governance decisions */}
            {selectedTrace.governance_decisions.filter(
              (d) => !selectedTrace.spans.some((s) => s.kind === "governance" && s.attributes?.["governor.tool"] === d.tool && Math.abs(new Date(s.start_time).getTime() - new Date(d.created_at).getTime()) < 5000)
            ).length > 0 && (
              <div style={{ padding: "10px 14px" }}>
                <div
                  style={{
                    fontFamily: mono,
                    fontSize: 12,
                    letterSpacing: 1.5,
                    color: C.p3,
                    textTransform: "uppercase",
                    marginBottom: 6,
                  }}
                >
                  CORRELATED GOVERNANCE DECISIONS
                </div>
                {selectedTrace.governance_decisions.map((d) => (
                  <div
                    key={d.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "5px 8px",
                      background: C.bg0,
                      border: `1px solid ${C.line}`,
                      marginBottom: 2,
                      fontFamily: mono,
                      fontSize: 13,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 12,
                        padding: "1px 5px",
                        background: C.redDim,
                        color: C.red,
                        border: `1px solid ${C.red}`,
                        letterSpacing: 1,
                      }}
                    >
                      🛡️ GOV
                    </span>
                    <span style={{ color: C.p1 }}>{d.tool}</span>
                    <span
                      style={{
                        color: DECISION_COLOR[d.decision] || C.p2,
                        fontWeight: 700,
                        textTransform: "uppercase",
                        fontSize: 12,
                        letterSpacing: 1,
                      }}
                    >
                      {d.decision}
                    </span>
                    <span style={{ color: C.p3, fontSize: 12 }}>
                      risk {d.risk_score}
                    </span>
                    <span
                      style={{ color: C.p3, flex: 1, textAlign: "right", fontSize: 12 }}
                    >
                      {fmtTime(d.created_at)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Span detail (right) */}
          {selectedSpan && (
            <div
              style={{
                width: "50%",
                overflow: "auto",
                background: C.bg1,
              }}
            >
              <SpanDetail span={selectedSpan} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
