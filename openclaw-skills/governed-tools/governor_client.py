"""
governed-tools – OpenClaw skill
================================
Routes every tool invocation through the OpenClaw Governor service before
execution. The governor returns an allow/block/review decision; this skill
raises an error for blocked actions and logs review decisions.

Also provides trace observability: ingest agent trace spans, query traces,
and correlate governance decisions with the agent's execution timeline.

Environment variables
---------------------
GOVERNOR_URL      – Base URL of the governor service (default: http://localhost:8000)
GOVERNOR_API_KEY  – API key for authentication (ocg_… format, sent as X-API-Key header)
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

GOVERNOR_URL = os.getenv("GOVERNOR_URL", "http://localhost:8000")
GOVERNOR_API_KEY = os.getenv("GOVERNOR_API_KEY", "")
_TIMEOUT = 10.0


def _headers() -> Dict[str, str]:
    """Build request headers, including X-API-Key when configured."""
    h: Dict[str, str] = {"Content-Type": "application/json"}
    key = GOVERNOR_API_KEY
    if key:
        h["X-API-Key"] = key
    return h


class GovernorBlockedError(RuntimeError):
    """Raised when the governor blocks an action."""


# ---------------------------------------------------------------------------
# Action evaluation
# ---------------------------------------------------------------------------

def evaluate_action(
    tool: str,
    args: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send a tool-call to the governor for evaluation.

    Returns the full decision dict:
      { decision, risk_score, explanation, policy_ids, modified_args }

    Raises GovernorBlockedError if decision == "block".

    Tip: include ``trace_id`` and ``span_id`` in *context* to auto-create a
    governance span in the agent's trace tree.
    """
    payload = {"tool": tool, "args": args, "context": context}
    with httpx.Client(timeout=_TIMEOUT, headers=_headers()) as client:
        resp = client.post(f"{GOVERNOR_URL}/actions/evaluate", json=payload)
        resp.raise_for_status()

    result = resp.json()

    if result.get("decision") == "block":
        raise GovernorBlockedError(
            f"Governor blocked tool '{tool}': {result.get('explanation', 'no reason given')}"
        )

    return result


def governed_call(
    tool: str,
    args: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convenience wrapper: evaluate then return the decision.
    Callers should inspect `decision` for 'review' and handle accordingly.
    """
    return evaluate_action(tool, args, context)


# ---------------------------------------------------------------------------
# Trace observability
# ---------------------------------------------------------------------------

def ingest_spans(spans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Batch-ingest agent trace spans.

    Each span dict should contain at minimum:
      trace_id, span_id, kind, name, start_time

    Optional fields: parent_span_id, status, end_time, duration_ms,
    agent_id, session_id, attributes, input, output, events.

    Valid span kinds: agent, llm, tool, governance, retrieval, chain, custom.

    Returns ``{"inserted": N, "skipped": M}`` — duplicates are silently
    skipped (idempotent).
    """
    payload = {"spans": spans}
    with httpx.Client(timeout=_TIMEOUT, headers=_headers()) as client:
        resp = client.post(f"{GOVERNOR_URL}/traces/ingest", json=payload)
        resp.raise_for_status()
    return resp.json()


def list_traces(
    *,
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    has_blocks: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    List traces with optional filters.

    Returns a list of trace summaries with span_count, governance_count,
    root_span_name, has_errors, has_blocks, etc.
    """
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if agent_id is not None:
        params["agent_id"] = agent_id
    if session_id is not None:
        params["session_id"] = session_id
    if has_blocks is not None:
        params["has_blocks"] = str(has_blocks).lower()
    with httpx.Client(timeout=_TIMEOUT, headers=_headers()) as client:
        resp = client.get(f"{GOVERNOR_URL}/traces", params=params)
        resp.raise_for_status()
    return resp.json()


def get_trace(trace_id: str) -> Dict[str, Any]:
    """
    Fetch full trace detail — all spans plus correlated governance decisions.

    Returns a dict with spans, governance_decisions, span_count,
    governance_count, total_duration_ms, has_errors, has_blocks.
    """
    with httpx.Client(timeout=_TIMEOUT, headers=_headers()) as client:
        resp = client.get(f"{GOVERNOR_URL}/traces/{trace_id}")
        resp.raise_for_status()
    return resp.json()


def delete_trace(trace_id: str) -> Dict[str, Any]:
    """
    Delete all spans for a trace (action log entries are preserved).

    Returns ``{"trace_id": "…", "spans_deleted": N}``.
    """
    with httpx.Client(timeout=_TIMEOUT, headers=_headers()) as client:
        resp = client.delete(f"{GOVERNOR_URL}/traces/{trace_id}")
        resp.raise_for_status()
    return resp.json()
