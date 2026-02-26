"""
chain_analysis.py — Persistent behavioural chain escalation
============================================================
Detects multi-step attack patterns across an agent's session history.
Operates on HistoryEntry records from session_store, not React state —
so context survives page reloads, server restarts (via DB), and
persists across a real agent's multi-hour session.

Sandbox guarantee: the history passed in is already scoped per
agent_id + session_id by session_store.get_agent_history(), so
no cross-contamination between concurrent agent sessions is possible.

Each chain pattern defines:
  name        — machine identifier surfaced in traces and alerts
  description — human-readable explanation shown in the dashboard
  match()     — function that inspects the history list
  boost       — risk score increase when triggered (0-100)
  min_actions — minimum history length before this pattern can fire
                (prevents false positives on fresh sessions)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from .session_store import HistoryEntry


@dataclass
class ChainResult:
    triggered: bool
    pattern: Optional[str] = None
    description: Optional[str] = None
    boost: int = 0
    evidence: Optional[str] = None   # human-readable evidence string for trace


@dataclass
class ChainPattern:
    name: str
    description: str
    match: Callable[[List[HistoryEntry]], bool]
    boost: int
    min_actions: int = 2


# ---------------------------------------------------------------------------
# Pattern definitions — mirror of the dashboard JS patterns but running
# against real persistent DB history rather than React state
# ---------------------------------------------------------------------------

def _recent_tools(history: List[HistoryEntry], n: int = 6) -> List[str]:
    return [h.tool for h in history[-n:]]


def _recent_policies(history: List[HistoryEntry], n: int = 10) -> List[str]:
    """Flatten all policy_ids from recent actions into a single list."""
    policies = []
    for h in history[-n:]:
        policies.extend(h.policy_ids)
    return policies


CHAIN_PATTERNS: List[ChainPattern] = [
    ChainPattern(
        name="browse-then-exfil",
        description="External HTTP browsing followed by outbound messaging — possible data exfiltration chain",
        match=lambda h: (
            "http_request" in _recent_tools(h) and
            "messaging_send" in _recent_tools(h)
        ),
        boost=35,
        min_actions=2,
    ),
    ChainPattern(
        name="read-write-exec",
        description="File read → file write → shell execution — classic lateral movement pattern",
        match=lambda h: (
            "file_read" in _recent_tools(h, 6) and
            "file_write" in _recent_tools(h, 6) and
            "shell" in _recent_tools(h, 6)
        ),
        boost=45,
        min_actions=3,
    ),
    ChainPattern(
        name="repeated-scope-probing",
        description="Multiple scope violations in this session — agent is probing permission boundaries",
        match=lambda h: sum(
            1 for entry in h if "scope-violation" in entry.policy_ids
        ) >= 2,
        boost=60,
        min_actions=2,
    ),
    ChainPattern(
        name="credential-then-http",
        description="Credential access followed by external HTTP — possible exfiltration in progress",
        match=lambda h: (
            any("credential-exfil" in p for p in _recent_policies(h, 4)) and
            "http_request" in _recent_tools(h, 4)
        ),
        boost=55,
        min_actions=2,
    ),
    ChainPattern(
        name="rapid-tool-switching",
        description="Agent switching between high-risk tool categories rapidly — automated attack pattern",
        match=lambda h: (
            len(set(_recent_tools(h, 5)) &
                {"shell", "file_write", "http_request", "messaging_send"}) >= 3
        ),
        boost=30,
        min_actions=3,
    ),
    ChainPattern(
        name="block-bypass-retry",
        description="Agent retrying previously blocked tools — attempting to find unguarded execution path",
        match=lambda h: any(
            entry.decision == "block" and
            any(other.tool == entry.tool and other.ts > entry.ts
                for other in h)
            for entry in h[-10:]
        ),
        boost=40,
        min_actions=2,
    ),
]


def check_chain_escalation(history: List[HistoryEntry]) -> ChainResult:
    """
    Evaluate all chain patterns against the agent's session history.
    Returns the first (highest boost) triggered pattern, or a
    ChainResult(triggered=False) if none match.

    Called by engine.py Layer 5 after retrieving history from
    session_store.get_agent_history().
    """
    if not history:
        return ChainResult(triggered=False)

    # Evaluate patterns in descending boost order so the most severe fires
    for pattern in sorted(CHAIN_PATTERNS, key=lambda p: p.boost, reverse=True):
        if len(history) < pattern.min_actions:
            continue
        try:
            if pattern.match(history):
                recent = [h.tool for h in history[-5:]]
                evidence = (
                    f"Last {min(5, len(history))} tools: {' → '.join(recent)}. "
                    f"Session depth: {len(history)} actions."
                )
                return ChainResult(
                    triggered=True,
                    pattern=pattern.name,
                    description=pattern.description,
                    boost=pattern.boost,
                    evidence=evidence,
                )
        except Exception:
            # Never let a chain pattern crash the evaluation
            continue

    return ChainResult(triggered=False)
