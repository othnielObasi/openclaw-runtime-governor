from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Action evaluation
# ---------------------------------------------------------------------------

class ActionInput(BaseModel):
    """Describes a tool invocation the agent wishes to make."""

    tool: str = Field(..., description="Name of the tool the agent wants to call.")
    args: Dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the tool.")
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional opaque context (e.g. user, session, agent_id, scopes, allowed_tools). "
            "Recognised keys: agent_id, session_id, user_id, channel, allowed_tools."
        ),
    )


class TraceStep(BaseModel):
    """One layer's record in the evaluation pipeline trace."""

    layer: int = Field(..., description="Layer index (1–5).")
    name: str  = Field(..., description="Human-readable layer name.")
    key: str   = Field(..., description="Machine key: kill | firewall | scope | policy | neuro.")
    outcome: str = Field(..., description="'pass' | 'block' | 'review'.")
    risk_contribution: int = Field(default=0, description="Risk points this layer added or confirmed.")
    matched_ids: List[str] = Field(default_factory=list, description="Policy IDs or pattern keys matched.")
    detail: Optional[str]  = Field(default=None, description="Human-readable detail for this layer.")
    duration_ms: float     = Field(default=0.0, description="Wall-clock time for this layer in milliseconds.")


class ActionDecision(BaseModel):
    """Governor's verdict on an ActionInput."""

    decision: str = Field(..., description="One of 'allow', 'block', or 'review'.")
    risk_score: int = Field(..., ge=0, le=100)
    explanation: str
    policy_ids: List[str] = Field(default_factory=list)
    modified_args: Optional[Dict[str, Any]] = None
    execution_trace: List[TraceStep] = Field(
        default_factory=list,
        description=(
            "Ordered trace of each evaluation layer: which fired, outcome, "
            "risk contribution, matched ids, and wall-clock duration. "
            "Layers that were not reached due to short-circuit are omitted."
        ),
    )
    # Chain analysis fields — populated when a behavioural pattern is detected
    chain_pattern: Optional[str] = Field(
        default=None,
        description="Machine name of the detected chain pattern, if any.",
    )
    chain_description: Optional[str] = Field(
        default=None,
        description="Human-readable description of the detected chain pattern.",
    )
    session_depth: int = Field(
        default=0,
        description="Number of prior actions in this agent's session history.",
    )


# ---------------------------------------------------------------------------
# Action log (read)
# ---------------------------------------------------------------------------

class ActionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    tool: str
    decision: str
    risk_score: int
    explanation: str
    policy_ids: List[str]
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    channel: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

class PolicyBase(BaseModel):
    policy_id: str = Field(..., description="Stable identifier for this policy.")
    description: str
    severity: int = Field(..., ge=0, le=100)


class PolicyCreate(PolicyBase):
    match_json: Dict[str, Any] = Field(default_factory=dict)
    action: str = Field(..., pattern="^(allow|block|review)$")


class PolicyUpdate(BaseModel):
    """Partial update — only supplied fields are changed."""
    description: Optional[str] = None
    severity: Optional[int] = Field(default=None, ge=0, le=100)
    match_json: Optional[Dict[str, Any]] = None
    action: Optional[str] = Field(default=None, pattern="^(allow|block|review)$")
    is_active: Optional[bool] = None


class PolicyRead(PolicyBase):
    model_config = ConfigDict(from_attributes=True)

    match_json: Dict[str, Any]
    action: str
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Summary / Moltbook
# ---------------------------------------------------------------------------

class SummaryOut(BaseModel):
    total_actions: int
    blocked: int
    allowed: int
    under_review: int
    avg_risk: float
    top_blocked_tool: Optional[str] = None
    high_risk_count: int = 0
    message: str


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class GovernorStatus(BaseModel):
    kill_switch: bool = Field(..., description="If true, all actions will be blocked.")


# ---------------------------------------------------------------------------
# Traces — Agent lifecycle observability
# ---------------------------------------------------------------------------

class SpanCreate(BaseModel):
    """One span in an agent trace (ingested from SDK / agent framework)."""
    trace_id: str = Field(..., min_length=1, max_length=128, description="Groups all spans of one agent task.")
    span_id: str = Field(..., min_length=1, max_length=128, description="Unique identifier for this span.")
    parent_span_id: Optional[str] = Field(default=None, max_length=128, description="Parent span for nesting.")
    kind: str = Field(..., pattern="^(agent|llm|tool|governance|retrieval|chain|custom)$")
    name: str = Field(..., min_length=1, max_length=256)
    status: str = Field(default="ok", pattern="^(ok|error)$")
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    agent_id: Optional[str] = Field(default=None, max_length=128)
    session_id: Optional[str] = Field(default=None, max_length=128)
    attributes: Optional[Dict[str, Any]] = Field(default=None, description="Flexible metadata (model, tokens, cost, etc.)")
    input: Optional[str] = Field(default=None, description="LLM prompt / tool args.")
    output: Optional[str] = Field(default=None, description="LLM response / tool result.")
    events: Optional[List[Dict[str, Any]]] = Field(default=None, description="Timestamped sub-events within the span.")


class SpanBatchCreate(BaseModel):
    """Batch ingest multiple spans."""
    spans: List[SpanCreate] = Field(..., min_length=1, max_length=500)


class SpanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    kind: str
    name: str
    status: str = "ok"
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    input: Optional[str] = None
    output: Optional[str] = None
    events: Optional[List[Dict[str, Any]]] = None
    created_at: datetime


class TraceListItem(BaseModel):
    """Summary of a trace for listing."""
    trace_id: str
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    span_count: int
    governance_count: int = 0
    root_span_name: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    total_duration_ms: Optional[float] = None
    has_errors: bool = False
    has_blocks: bool = False


class TraceDetail(BaseModel):
    """Full trace with all spans and correlated governance decisions."""
    trace_id: str
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    spans: List[SpanRead]
    governance_decisions: List[ActionLogRead] = Field(default_factory=list)
    span_count: int
    governance_count: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_duration_ms: Optional[float] = None
    has_errors: bool = False
    has_blocks: bool = False
