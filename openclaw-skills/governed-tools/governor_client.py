"""
governed-tools – OpenClaw skill
================================
Routes every tool invocation through the OpenClaw Governor service before
execution. The governor returns an allow/block/review decision; this skill
raises an error for blocked actions and logs review decisions.

Environment variables
---------------------
GOVERNOR_URL  – Base URL of the governor service (default: http://localhost:8000)
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

GOVERNOR_URL = os.getenv("GOVERNOR_URL", "http://localhost:8000")
_TIMEOUT = 10.0


class GovernorBlockedError(RuntimeError):
    """Raised when the governor blocks an action."""


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
    """
    payload = {"tool": tool, "args": args, "context": context}
    with httpx.Client(timeout=_TIMEOUT) as client:
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
