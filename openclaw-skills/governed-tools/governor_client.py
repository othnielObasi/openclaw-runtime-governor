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
import time
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


class GovernorReviewRejectedError(RuntimeError):
    """Raised when a review decision is rejected by a human operator."""


class GovernorReviewExpiredError(RuntimeError):
    """Raised when a review decision times out (hold mode only)."""


# ---------------------------------------------------------------------------
# Action evaluation
# ---------------------------------------------------------------------------

def evaluate_action(
    tool: str,
    args: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    *,
    review_mode: str = "proceed",
    hold_timeout: int = 60,
    hold_poll_interval: float = 1.0,
) -> Dict[str, Any]:
    """
    Send a tool-call to the governor for evaluation.

    Returns the full decision dict:
      { decision, risk_score, explanation, policy_ids, modified_args }

    Raises GovernorBlockedError if decision == "block".

    review_mode:
      - "proceed" (default): Return the result immediately for 'review'
        decisions. Callers should inspect decision and handle accordingly.
      - "hold": If decision is 'review', long-poll the hold endpoint until
        a human operator approves/rejects, or the timeout expires.
        Raises GovernorReviewRejectedError if rejected.
        Raises GovernorReviewExpiredError if timed out or expired.

    hold_timeout: Max seconds to wait in hold mode (1-300, default: 60).
    hold_poll_interval: Seconds between server-side polls (default: 1.0).

    Tip: include ``trace_id`` and ``span_id`` in *context* to auto-create a
    governance span in the agent's trace tree.
    """
    if review_mode not in ("proceed", "hold"):
        raise ValueError(f"review_mode must be 'proceed' or 'hold', got '{review_mode}'")

    payload = {"tool": tool, "args": args, "context": context}
    with httpx.Client(timeout=_TIMEOUT, headers=_headers()) as client:
        resp = client.post(f"{GOVERNOR_URL}/actions/evaluate", json=payload)
        resp.raise_for_status()

    result = resp.json()

    if result.get("decision") == "block":
        raise GovernorBlockedError(
            f"Governor blocked tool '{tool}': {result.get('explanation', 'no reason given')}"
        )

    # Handle review decisions
    if result.get("decision") == "review" and review_mode == "hold":
        escalation_id = result.get("escalation_id")
        if escalation_id:
            hold_result = _hold_for_review(
                escalation_id,
                timeout_seconds=hold_timeout,
                poll_interval=hold_poll_interval,
            )
            result["review_status"] = hold_result.get("status", "unknown")
            result["review_resolved_by"] = hold_result.get("resolved_by")
            result["review_resolution_note"] = hold_result.get("resolution_note")

            if hold_result.get("timed_out"):
                raise GovernorReviewExpiredError(
                    f"Review for tool '{tool}' timed out after {hold_timeout}s "
                    f"(escalation_id={escalation_id})"
                )
            if hold_result.get("status") == "rejected":
                raise GovernorReviewRejectedError(
                    f"Review for tool '{tool}' was rejected: "
                    f"{hold_result.get('resolution_note', 'no reason given')} "
                    f"(escalation_id={escalation_id})"
                )
            if hold_result.get("status") == "expired":
                raise GovernorReviewExpiredError(
                    f"Review for tool '{tool}' expired before resolution "
                    f"(escalation_id={escalation_id})"
                )
            # approved or auto_resolved → continue

    return result


def _hold_for_review(
    escalation_id: int,
    timeout_seconds: int = 60,
    poll_interval: float = 1.0,
) -> Dict[str, Any]:
    """
    Call the hold endpoint to long-poll for review resolution.
    Returns the hold result dict from the server.
    """
    params = {
        "timeout_seconds": timeout_seconds,
        "poll_interval": poll_interval,
    }
    # Use a longer client timeout than the hold timeout to avoid premature disconnects
    client_timeout = timeout_seconds + 10
    try:
        with httpx.Client(timeout=client_timeout, headers=_headers()) as client:
            resp = client.post(
                f"{GOVERNOR_URL}/escalation/queue/{escalation_id}/hold",
                params=params,
            )
            resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException:
        return {"event_id": escalation_id, "status": "pending", "timed_out": True}
    except Exception:
        # If the hold endpoint is unavailable, fall through gracefully
        return {"event_id": escalation_id, "status": "pending", "timed_out": True}


def governed_call(
    tool: str,
    args: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    *,
    review_mode: str = "proceed",
    hold_timeout: int = 60,
) -> Dict[str, Any]:
    """
    Convenience wrapper: evaluate then return the decision.

    review_mode:
      - "proceed": Return immediately (caller handles 'review' decisions).
      - "hold": Wait for human resolution on 'review' decisions.
        Raises GovernorReviewRejectedError / GovernorReviewExpiredError.
    """
    return evaluate_action(
        tool, args, context,
        review_mode=review_mode,
        hold_timeout=hold_timeout,
    )


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
