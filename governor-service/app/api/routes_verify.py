"""
routes_verify.py — Post-execution verification endpoint
=========================================================
Agents call POST /actions/verify after executing a tool to submit
the actual result for compliance checking. The verification engine
runs 8 independent checks and returns a verdict.

This closes the intent-vs-reality gap identified in the governance
audit: the policy engine gates intent, the verification engine
validates outcome.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..auth.dependencies import require_any, require_operator
from ..database import db_session
from ..escalation.engine import handle_post_evaluation
from ..event_bus import ActionEvent, action_bus
from ..models import ActionLog, TraceSpan, User, VerificationLog
from ..schemas import (
    VerificationInput,
    VerificationResult,
    VerificationFinding,
    VerificationLogRead,
    DriftSignalRead,
)
from ..verification.engine import verify_execution

logger = logging.getLogger("governor.verify")

router = APIRouter(prefix="/actions", tags=["verification"])


def _create_verification_span(
    verify_input: VerificationInput,
    verdict: VerificationResult,
    start: datetime,
) -> None:
    """Auto-create a 'governance' trace span for the verification."""
    ctx = verify_input.context or {}
    trace_id = ctx.get("trace_id")
    if not trace_id:
        return

    now = datetime.now(timezone.utc)
    dur = (now - start).total_seconds() * 1000

    attrs = {
        "governor.type": "verification",
        "governor.verdict": verdict.verification,
        "governor.risk_delta": verdict.risk_delta,
        "governor.tool": verify_input.tool,
        "governor.action_id": verify_input.action_id,
        "governor.findings": [
            {"check": f.check, "result": f.result, "risk": f.risk_contribution}
            for f in verdict.findings
        ],
    }
    if verdict.drift_score is not None:
        attrs["governor.drift_score"] = verdict.drift_score

    span_id = f"verify-{secrets.token_hex(12)}"

    try:
        with db_session() as session:
            row = TraceSpan(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=ctx.get("span_id"),
                kind="governance",
                name=f"governor.verify({verify_input.tool})",
                status="ok" if verdict.verification == "compliant" else "error",
                start_time=start,
                end_time=now,
                duration_ms=round(dur, 2),
                agent_id=ctx.get("agent_id"),
                session_id=ctx.get("session_id"),
                attributes_json=json.dumps(attrs),
                input_text=json.dumps({
                    "tool": verify_input.tool,
                    "action_id": verify_input.action_id,
                    "result_keys": list(verify_input.result.keys()),
                }),
                output_text=json.dumps({
                    "verdict": verdict.verification,
                    "risk_delta": verdict.risk_delta,
                    "finding_count": len(verdict.findings),
                }),
            )
            session.add(row)
    except Exception as exc:
        logger.warning("Failed to create verification span: %s", exc)


@router.post("/verify", response_model=VerificationResult)
def verify_action_route(
    verify_input: VerificationInput,
    _user: User = Depends(require_operator),
) -> VerificationResult:
    """Verify a tool execution result against the governance safety model.

    The agent calls this AFTER executing a tool to submit the actual result.
    The verification engine runs 8 independent checks:

    1. **Credential leak scan** — secrets, API keys, tokens in output
    2. **Destructive output detection** — mass deletion, schema drops, etc.
    3. **Scope compliance** — result consistent with allowed scope
    4. **Diff size anomaly** — unexpectedly large changes
    5. **Result-intent alignment** — was a blocked action executed anyway?
    6. **Output injection detection** — prompt injection in tool output
    7. **Independent re-verification** — policy engine re-run on result
    8. **Cross-session drift** — behavioural baseline comparison

    Returns one of: `compliant`, `suspicious`, or `violation`.
    Violations may trigger escalation (review queue + notifications).
    """
    eval_start = datetime.now(timezone.utc)
    ctx = verify_input.context or {}

    # ── Look up the original evaluation ───────────────────────────────
    with db_session() as session:
        original = session.execute(
            select(ActionLog).where(ActionLog.id == verify_input.action_id)
        ).scalar_one_or_none()

    if not original:
        raise HTTPException(
            status_code=404,
            detail=f"No evaluation found with action_id={verify_input.action_id}. "
                   "Submit the action_id returned from POST /actions/evaluate.",
        )

    # Parse original context for allowed_tools
    original_context = {}
    if original.context:
        try:
            original_context = json.loads(original.context)
        except (json.JSONDecodeError, TypeError):
            pass

    original_args = {}
    if original.args:
        try:
            original_args = json.loads(original.args)
        except (json.JSONDecodeError, TypeError):
            pass

    # ── Run verification pipeline ─────────────────────────────────────
    verdict_data = verify_execution(
        action_id=verify_input.action_id,
        tool=verify_input.tool,
        result=verify_input.result,
        original_decision=original.decision,
        original_risk=original.risk_score,
        original_args=original_args,
        allowed_tools=original_context.get("allowed_tools"),
        agent_id=ctx.get("agent_id") or original.agent_id,
        session_id=ctx.get("session_id") or original.session_id,
    )

    # ── Build response ────────────────────────────────────────────────
    findings = [
        VerificationFinding(
            check=f.check,
            result=f.result,
            detail=f.detail,
            risk_contribution=f.risk_contribution,
            duration_ms=f.duration_ms,
        )
        for f in verdict_data.findings
    ]

    drift_signals = [
        DriftSignalRead(
            name=s.name,
            description=s.description,
            weight=s.weight,
            triggered=s.triggered,
            value=s.value,
            detail=s.detail,
        )
        for s in verdict_data.drift_signals
    ]

    result = VerificationResult(
        verification=verdict_data.verification,
        risk_delta=verdict_data.risk_delta,
        findings=findings,
        escalated=False,
        drift_score=verdict_data.drift_score,
        drift_signals=drift_signals,
    )

    # ── Escalate violations ───────────────────────────────────────────
    if verdict_data.verification == "violation":
        try:
            escalation = handle_post_evaluation(
                tool=verify_input.tool,
                decision="block",  # Treat verification violations as blocks
                risk_score=min(100, original.risk_score + verdict_data.risk_delta),
                explanation=f"Post-execution verification: {verdict_data.verification}. "
                           + "; ".join(f.detail for f in verdict_data.findings if f.result == "fail"),
                policy_ids=[f.check for f in verdict_data.findings if f.result == "fail"],
                chain_pattern=None,
                agent_id=ctx.get("agent_id") or original.agent_id,
                session_id=ctx.get("session_id") or original.session_id,
            )
            result.escalated = True
            result.escalation_id = escalation.get("escalation_id")
        except Exception as exc:
            logger.warning("Failed to escalate verification violation: %s", exc)

    # ── Persist verification log ──────────────────────────────────────
    try:
        with db_session() as session:
            log = VerificationLog(
                action_id=verify_input.action_id,
                tool=verify_input.tool,
                agent_id=ctx.get("agent_id") or original.agent_id,
                session_id=ctx.get("session_id") or original.session_id,
                trace_id=ctx.get("trace_id") or original.trace_id,
                result_json=json.dumps(verify_input.result),
                verdict=verdict_data.verification,
                risk_delta=verdict_data.risk_delta,
                findings_json=json.dumps([
                    {"check": f.check, "result": f.result, "detail": f.detail,
                     "risk_contribution": f.risk_contribution, "duration_ms": f.duration_ms}
                    for f in verdict_data.findings
                ]),
                drift_score=verdict_data.drift_score,
                escalated=result.escalated,
                escalation_id=result.escalation_id,
            )
            session.add(log)
    except Exception as exc:
        logger.warning("Failed to persist verification log: %s", exc)

    # ── Create trace span ─────────────────────────────────────────────
    _create_verification_span(verify_input, result, eval_start)

    # ── Broadcast to SSE ──────────────────────────────────────────────
    action_bus.publish(
        ActionEvent(
            event_type="action_verified",
            tool=verify_input.tool,
            decision=verdict_data.verification,
            risk_score=min(100, original.risk_score + verdict_data.risk_delta),
            explanation=f"Verification: {verdict_data.verification} ({len(findings)} checks)",
            policy_ids=[f.check for f in verdict_data.findings if f.result != "pass"],
            agent_id=ctx.get("agent_id") or original.agent_id,
            session_id=ctx.get("session_id") or original.session_id,
        )
    )

    return result


@router.get("/verifications", response_model=List[VerificationLogRead])
def list_verifications(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    agent_id: Optional[str] = Query(None),
    verdict: Optional[str] = Query(None, pattern="^(compliant|violation|suspicious)$"),
    _user: User = Depends(require_any),
) -> List[VerificationLogRead]:
    """List post-execution verification records with optional filters."""
    with db_session() as session:
        stmt = select(VerificationLog).order_by(VerificationLog.created_at.desc())
        if agent_id:
            stmt = stmt.where(VerificationLog.agent_id == agent_id)
        if verdict:
            stmt = stmt.where(VerificationLog.verdict == verdict)
        stmt = stmt.offset(offset).limit(limit)

        rows = session.execute(stmt).scalars().all()
        results = []
        for r in rows:
            findings_parsed = None
            if r.findings_json:
                try:
                    findings_parsed = json.loads(r.findings_json)
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(VerificationLogRead(
                id=r.id,
                created_at=r.created_at,
                action_id=r.action_id,
                tool=r.tool,
                agent_id=r.agent_id,
                session_id=r.session_id,
                trace_id=r.trace_id,
                verdict=r.verdict,
                risk_delta=r.risk_delta,
                findings_json=findings_parsed,
                drift_score=r.drift_score,
                escalated=r.escalated,
                escalation_id=r.escalation_id,
            ))
        return results
