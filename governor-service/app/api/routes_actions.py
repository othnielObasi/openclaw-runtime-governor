from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from ..auth.dependencies import require_any, require_operator
from ..database import db_session
from ..escalation.engine import handle_post_evaluation
from ..event_bus import ActionEvent, action_bus
from ..models import ActionLog, TraceSpan, User
from ..policies.engine import evaluate_action
from ..schemas import ActionInput, ActionDecision, ActionLogRead
from ..telemetry.logger import log_action
from .routes_surge import create_governance_receipt, check_wallet_balance

router = APIRouter(prefix="/actions", tags=["actions"])


def _create_governance_span(
    action: ActionInput, decision: ActionDecision, eval_start: datetime,
) -> None:
    """Auto-create a 'governance' trace span when trace_id is in context.

    This links the Governor's evaluation into the agent's trace tree so
    GET /traces/{trace_id} shows governance decisions inline with the
    agent's own reasoning and tool-call spans.
    """
    ctx = action.context or {}
    trace_id = ctx.get("trace_id")
    if not trace_id:
        return

    now = datetime.now(timezone.utc)
    dur = (now - eval_start).total_seconds() * 1000

    # Build a descriptive attributes payload
    attrs = {
        "governor.decision": decision.decision,
        "governor.risk_score": decision.risk_score,
        "governor.policy_ids": decision.policy_ids,
        "governor.tool": action.tool,
    }
    if decision.chain_pattern:
        attrs["governor.chain_pattern"] = decision.chain_pattern
    trace_steps = [
        {"layer": s.layer, "name": s.name, "outcome": s.outcome,
         "risk": s.risk_contribution, "matched": s.matched_ids,
         "duration_ms": s.duration_ms}
        for s in decision.execution_trace
    ]
    attrs["governor.trace"] = trace_steps

    span_id = f"gov-{secrets.token_hex(12)}"

    with db_session() as session:
        row = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=ctx.get("span_id"),   # nest under calling span if provided
            kind="governance",
            name=f"governor.evaluate({action.tool})",
            status="ok",
            start_time=eval_start,
            end_time=now,
            duration_ms=round(dur, 2),
            agent_id=ctx.get("agent_id"),
            session_id=ctx.get("session_id"),
            attributes_json=json.dumps(attrs),
            input_text=json.dumps({"tool": action.tool, "args": action.args}),
            output_text=json.dumps({
                "decision": decision.decision,
                "risk_score": decision.risk_score,
                "explanation": decision.explanation,
            }),
        )
        session.add(row)


@router.post("/evaluate", response_model=ActionDecision)
def evaluate_action_route(
    action: ActionInput,
    _user: User = Depends(require_operator),
) -> ActionDecision:
    """Evaluate a tool call and return a governance decision.

    Requires operator or admin credentials (JWT or API key).
    Also generates a SURGE governance receipt for on-chain attestation.
    When trace_id is present in context, a 'governance' span is auto-created
    in the trace for full agent lifecycle visibility.

    If SURGE fee gating is enabled, the agent's wallet balance is checked
    before evaluation. Returns 402 Payment Required if balance ≤ 0.
    """
    # Check SURGE wallet balance before evaluation (402 if empty)
    ctx = action.context or {}
    check_wallet_balance(ctx.get("agent_id"))

    eval_start = datetime.now(timezone.utc)
    decision = evaluate_action(action)
    log_action(action, decision)

    # Auto-create governance span if trace_id in context
    _create_governance_span(action, decision, eval_start)

    # Broadcast to real-time SSE subscribers
    action_bus.publish(
        ActionEvent(
            event_type="action_evaluated",
            tool=action.tool,
            decision=decision.decision,
            risk_score=decision.risk_score,
            explanation=decision.explanation,
            policy_ids=decision.policy_ids,
            agent_id=ctx.get("agent_id"),
            session_id=ctx.get("session_id"),
            user_id=ctx.get("user_id"),
            channel=ctx.get("channel"),
            chain_pattern=decision.chain_pattern,
        )
    )

    # Generate SURGE governance receipt
    create_governance_receipt(
        tool=action.tool,
        decision=decision.decision,
        risk_score=decision.risk_score,
        policy_ids=decision.policy_ids,
        chain_pattern=decision.chain_pattern,
        agent_id=ctx.get("agent_id"),
    )

    # ── Escalation: review queue + auto-kill-switch + webhooks ──
    escalation = handle_post_evaluation(
        tool=action.tool,
        decision=decision.decision,
        risk_score=decision.risk_score,
        explanation=decision.explanation,
        policy_ids=decision.policy_ids,
        chain_pattern=decision.chain_pattern,
        agent_id=ctx.get("agent_id"),
        session_id=ctx.get("session_id"),
    )
    decision.escalation_id = escalation.get("escalation_id")
    decision.auto_ks_triggered = escalation.get("auto_ks_triggered", False)
    decision.escalation_severity = escalation.get("severity")

    return decision


@router.get("", response_model=List[ActionLogRead])
def list_actions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, description="Number of records to skip for pagination"),
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
        stmt = stmt.offset(offset).limit(limit)

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
                trace_id=r.trace_id,
                span_id=r.span_id,
                conversation_id=r.conversation_id,
                turn_id=r.turn_id,
                chain_pattern=r.chain_pattern,
            )
            for r in rows
        ]
