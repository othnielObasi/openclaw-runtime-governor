"use client";

import React, { useEffect, useState, useCallback } from "react";
import { api } from "./ApiClient";

/* ── Design tokens (matches GovernorDashboard) ────────────────────────── */
const C = {
  bg0: "#080e1a", bg1: "#0f1b2d", bg2: "#1d3452",
  line: "#1d3452", line2: "#243d58",
  p1: "#e2e8f0", p2: "#8fa3bf", p3: "#4a6785",
  green: "#22c55e", greenDim: "rgba(34,197,94,0.10)",
  amber: "#f59e0b", amberDim: "rgba(245,158,11,0.10)",
  red: "#ef4444", redDim: "rgba(239,68,68,0.10)",
  accent: "#e8412a",
};
const mono = "'IBM Plex Mono', monospace";
const sans = "'DM Sans', sans-serif";

/* ── Types ────────────────────────────────────────────────────────────── */
interface Policy {
  policy_id: string;
  description: string;
  severity: number;
  match_json: Record<string, unknown>;
  action: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

/* ── Component ────────────────────────────────────────────────────────── */
export const PolicyEditor: React.FC = () => {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Create form state
  const [policyId, setPolicyId] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState(50);
  const [matchJson, setMatchJson] = useState('{"tool": "shell"}');
  const [action, setAction] = useState<"allow" | "block" | "review">("review");
  const [jsonError, setJsonError] = useState<string | null>(null);

  // Inline edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<{
    description: string; severity: number; matchJson: string; action: string;
  }>({ description: "", severity: 50, matchJson: "{}", action: "review" });
  const [editJsonError, setEditJsonError] = useState<string | null>(null);

