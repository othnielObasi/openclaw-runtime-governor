"use client";

import React, { useEffect, useState } from "react";
import { api } from "./ApiClient";

interface Policy {
  policy_id: string;
  description: string;
  severity: number;
  match_json: any;
  action: string;
}

export const PolicyEditor: React.FC = () => {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [policyId, setPolicyId] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState(50);
  const [matchJson, setMatchJson] = useState('{"tool": "shell"}');
  const [action, setAction] = useState<"allow" | "block" | "review">("review");
  const [error, setError] = useState<string | null>(null);

  const loadPolicies = () => {
    api
      .get<Policy[]>("/policies")
      .then(res => setPolicies(res.data))
      .catch(e => setError(e?.message || "Failed to load policies"));
  };

  useEffect(() => {
    loadPolicies();
  }, []);

  const onCreate = async () => {
    setError(null);
    try {
      const payload = {
        policy_id: policyId,
        description,
        severity,
        match_json: JSON.parse(matchJson || "{}"),
        action
      };
      await api.post("/policies", payload);
      setPolicyId("");
      setDescription("");
      setMatchJson("{}");
      setSeverity(50);
      setAction("review");
      loadPolicies();
    } catch (e: any) {
      setError(e?.message || "Failed to create policy");
    }
  };

  const onDelete = async (id: string) => {
    await api.delete(`/policies/${id}`);
    loadPolicies();
  };

  return (
    <div className="border border-slate-800 rounded-xl p-4 space-y-3">
      <h2 className="font-semibold text-lg">Policy Editor</h2>
      {error && <p className="text-xs text-red-400">Error: {error}</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
        <div className="space-y-2">
          <div>
            <label className="text-xs">Policy ID</label>
            <input
              className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-xs"
              value={policyId}
              onChange={e => setPolicyId(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs">Description</label>
            <input
              className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-xs"
              value={description}
              onChange={e => setDescription(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs">Severity ({severity})</label>
            <input
              type="range"
              min={0}
              max={100}
              value={severity}
              onChange={e => setSeverity(parseInt(e.target.value, 10))}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-xs">Action</label>
            <select
              className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-xs"
              value={action}
              onChange={e => setAction(e.target.value as any)}
            >
              <option value="allow">allow</option>
              <option value="block">block</option>
              <option value="review">review</option>
            </select>
          </div>
          <div>
            <label className="text-xs">Match JSON</label>
            <textarea
              className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-xs h-24"
              value={matchJson}
              onChange={e => setMatchJson(e.target.value)}
            />
          </div>
          <button
            onClick={onCreate}
            className="px-3 py-1 rounded bg-emerald-500 text-xs font-semibold text-slate-950 hover:bg-emerald-400"
          >
            Create Policy
          </button>
        </div>
        <div className="space-y-2 max-h-80 overflow-auto text-xs">
          {policies.map(p => (
            <div
              key={p.policy_id}
              className="border border-slate-700 rounded p-2 bg-slate-900"
            >
              <div className="flex justify-between items-center">
                <span className="font-semibold">{p.policy_id}</span>
                <span className="text-[10px] uppercase">{p.action}</span>
              </div>
              <div>{p.description}</div>
              <div>Severity: {p.severity}</div>
              <div className="mt-1">
                <span className="font-semibold">Match:</span>{" "}
                <pre className="whitespace-pre-wrap">
                  {JSON.stringify(p.match_json, null, 2)}
                </pre>
              </div>
              <button
                onClick={() => onDelete(p.policy_id)}
                className="mt-1 text-[10px] text-red-300 hover:text-red-200"
              >
                Delete
              </button>
            </div>
          ))}
          {!policies.length && <p className="text-slate-400">No dynamic policies yet.</p>}
        </div>
      </div>
    </div>
  );
};
