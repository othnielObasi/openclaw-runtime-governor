from __future__ import annotations

import json
import logging
import secrets
import time as _time
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select

from ..auth.dependencies import require_any, require_operator
from ..config import settings
from ..database import db_session
from ..escalation.engine import handle_post_evaluation
from ..event_bus import ActionEvent, action_bus
from ..models import ActionLog, TraceSpan, User
from ..modules import modules as gov_modules
from ..policies.engine import evaluate_action
from ..schemas import ActionInput, ActionDecision, ActionLogRead
from ..telemetry.logger import log_action
from .routes_surge import create_governance_receipt, check_wallet_balance

router = APIRouter(prefix="/actions", tags=["actions"])
_log = logging.getLogger("governor.actions")


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

    Pre-evaluation gates:
      - Budget enforcer: blocks if agent has blown through eval quotas.
    Post-evaluation hooks:
      - Metrics recording (Prometheus counters + latency histogram)
      - Agent fingerprinting (record + deviation check)
      - Impact assessment recording
      - SIEM dispatch for high-severity events
    """
    ctx = action.context or {}
    # Merge top-level parameters into args
    if action.parameters:
        action.args = {**action.args, **(action.parameters or {})}
    # Prefer top-level agent_id/session_id, fall back to context
    agent_id = action.agent_id or ctx.get("agent_id")
    session_id = action.session_id or ctx.get("session_id")

    # ── Pre-eval gate: Budget enforcer ────────────────────────────
    budget_enforcer = gov_modules.budget_enforcer if (
        settings.modules_enabled and settings.budget_enforcer_enabled
    ) else None

    if budget_enforcer is not None:
        try:
            budget_status = budget_enforcer.check_budget(
                agent_id=agent_id or "anonymous",
                session_id=session_id or "default",
            )
            if budget_status.exceeded:
                # Record metric
                if gov_modules.metrics:
                    gov_modules.metrics.record_budget_exceeded(budget_status.reason or "quota")
                raise HTTPException(
                    status_code=429,
                    detail=f"Budget exceeded: {budget_status.reason}",
                )
        except HTTPException:
            raise
        except Exception as exc:
            _log.warning("Budget check error (non-blocking): %s", exc)

    # Check SURGE wallet balance before evaluation (402 if empty)
    check_wallet_balance(agent_id)

    eval_start = datetime.now(timezone.utc)
    t0 = _time.perf_counter()
    decision = evaluate_action(action)
    latency_ms = (_time.perf_counter() - t0) * 1000
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
            agent_id=agent_id,
            session_id=session_id,
            user_id=ctx.get("user_id"),
            channel=ctx.get("channel"),
            chain_pattern=decision.chain_pattern,
        )
    )

    # Generate SURGE governance receipt (v2 when enabled, v1 fallback)
    if settings.surge_v2_enabled and gov_modules.surge_engine:
        try:
            gov_modules.surge_engine.issue(
                tool=action.tool,
                decision=decision.decision,
                risk_score=decision.risk_score,
                explanation=decision.explanation or "",
                policy_ids=decision.policy_ids or [],
                chain_pattern=decision.chain_pattern,
                agent_id=agent_id,
                session_id=session_id,
            )
        except Exception as exc:
            _log.warning("SURGE v2 receipt error (falling back to v1): %s", exc)
            create_governance_receipt(
                tool=action.tool,
                decision=decision.decision,
                risk_score=decision.risk_score,
                policy_ids=decision.policy_ids,
                chain_pattern=decision.chain_pattern,
                agent_id=agent_id,
            )
    else:
        create_governance_receipt(
            tool=action.tool,
            decision=decision.decision,
            risk_score=decision.risk_score,
            policy_ids=decision.policy_ids,
            chain_pattern=decision.chain_pattern,
            agent_id=agent_id,
        )

    # ── Escalation: review queue + auto-kill-switch + webhooks ──
    escalation = handle_post_evaluation(
        tool=action.tool,
        decision=decision.decision,
        risk_score=decision.risk_score,
        explanation=decision.explanation,
        policy_ids=decision.policy_ids,
        chain_pattern=decision.chain_pattern,
        agent_id=agent_id,
        session_id=session_id,
    )
    decision.escalation_id = escalation.get("escalation_id")
    decision.auto_ks_triggered = escalation.get("auto_ks_triggered", False)
    decision.escalation_severity = escalation.get("severity")

    # ── Post-eval hooks: Compliance modules ────────────────────────
    _run_post_eval_hooks(action, decision, latency_ms)

    return decision


def _run_post_eval_hooks(
    action: ActionInput,
    decision: ActionDecision,
    latency_ms: float,
) -> None:
    """Fire-and-forget post-evaluation hooks.  Errors are logged, never raised."""
    ctx = action.context or {}
    agent_id = ctx.get("agent_id", "anonymous")
    session_id = ctx.get("session_id", "default")

    # ── Metrics ──
    if settings.modules_enabled and settings.metrics_enabled and gov_modules.metrics:
        try:
            gov_modules.metrics.record_evaluation(
                decision=decision.decision,
                latency_ms=latency_ms,
                tool=action.tool,
                policy_ids=decision.policy_ids or None,
            )
            if decision.chain_pattern:
                gov_modules.metrics.record_chain_detection(decision.chain_pattern)
        except Exception as exc:
            _log.warning("Metrics recording error: %s", exc)

    # ── Budget: record the evaluation cost ──
    if settings.modules_enabled and settings.budget_enforcer_enabled and gov_modules.budget_enforcer:
        try:
            gov_modules.budget_enforcer.record_evaluation(
                agent_id=agent_id,
                session_id=session_id,
                decision=decision.decision,
                cost=0.0,
            )
        except Exception as exc:
            _log.warning("Budget record error: %s", exc)

    # ── Agent fingerprinting ──
    if settings.modules_enabled and settings.fingerprinting_enabled and gov_modules.fingerprint_engine:
        try:
            deviations = gov_modules.fingerprint_engine.check(
                agent_id=agent_id,
                tool=action.tool,
                args=action.args,
                session_id=session_id,
            )
            if deviations:
                decision.deviation_count = len(deviations)
                decision.deviation_types = [d.deviation_type for d in deviations]

            gov_modules.fingerprint_engine.record(
                agent_id=agent_id,
                tool=action.tool,
                args=action.args,
                decision=decision.decision,
                risk_score=decision.risk_score,
                latency_ms=latency_ms,
                session_id=session_id,
            )
        except Exception as exc:
            _log.warning("Fingerprinting error: %s", exc)

    # ── Impact assessment ──
    if settings.modules_enabled and settings.impact_assessment_enabled and gov_modules.impact_engine:
        try:
            gov_modules.impact_engine.record(
                tool=action.tool,
                decision=decision.decision,
                risk_score=decision.risk_score,
                agent_id=agent_id,
                session_id=session_id,
                policy_ids=decision.policy_ids or [],
                chain_pattern=decision.chain_pattern,
                deviation_types=decision.deviation_types or [],
                explanation=decision.explanation or "",
            )
        except Exception as exc:
            _log.warning("Impact assessment error: %s", exc)

    # ── SIEM dispatch ──
    if settings.modules_enabled and settings.siem_enabled and gov_modules.siem_dispatcher:
        try:
            from siem_webhook import GovernanceEvent, compute_severity
            severity = compute_severity(
                decision.decision, decision.risk_score,
                decision.chain_pattern, decision.deviation_types or [],
            )
            siem_event = GovernanceEvent(
                event_id=f"gov-{__import__('secrets').token_hex(8)}",
                timestamp=__import__('datetime').datetime.now(
                    __import__('datetime').timezone.utc
                ).isoformat(),
                event_type="evaluation",
                tool=action.tool,
                decision=decision.decision,
                risk_score=decision.risk_score,
                explanation=decision.explanation or "",
                agent_id=agent_id,
                session_id=session_id,
                policy_ids=decision.policy_ids or [],
                chain_pattern=decision.chain_pattern,
                severity=severity,
            )
            gov_modules.siem_dispatcher.dispatch(siem_event)
        except Exception as exc:
            _log.warning("SIEM dispatch error: %s", exc)

    # ── Escalation connector ──
    if settings.modules_enabled and gov_modules.escalation_connector:
        try:
            from escalation import EscalationEvent
            # Only escalate for block/review decisions or high risk
            if decision.decision in ("block", "review") or decision.risk_score >= 70:
                esc_event = EscalationEvent(
                    event_id=f"esc-{__import__('secrets').token_hex(8)}",
                    timestamp=__import__('datetime').datetime.now(
                        __import__('datetime').timezone.utc
                    ).isoformat(),
                    tool=action.tool,
                    decision=decision.decision,
                    risk_score=decision.risk_score,
                    explanation=decision.explanation or "",
                    agent_id=agent_id,
                    session_id=session_id,
                    policy_ids=decision.policy_ids or [],
                    chain_pattern=decision.chain_pattern,
                    deviations=[{"type": d} for d in (decision.deviation_types or [])],
                    is_kill_switch=(decision.decision == "block" and decision.risk_score >= 90),
                )
                gov_modules.escalation_connector.escalate(esc_event)
        except Exception as exc:
            _log.warning("Escalation connector error: %s", exc)


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
