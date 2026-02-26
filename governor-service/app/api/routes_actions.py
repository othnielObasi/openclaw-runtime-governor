from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from ..auth.dependencies import require_any, require_operator
from ..database import db_session
from ..models import ActionLog, User
from ..policies.engine import evaluate_action
from ..schemas import ActionInput, ActionDecision, ActionLogRead
from ..telemetry.logger import log_action
from .routes_surge import create_governance_receipt

router = APIRouter(prefix="/actions", tags=["actions"])


@router.post("/evaluate", response_model=ActionDecision)
def evaluate_action_route(
    action: ActionInput,
    _user: User = Depends(require_operator),
) -> ActionDecision:
    """Evaluate a tool call and return a governance decision.

    Requires operator or admin credentials (JWT or API key).
    Also generates a SURGE governance receipt for on-chain attestation.
    """
    decision = evaluate_action(action)
    log_action(action, decision)

    # Generate SURGE governance receipt
    ctx = action.context or {}
    create_governance_receipt(
        tool=action.tool,
        decision=decision.decision,
        risk_score=decision.risk_score,
        policy_ids=decision.policy_ids,
        chain_pattern=decision.chain_pattern,
        agent_id=ctx.get("agent_id"),
    )

    return decision


@router.get("", response_model=List[ActionLogRead])
def list_actions(
    limit: int = Query(50, ge=1, le=200),
    tool: str | None = Query(None, description="Filter by tool name"),
    decision: str | None = Query(None, description="Filter by decision (allow/block/review)"),
    agent_id: str | None = Query(None, description="Filter by agent_id"),
    _user: User = Depends(require_any),
) -> List[ActionLogRead]:
    """List recent governed actions with optional filters."""
    with db_session() as session:
        stmt = select(ActionLog).order_by(ActionLog.created_at.desc())
        if tool:
            stmt = stmt.where(ActionLog.tool == tool)
        if decision:
            stmt = stmt.where(ActionLog.decision == decision)
        if agent_id:
            stmt = stmt.where(ActionLog.agent_id == agent_id)
        stmt = stmt.limit(limit)

        rows = session.execute(stmt).scalars().all()
        return [
            ActionLogRead(
                id=r.id,
                created_at=r.created_at,
                tool=r.tool,
                decision=r.decision,
                risk_score=r.risk_score,
                explanation=r.explanation,
                policy_ids=[p for p in (r.policy_ids or "").split(",") if p],
                agent_id=r.agent_id,
                session_id=r.session_id,
                user_id=r.user_id,
                channel=r.channel,
            )
            for r in rows
        ]
