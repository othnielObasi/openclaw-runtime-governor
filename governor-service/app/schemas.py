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


class PolicyRead(PolicyBase):
    model_config = ConfigDict(from_attributes=True)

    match_json: Dict[str, Any]
    action: str


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