  const flash = (msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(null), 3000); };

  const loadPolicies = useCallback(() => {
    api.get<Policy[]>("/policies")
      .then(res => setPolicies(res.data))
      .catch(e => setError(e?.response?.data?.detail || e?.message || "Failed to load policies"));
  }, []);

  useEffect(() => { loadPolicies(); }, [loadPolicies]);

  /* ── Validate JSON + regex ────────────────────────────────────────── */
  const validateMatchJson = (raw: string): string | null => {
    let obj: Record<string, unknown>;
    try { obj = JSON.parse(raw); } catch { return "Invalid JSON"; }
    for (const key of ["url_regex", "args_regex"]) {
      const pattern = obj[key];
      if (typeof pattern === "string") {
        try { new RegExp(pattern); } catch (e: any) { return `Bad regex in '${key}': ${e.message}`; }
      }
    }
    return null;
  };

  useEffect(() => { setJsonError(validateMatchJson(matchJson)); }, [matchJson]);

  /* ── Create ───────────────────────────────────────────────────────── */
  const onCreate = async () => {
    setError(null);
    const vErr = validateMatchJson(matchJson);
    if (vErr) { setError(vErr); return; }
    if (!policyId.trim()) { setError("Policy ID is required."); return; }
    setLoading(true);
    try {
      await api.post("/policies", {
        policy_id: policyId.trim(), description, severity,
        match_json: JSON.parse(matchJson), action,
      });
      setPolicyId(""); setDescription(""); setMatchJson('{"tool": "shell"}');
      setSeverity(50); setAction("review");
      flash(`Policy '${policyId.trim()}' created`);
      loadPolicies();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || "Failed to create policy");
    } finally { setLoading(false); }
  };

  /* ── Toggle ───────────────────────────────────────────────────────── */
  const onToggle = async (id: string) => {
    try {
      await api.patch(`/policies/${id}/toggle`);
      loadPolicies();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || "Toggle failed");
    }
  };

  /* ── Start editing ────────────────────────────────────────────────── */
  const startEdit = (p: Policy) => {
    setEditingId(p.policy_id);
    setEditForm({
      description: p.description,
      severity: p.severity,
      matchJson: JSON.stringify(p.match_json, null, 2),
      action: p.action,
    });
    setEditJsonError(null);
  };

  /* ── Save edit ────────────────────────────────────────────────────── */
  const saveEdit = async () => {
    if (!editingId) return;
    const vErr = validateMatchJson(editForm.matchJson);
    if (vErr) { setEditJsonError(vErr); return; }
    setLoading(true);
    try {
      await api.patch(`/policies/${editingId}`, {
        description: editForm.description,
        severity: editForm.severity,
        match_json: JSON.parse(editForm.matchJson),
        action: editForm.action,
      });
      setEditingId(null);
      flash(`Policy '${editingId}' updated`);
      loadPolicies();
    } catch (e: any) {
      setEditJsonError(e?.response?.data?.detail || e?.message || "Update failed");
    } finally { setLoading(false); }
  };

  /* ── Delete ───────────────────────────────────────────────────────── */
  const onDelete = async (id: string) => {
    if (!confirm(`Delete policy '${id}' permanently?`)) return;
    try {
      await api.delete(`/policies/${id}`);
      flash(`Policy '${id}' deleted`);
      loadPolicies();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || "Delete failed");
    }
  };

  /* ── Severity color helper ────────────────────────────────────────── */
  const sevColor = (s: number) => s >= 80 ? C.red : s >= 50 ? C.amber : C.green;
  const actionColor = (a: string) =>
    a === "block" ? C.red : a === "review" ? C.amber : C.green;

  /* ── Render ───────────────────────────────────────────────────────── */
  const inputStyle: React.CSSProperties = {
    fontFamily: mono, fontSize: 11, color: C.p1, background: C.bg0,
    border: `1px solid ${C.line2}`, padding: "7px 10px", width: "100%",
    boxSizing: "border-box", outline: "none",
  };
  const labelStyle: React.CSSProperties = {
    fontFamily: mono, fontSize: 8, letterSpacing: 1.5, color: C.p3,
    textTransform: "uppercase" as const, marginBottom: 3,
  };
  const btnStyle = (color: string, dim: string): React.CSSProperties => ({
    fontFamily: mono, fontSize: 9, letterSpacing: 1.5, padding: "5px 14px",
    border: `1px solid ${color}`, color, background: dim,
    cursor: "pointer", textTransform: "uppercase" as const,
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* ── Header ────────────────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontFamily: mono, fontSize: 13, fontWeight: 700, color: C.p1, letterSpacing: 2 }}>
            POLICY MANAGEMENT
          </div>
          <div style={{ fontFamily: sans, fontSize: 10, color: C.p3, marginTop: 2 }}>
            {policies.length} dynamic {policies.length === 1 ? "policy" : "policies"}
            {" · "}{policies.filter(p => p.is_active).length} active
          </div>
        </div>
        <button onClick={loadPolicies} style={btnStyle(C.p3, "transparent")}>
          ↻ REFRESH
        </button>
      </div>

      {/* ── Feedback ──────────────────────────────────────────────── */}
      {error && (
        <div style={{ padding: "8px 12px", background: C.redDim, border: `1px solid ${C.red}`,
          fontFamily: mono, fontSize: 10, color: C.red }}>
          {error}
          <span onClick={() => setError(null)}
            style={{ float: "right", cursor: "pointer", opacity: 0.7 }}>✕</span>
        </div>
      )}
      {success && (
        <div style={{ padding: "8px 12px", background: C.greenDim, border: `1px solid ${C.green}`,
          fontFamily: mono, fontSize: 10, color: C.green }}>
          ✓ {success}
        </div>
      )}

      {/* ── Create Form ───────────────────────────────────────────── */}
      <div style={{ background: C.bg1, border: `1px solid ${C.line}`, padding: 16 }}>
        <div style={{ fontFamily: mono, fontSize: 9, letterSpacing: 2, color: C.p3,
          textTransform: "uppercase" as const, marginBottom: 12, borderBottom: `1px solid ${C.line}`,
          paddingBottom: 8 }}>
          + CREATE NEW POLICY
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <div style={labelStyle}>Policy ID</div>
            <input style={inputStyle} placeholder="e.g. block-external-uploads"
              value={policyId} onChange={e => setPolicyId(e.target.value)} />
          </div>
          <div>
            <div style={labelStyle}>Description</div>
            <input style={inputStyle} placeholder="Human-readable description"
              value={description} onChange={e => setDescription(e.target.value)} />
          </div>
          <div>
            <div style={labelStyle}>Severity ({severity})</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="range" min={0} max={100} value={severity}
                onChange={e => setSeverity(parseInt(e.target.value, 10))}
                style={{ flex: 1 }} />
              <span style={{ fontFamily: mono, fontSize: 12, fontWeight: 700,
                color: sevColor(severity), minWidth: 28, textAlign: "right" }}>
                {severity}
              </span>
            </div>
          </div>
          <div>
            <div style={labelStyle}>Action</div>
            <select style={{ ...inputStyle, cursor: "pointer" }} value={action}
              onChange={e => setAction(e.target.value as any)}>
              <option value="allow">allow</option>
              <option value="block">block</option>
              <option value="review">review</option>
            </select>
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <div style={labelStyle}>
              Match JSON
              {jsonError && (
                <span style={{ color: C.red, marginLeft: 8, letterSpacing: 0.5 }}>
                  — {jsonError}
                </span>
              )}
            </div>
            <textarea style={{ ...inputStyle, height: 64, resize: "vertical" as const }}
              value={matchJson} onChange={e => setMatchJson(e.target.value)} />
          </div>
        </div>
        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <button onClick={onCreate} disabled={loading || !!jsonError || !policyId.trim()}
            style={{
              ...btnStyle(C.green, C.greenDim),
              opacity: (loading || !!jsonError || !policyId.trim()) ? 0.4 : 1,
              cursor: (loading || !!jsonError || !policyId.trim()) ? "not-allowed" : "pointer",
            }}>
            {loading ? "CREATING…" : "CREATE POLICY"}
          </button>
        </div>
      </div>

      {/* ── Policy List ───────────────────────────────────────────── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 1, background: C.line }}>
        {policies.length === 0 && (
          <div style={{ background: C.bg1, padding: 24, textAlign: "center",
            fontFamily: sans, fontSize: 11, color: C.p3 }}>
            No dynamic policies configured. Create one above.
          </div>
        )}
        {policies.map(p => {
          const isEditing = editingId === p.policy_id;
          return (
            <div key={p.policy_id}
              style={{
                background: C.bg1, padding: "12px 16px",
                opacity: p.is_active ? 1 : 0.5,
                borderLeft: `3px solid ${p.is_active ? actionColor(p.action) : C.p3}`,
              }}>
              {isEditing ? (
                /* ── Inline Edit ──────────────────────────────────── */
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                    <div>
                      <div style={labelStyle}>Description</div>
                      <input style={inputStyle} value={editForm.description}
                        onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))} />
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                      <div>
                        <div style={labelStyle}>Severity</div>
                        <input type="number" min={0} max={100} style={inputStyle}
                          value={editForm.severity}
                          onChange={e => setEditForm(f => ({ ...f, severity: parseInt(e.target.value, 10) || 0 }))} />
                      </div>
                      <div>
                        <div style={labelStyle}>Action</div>
                        <select style={{ ...inputStyle, cursor: "pointer" }} value={editForm.action}
                          onChange={e => setEditForm(f => ({ ...f, action: e.target.value }))}>
                          <option value="allow">allow</option>
                          <option value="block">block</option>
                          <option value="review">review</option>
                        </select>
                      </div>
                    </div>
                  </div>
                  <div>
                    <div style={labelStyle}>
                      Match JSON
                      {editJsonError && (
                        <span style={{ color: C.red, marginLeft: 8 }}>— {editJsonError}</span>
                      )}
                    </div>
                    <textarea style={{ ...inputStyle, height: 56, resize: "vertical" as const }}
                      value={editForm.matchJson}
                      onChange={e => {
                        const v = e.target.value;
                        setEditForm(f => ({ ...f, matchJson: v }));
                        setEditJsonError(validateMatchJson(v));
                      }} />
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={saveEdit} disabled={!!editJsonError}
                      style={{ ...btnStyle(C.green, C.greenDim),
                        opacity: editJsonError ? 0.4 : 1,
                        cursor: editJsonError ? "not-allowed" : "pointer" }}>
                      SAVE
                    </button>
                    <button onClick={() => setEditingId(null)}
                      style={btnStyle(C.p3, "transparent")}>
                      CANCEL
                    </button>
                  </div>
                </div>
              ) : (
                /* ── Read View ────────────────────────────────────── */
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span style={{ fontFamily: mono, fontSize: 12, fontWeight: 600, color: C.p1 }}>
                        {p.policy_id}
                      </span>
                      <span style={{
                        fontFamily: mono, fontSize: 8, letterSpacing: 1, padding: "1px 6px",
                        border: `1px solid ${actionColor(p.action)}`,
                        color: actionColor(p.action),
                      }}>
                        {p.action.toUpperCase()}
                      </span>
                      <span style={{
                        fontFamily: mono, fontSize: 8, letterSpacing: 1, padding: "1px 6px",
                        border: `1px solid ${sevColor(p.severity)}`,
                        color: sevColor(p.severity),
                      }}>
                        SEV {p.severity}
                      </span>
                      {!p.is_active && (
                        <span style={{
                          fontFamily: mono, fontSize: 8, letterSpacing: 1, padding: "1px 6px",
                          border: `1px solid ${C.p3}`, color: C.p3,
                        }}>
                          DISABLED
                        </span>
                      )}
                    </div>
                    <div style={{ fontFamily: sans, fontSize: 11, color: C.p2, marginBottom: 4 }}>
                      {p.description}
                    </div>
                    <pre style={{
                      fontFamily: mono, fontSize: 9, color: C.p3, margin: 0,
                      whiteSpace: "pre-wrap", wordBreak: "break-all",
                    }}>
                      {JSON.stringify(p.match_json)}
                    </pre>
                    {p.updated_at && (
                      <div style={{ fontFamily: mono, fontSize: 8, color: C.p3, marginTop: 4, opacity: 0.6 }}>
                        Updated {new Date(p.updated_at).toLocaleString()}
                      </div>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 6, flexShrink: 0, marginLeft: 12 }}>
                    <button onClick={() => startEdit(p)}
                      style={btnStyle(C.accent, "transparent")}>
                      EDIT
                    </button>
                    <button onClick={() => onToggle(p.policy_id)}
                      style={btnStyle(p.is_active ? C.amber : C.green,
                        p.is_active ? C.amberDim : C.greenDim)}>
                      {p.is_active ? "DISABLE" : "ENABLE"}
                    </button>
                    <button onClick={() => onDelete(p.policy_id)}
                      style={btnStyle(C.red, C.redDim)}>
                      DELETE
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
