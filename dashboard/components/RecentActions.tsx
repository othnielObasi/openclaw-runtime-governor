"use client";

import React, { useEffect, useState, useCallback } from "react";
import { api } from "./ApiClient";

interface ActionLog {
  id: number;
  created_at: string;
  tool: string;
  decision: string;
  risk_score: number;
  explanation: string;
  policy_ids: string[];
  agent_id?: string;
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

export const RecentActions: React.FC = () => {
  const [items, setItems] = useState<ActionLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const AUTO_REFRESH_SEC = 30;

  const load = useCallback(() => {
    api
      .get<ActionLog[]>("/actions", { params: { limit: 20 } })
      .then(res => {
        setItems(res.data);
        setError(null);
        setLastRefresh(new Date());
      })
      .catch(e => setError(e?.message || "Failed to load actions"))
      .finally(() => setLoading(false));
  }, []);

  // Initial load + auto-refresh every 30 seconds
  useEffect(() => {
    load();
    const interval = setInterval(load, AUTO_REFRESH_SEC * 1000);
    return () => clearInterval(interval);
  }, [load]);

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

      <div className="flex items-center gap-1 text-[10px] text-slate-500">
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        Auto-refreshes every {AUTO_REFRESH_SEC}s
      </div>

      {error && <p className="text-xs text-red-400">Error: {error}</p>}
      {loading && <p className="text-xs text-slate-400">Loading...</p>}

      <div className="space-y-2 max-h-96 overflow-auto text-xs">
        {items.map(item => (
          <div
            key={item.id}
            className="border border-slate-700 rounded p-2 bg-slate-900/60"
          >
            <div className="flex justify-between items-center">
              <span className="font-mono font-semibold text-slate-200">{item.tool}</span>
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
