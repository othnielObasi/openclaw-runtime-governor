"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import { api } from "./ApiClient";
import { useActionStream, StreamAction, StreamStatus } from "./useActionStream";

interface ActionLog {
  id: number;
  created_at: string;
  tool: string;
  decision: string;
  risk_score: number;
  explanation: string;
  policy_ids: string[];
  agent_id?: string;
  conversation_id?: string;
}

const DECISION_STYLES: Record<string, string> = {
  block:  "bg-red-500/20 text-red-300 border border-red-500/30",
  review: "bg-amber-500/20 text-amber-300 border border-amber-500/30",
  allow:  "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30",
};

const RISK_COLOR = (score: number) => {
  if (score >= 80) return "text-red-400";
  if (score >= 50) return "text-amber-400";
  return "text-emerald-400";
};

const STATUS_DOT: Record<StreamStatus, string> = {
  connected:    "bg-emerald-500",
  connecting:   "bg-amber-500 animate-pulse",
  disconnected: "bg-slate-500",
  error:        "bg-red-500",
};

const STATUS_LABEL: Record<StreamStatus, string> = {
  connected:    "Live",
  connecting:   "Connecting...",
  disconnected: "Offline",
  error:        "Error",
};

/** Convert a StreamAction (from SSE) into the same ActionLog shape */
function streamToLog(s: StreamAction, idx: number): ActionLog {
  return {
    id: -(idx + 1), // negative IDs so they don't clash with DB rows
    created_at: new Date(s.timestamp * 1000).toISOString(),
    tool: s.tool,
    decision: s.decision,
    risk_score: s.risk_score,
    explanation: s.explanation,
    policy_ids: s.policy_ids ?? [],
    agent_id: s.agent_id,
    conversation_id: (s as any).conversation_id,
  };
}

export const RecentActions: React.FC = () => {
  const [dbItems, setDbItems] = useState<ActionLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const AUTO_REFRESH_SEC = 30;

  // Real-time SSE stream
  const { events: streamEvents, status: streamStatus, subscriberCount } =
    useActionStream({ maxItems: 50 });

  const load = useCallback(() => {
    api
      .get<ActionLog[]>("/actions", { params: { limit: 20 } })
      .then(res => {
        setDbItems(res.data);
        setError(null);
        setLastRefresh(new Date());
      })
      .catch(e => setError(e?.message || "Failed to load actions"))
      .finally(() => setLoading(false));
  }, []);

  // Initial load + fallback polling (longer interval when streaming)
  useEffect(() => {
    load();
    const interval = setInterval(
      load,
      streamStatus === "connected" ? 60_000 : AUTO_REFRESH_SEC * 1000
    );
    return () => clearInterval(interval);
  }, [load, streamStatus]);

  // Merge: real-time events first, then DB items (deduplicated by tool+timestamp window)
  const items = useMemo(() => {
    const realtime = streamEvents.map(streamToLog);
    // Combine: real-time items first (newest), then DB items
    const merged = [...realtime, ...dbItems];
    // Deduplicate: keep first occurrence (real-time preferred over DB poll)
    const seen = new Set<string>();
    return merged.filter((item) => {
      // Use tool + decision + approx timestamp as dedup key
      const key = `${item.tool}:${item.decision}:${item.created_at.slice(0, 19)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).slice(0, 30);
  }, [streamEvents, dbItems]);

  return (
    <div className="border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-lg">Recent Actions</h2>
        <div className="flex items-center gap-2">
          {lastRefresh && (
            <span className="text-[10px] text-slate-500">
              {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={load}
            className="text-[10px] text-slate-400 hover:text-slate-200 px-2 py-0.5 rounded border border-slate-700 hover:border-slate-500"
          >
            ↺ Refresh
          </button>
        </div>
      </div>

      {/* Real-time status indicator */}
      <div className="flex items-center gap-2 text-[10px]">
        <div className="flex items-center gap-1 text-slate-400">
          <div className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[streamStatus]} ${streamStatus === "connected" ? "animate-pulse" : ""}`} />
          {STATUS_LABEL[streamStatus]}
        </div>
        {streamStatus === "connected" && subscriberCount > 0 && (
          <span className="text-slate-600">
            {subscriberCount} viewer{subscriberCount !== 1 ? "s" : ""}
          </span>
        )}
        {streamStatus !== "connected" && (
          <span className="text-slate-600">Polling every {AUTO_REFRESH_SEC}s</span>
        )}
      </div>

      {error && <p className="text-xs text-red-400">Error: {error}</p>}
      {loading && <p className="text-xs text-slate-400">Loading...</p>}

      <div className="space-y-2 max-h-96 overflow-auto text-xs">
        {items.map(item => (
          <div
            key={item.id}
            className={`border border-slate-700 rounded p-2 bg-slate-900/60 transition-all duration-300 ${item.id < 0 ? "ring-1 ring-emerald-500/20" : ""}`}
          >
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-1.5">
                {item.id < 0 && (
                  <span className="text-[8px] text-emerald-500 font-bold uppercase tracking-wider">LIVE</span>
                )}
                <span className="font-mono font-semibold text-slate-200">{item.tool}</span>
              </div>
              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${DECISION_STYLES[item.decision] || ""}`}>
                {item.decision}
              </span>
            </div>

            <div className="flex gap-3 mt-1">
              <span className={`font-semibold ${RISK_COLOR(item.risk_score)}`}>
                Risk: {item.risk_score}/100
              </span>
              {item.agent_id && (
                <span className="text-slate-500 truncate max-w-[120px]">
                  agent: {item.agent_id}
                </span>
              )}
              {item.conversation_id && (
                <span className="text-blue-400/70 truncate max-w-[160px]" title={item.conversation_id}>
                  💬 {item.conversation_id}
                </span>
              )}
            </div>

            {item.policy_ids.length > 0 && (
              <div className="mt-1 text-slate-400">
                Policies: {item.policy_ids.join(", ")}
              </div>
            )}

            <div className="mt-1 text-slate-400 leading-snug">{item.explanation}</div>

            <div className="mt-1 text-slate-600 text-[10px]">
              {new Date(item.created_at).toLocaleString()}
            </div>
          </div>
        ))}

        {!items.length && !loading && !error && (
          <p className="text-slate-500 text-center py-4">No actions logged yet.</p>
        )}
      </div>
    </div>
  );
};
