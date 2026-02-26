"""
session_store.py — Persistent session history for chain analysis
================================================================
Queries the existing action_logs table to reconstruct an agent's
recent behaviour. No new table or Redis required — the audit log
IS the session store.

Sandboxing: history is scoped by agent_id. If a session_id is
also provided, history is further scoped to that session only,
ensuring complete isolation between concurrent agent sessions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select

from .database import db_session
from .models import ActionLog

# How far back to look when reconstructing session history
SESSION_WINDOW_MINUTES = 60
# Maximum number of recent actions to return (performance cap)
MAX_HISTORY = 50


@dataclass
class HistoryEntry:
    """Lightweight record of one past action — enough for chain analysis."""
    tool: str
    decision: str
    policy_ids: List[str]
    ts: datetime
    session_id: Optional[str]


def get_agent_history(
    agent_id: str,
    session_id: Optional[str] = None,
) -> List[HistoryEntry]:
    """
    Return recent action history for an agent, scoped to the session
    window. If session_id is provided, only actions from that session
    are returned — full sandbox isolation.

    Called by the evaluation engine before Layer 5 runs.
    """
    if not agent_id:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_WINDOW_MINUTES)
    # SQLite stores naive UTC datetimes; strip tzinfo for comparison
    cutoff_naive = cutoff.replace(tzinfo=None)

    with db_session() as session:
        stmt = (
            select(ActionLog)
            .where(ActionLog.agent_id == agent_id)
            .where(ActionLog.created_at >= cutoff_naive)
            .order_by(ActionLog.created_at.asc())
            .limit(MAX_HISTORY)
        )

        # Sandbox: if session_id given, restrict to that session only
        if session_id:
            stmt = stmt.where(ActionLog.session_id == session_id)

        rows = session.execute(stmt).scalars().all()

    return [
        HistoryEntry(
            tool=row.tool,
            decision=row.decision,
            policy_ids=[p for p in (row.policy_ids or "").split(",") if p],
            ts=row.created_at,
            session_id=row.session_id,
        )
        for row in rows
    ]
