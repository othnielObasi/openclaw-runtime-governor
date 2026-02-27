from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Integer, String, DateTime, Text, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ActionLog(Base):
    """Persisted record of every evaluated action."""

    __tablename__ = "action_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Tool call
    tool: Mapped[str] = mapped_column(String(128), index=True)
    args: Mapped[str] = mapped_column(Text)          # JSON
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # Context metadata (extracted from context for easy filtering)
    agent_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    channel: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # Trace correlation (links audit log entries to agent traces)
    trace_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    span_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Decision
    decision: Mapped[str] = mapped_column(String(32), index=True)
    risk_score: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    policy_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # comma-separated


class PolicyModel(Base):
    """Dynamically managed policy stored in DB (supplements base_policies.yml)."""

    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    policy_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[int] = mapped_column(Integer)
    match_json: Mapped[str] = mapped_column(Text)    # JSON
    action: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class User(Base):
    """Operator / admin / auditor account with role-based access."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32), index=True)  # admin | operator | auditor
    api_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class TraceSpan(Base):
    """One span in an agent trace — stores reasoning, LLM calls, tool selections, governance decisions."""

    __tablename__ = "trace_spans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    span_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    parent_span_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # agent | llm | tool | governance | retrieval | chain | custom
    name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | error
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Flexible metadata
    attributes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON dict
    input_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # LLM prompt / tool args
    output_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # LLM response / tool result
    events_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # JSON list of {time, name, attrs}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class GovernorState(Base):
    """Persistent key-value store for governor runtime state (e.g. kill switch).

    Survives restarts and works correctly across multiple instances.
    """

    __tablename__ = "governor_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
