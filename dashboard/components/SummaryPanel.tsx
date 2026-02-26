"use client";

import React, { useEffect, useState, useCallback } from "react";
import { api } from "./ApiClient";

interface Summary {
  total_actions: number;
  blocked: number;
  allowed: number;
  under_review: number;
  avg_risk: number;
  top_blocked_tool?: string;
  high_risk_count?: number;
  message: string;
}

const Stat: React.FC<{ label: string; value: string | number; colour?: string }> = ({
  label, value, colour = "text-slate-100",
}) => (
  <div className="text-center">
    <div className={`text-2xl font-bold tabular-nums ${colour}`}>{value}</div>
    <div className="text-[10px] text-slate-400 mt-0.5">{label}</div>
  </div>
);

export const SummaryPanel: React.FC = () => {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const load = useCallback(() => {
    api
      .get<Summary>("/summary/moltbook")
      .then(res => {
        setSummary(res.data);
        setError(null);
        setLastRefresh(new Date());
      })
      .catch(e => setError(e?.message || "Failed to load summary"));
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, [load]);

  const blockPct = summary && summary.total_actions > 0
    ? Math.round((summary.blocked / summary.total_actions) * 100)
    : 0;

  const riskColour = summary
    ? summary.avg_risk >= 70 ? "text-red-400"
    : summary.avg_risk >= 40 ? "text-amber-400"
    : "text-emerald-400"
    : "text-slate-100";

  return (
    <div className="border border-slate-800 rounded-xl p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-lg">Governance Summary</h2>
        <div className="flex items-center gap-2">
          {lastRefresh && (
            <span className="text-[10px] text-slate-500">{lastRefresh.toLocaleTimeString()}</span>
          )}
          <button
            onClick={load}
            className="text-[10px] text-slate-400 hover:text-slate-200 px-2 py-0.5 rounded border border-slate-700"
          >
            ↺
          </button>
        </div>
      </div>

      {error && <p className="text-xs text-red-400">Error: {error}</p>}

      {summary && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Total Evaluated" value={summary.total_actions.toLocaleString()} />
            <Stat
              label={`Blocked (${blockPct}%)`}
              value={summary.blocked.toLocaleString()}
              colour="text-red-400"
            />
            <Stat
              label="Under Review"
              value={summary.under_review.toLocaleString()}
              colour="text-amber-400"
            />
            <Stat
              label="Avg Risk Score"
              value={`${summary.avg_risk.toFixed(1)}/100`}
              colour={riskColour}
            />
          </div>

          {(summary.top_blocked_tool || summary.high_risk_count !== undefined) && (
            <div className="flex flex-wrap gap-3 text-xs text-slate-400">
              {summary.top_blocked_tool && (
                <span>
                  ⛔ Most blocked tool:{" "}
                  <span className="font-mono text-slate-200">{summary.top_blocked_tool}</span>
                </span>
              )}
              {summary.high_risk_count !== undefined && (
                <span>
                  ⚠️ High-risk actions (≥80):{" "}
                  <span className="text-red-300 font-semibold">{summary.high_risk_count}</span>
                </span>
              )}
            </div>
          )}

          <p className="text-[11px] text-slate-400 border-t border-slate-800 pt-2 leading-relaxed">
            {summary.message}
          </p>
        </>
      )}

      {!summary && !error && (
        <p className="text-xs text-slate-500 text-center py-4">Loading summary...</p>
      )}
    </div>
  );
};
