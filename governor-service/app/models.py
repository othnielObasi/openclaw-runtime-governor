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
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PolicyVersion(Base):
    """
    Immutable snapshot of a policy at a specific version.

    Every edit creates a new version entry preserving the full prior state.
    Enables restoring any previous version.
    """

    __tablename__ = "policy_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    policy_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[int] = mapped_column(Integer)
    match_json: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PolicyAuditLog(Base):
    """
    Server-side audit trail for every policy mutation.

    Every create, edit, archive, activate, delete, import, bulk action
    is recorded here with who did it, when, and what changed.
    """

    __tablename__ = "policy_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    # What happened
    action: Mapped[str] = mapped_column(String(32), index=True)
    # action: create | edit | archive | activate | delete | import | bulk_archive | bulk_activate | bulk_delete | toggle

    # Which policy
    policy_id: Mapped[str] = mapped_column(String(64), index=True)

    # Who did it
    username: Mapped[str] = mapped_column(String(256), index=True)
    user_role: Mapped[str] = mapped_column(String(32))

    # Change details (JSON): before/after snapshots for edits, or summary for bulk ops
    changes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Optional note
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class User(Base):
    """Operator / admin / auditor account with role-based access."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32), index=True)  # superadmin | admin | operator | auditor
    api_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    login_count: Mapped[int] = mapped_column(Integer, default=0)


class LoginHistory(Base):
    """Tracks every login event per user."""

    __tablename__ = "login_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[str] = mapped_column(String(256), index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    method: Mapped[str] = mapped_column(String(16), default="jwt")  # jwt | api_key
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


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


# ---------------------------------------------------------------------------
# SURGE Token Governance — DB-persisted models
# ---------------------------------------------------------------------------

class VerificationLog(Base):
    """Post-execution verification record — tracks compliance of actual tool results."""

    __tablename__ = "verification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Link to the original pre-execution evaluation
    action_id: Mapped[int] = mapped_column(Integer, index=True)

    # Tool and context
    tool: Mapped[str] = mapped_column(String(128), index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    # Result data (JSON)
    result_json: Mapped[str] = mapped_column(Text)

    # Verdict
    verdict: Mapped[str] = mapped_column(String(32), index=True)  # compliant | violation | suspicious
    risk_delta: Mapped[int] = mapped_column(Integer, default=0)
    findings_json: Mapped[str] = mapped_column(Text)  # JSON array of findings

    # Drift
    drift_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Escalation
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class SurgeReceipt(Base):
    """DB-persisted governance receipt — every evaluation is recorded for on-chain attestation."""

    __tablename__ = "surge_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    receipt_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    tool: Mapped[str] = mapped_column(String(128), index=True)
    decision: Mapped[str] = mapped_column(String(32))
    risk_score: Mapped[int] = mapped_column(Integer)
    policy_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # comma-separated
    chain_pattern: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    digest: Mapped[str] = mapped_column(String(64))
    governance_fee: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)


class SurgeStakedPolicy(Base):
    """A policy backed by $SURGE token stake — persisted in DB."""

    __tablename__ = "surge_staked_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    policy_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[int] = mapped_column(Integer)
    staked_surge: Mapped[str] = mapped_column(String(32))
    staker_wallet: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SurgeWallet(Base):
    """Virtual SURGE wallet balance per agent/org — enforced during evaluations.

    In production this would verify on-chain balances. For the hackathon demo
    we maintain a virtual ledger that gates /evaluate when empty.
    """

    __tablename__ = "surge_wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    wallet_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(256), default="")
    balance: Mapped[str] = mapped_column(String(32), default="100.0000")  # start with 100 SURGE
    total_deposited: Mapped[str] = mapped_column(String(32), default="100.0000")
    total_fees_paid: Mapped[str] = mapped_column(String(32), default="0.0000")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
