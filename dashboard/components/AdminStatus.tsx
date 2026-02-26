"use client";

import React, { useEffect, useState } from "react";
import { api } from "./ApiClient";

interface Status {
  kill_switch: boolean;
}

export const AdminStatus: React.FC = () => {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    api
      .get<Status>("/admin/status")
      .then(res => setStatus(res.data))
      .catch(e => setError(e?.message || "Failed to load status"));
  };

  useEffect(() => {
    load();
  }, []);

  const setKill = async (enabled: boolean) => {
    try {
      const path = enabled ? "/admin/kill" : "/admin/resume";
      const res = await api.post<Status>(path);
      setStatus(res.data);
    } catch (e: any) {
      setError(e?.message || "Failed to update kill switch");
    }
  };

  return (
    <div className="border border-slate-800 rounded-xl p-4 space-y-3">
      <h2 className="font-semibold text-lg">Runtime Control</h2>
      {error && <p className="text-xs text-red-400">Error: {error}</p>}
      <div className="flex items-center justify-between text-sm">
        <div>
          Kill switch:{" "}
          <span
            className={
              "font-semibold " +
              (status?.kill_switch ? "text-red-300" : "text-emerald-300")
            }
          >
            {status?.kill_switch ? "ENABLED" : "DISABLED"}
          </span>
        </div>
        <div className="space-x-2">
          <button
            onClick={() => setKill(true)}
            className="px-3 py-1 rounded bg-red-500/80 text-xs font-semibold text-slate-950 hover:bg-red-400"
          >
            Enable
          </button>
          <button
            onClick={() => setKill(false)}
            className="px-3 py-1 rounded bg-slate-700 text-xs font-semibold hover:bg-slate-600"
          >
            Resume
          </button>
        </div>
      </div>
    </div>
  );
};
