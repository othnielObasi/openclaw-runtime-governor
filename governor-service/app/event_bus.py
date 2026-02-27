"""
event_bus.py — In-memory pub/sub for real-time action events
=============================================================
When an action is evaluated, the evaluate route publishes an event here.
SSE listeners (connected via /actions/stream) receive the event instantly.

Uses asyncio.Queue per subscriber so each dashboard tab / client gets
its own independent stream. Subscribers are cleaned up on disconnect.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ActionEvent:
    """Lightweight event payload broadcast to all subscribers."""

    event_type: str  # "action_evaluated"
    tool: str
    decision: str
    risk_score: int
    explanation: str
    policy_ids: list[str]
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    channel: Optional[str] = None
    chain_pattern: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(
            {
                "event": self.event_type,
                "tool": self.tool,
                "decision": self.decision,
                "risk_score": self.risk_score,
                "explanation": self.explanation,
                "policy_ids": self.policy_ids,
                "agent_id": self.agent_id,
                "session_id": self.session_id,
                "user_id": self.user_id,
                "channel": self.channel,
                "chain_pattern": self.chain_pattern,
                "timestamp": self.timestamp,
            }
        )


class EventBus:
    """Simple broadcast pub/sub using per-subscriber asyncio queues."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[ActionEvent]] = set()

    def subscribe(self) -> asyncio.Queue[ActionEvent]:
        """Register a new subscriber. Returns the queue to read from."""
        q: asyncio.Queue[ActionEvent] = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[ActionEvent]) -> None:
        """Remove a subscriber (called on disconnect)."""
        self._subscribers.discard(q)

    def publish(self, event: ActionEvent) -> None:
        """Broadcast an event to all connected subscribers.

        Non-blocking: if a subscriber's queue is full the event is dropped
        (the client can catch up via the REST endpoint).
        """
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow consumer — drop rather than block

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Module-level singleton
action_bus = EventBus()
