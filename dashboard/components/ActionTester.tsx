"use client";

import React, { useState } from "react";
import { api } from "./ApiClient";

interface Decision {
  decision: string;
  risk_score: number;
  explanation: string;
  policy_ids: string[];
}

export const ActionTester: React.FC = () => {
  const [tool, setTool] = useState("http_request");
  const [args, setArgs] = useState('{"url": "http://localhost"}');
  const [context, setContext] = useState("{}");
  const [result, setResult] = useState<Decision | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async () => {
    setError(null);
    setResult(null);
    try {
      const payload = {
        tool,
        args: JSON.parse(args || "{}"),
        context: context ? JSON.parse(context) : null
      };
      const res = await api.post<Decision>("/actions/evaluate", payload);
      setResult(res.data);
    } catch (e: any) {
      setError(e?.message || "Request failed");
    }
  };

  return (
    <div className="border border-slate-800 rounded-xl p-4 space-y-3">
      <h2 className="font-semibold text-lg">Action Tester</h2>
      <div className="space-y-2">
        <label className="text-sm">Tool</label>
        <input
          className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-sm"
          value={tool}
          onChange={e => setTool(e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <label className="text-sm">Args (JSON)</label>
        <textarea
          className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-sm h-20"
          value={args}
          onChange={e => setArgs(e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <label className="text-sm">Context (JSON, optional)</label>
        <textarea
          className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-sm h-16"
          value={context}
          onChange={e => setContext(e.target.value)}
        />
      </div>
      <button
        onClick={onSubmit}
        className="px-3 py-1 rounded bg-emerald-500 text-sm font-semibold text-slate-950 hover:bg-emerald-400"
      >
        Evaluate
      </button>
      {error && <p className="text-xs text-red-400 mt-2">Error: {error}</p>}
      {result && (
        <div className="mt-3 text-xs space-y-1 bg-slate-900 border border-slate-700 rounded p-2">
          <div>
            <span className="font-semibold">Decision:</span> {result.decision}
          </div>
          <div>
            <span className="font-semibold">Risk:</span> {result.risk_score}
          </div>
          <div>
            <span className="font-semibold">Policies:</span>{" "}
            {result.policy_ids.length ? result.policy_ids.join(", ") : "None"}
          </div>
          <div>
            <span className="font-semibold">Explanation:</span> {result.explanation}
          </div>
        </div>
      )}
    </div>
  );
};
