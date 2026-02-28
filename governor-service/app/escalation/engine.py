"""
escalation/engine.py — Server-side escalation logic
=====================================================

Called after every action evaluation to:
1. Check if auto-kill-switch thresholds are breached
2. Create review queue entries for block/review decisions
3. Dispatch webhook notifications
4. Compute severity based on risk + trigger type

This runs SERVER-SIDE (not in the dashboard), ensuring escalation
happens even when no dashboard is open.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select, func

from ..database import db_session
from ..models import ActionLog
from ..state import set_kill_switch, is_kill_switch_enabled
from ..event_bus import ActionEvent, action_bus
from .models import EscalationConfig, EscalationEvent, EscalationWebhook

logger = logging.getLogger("governor.escalation")


# ---------------------------------------------------------------------------
# Config resolution — per-agent overrides fall back to global "*"
# ---------------------------------------------------------------------------

def get_escalation_config(agent_id: Optional[str] = None) -> dict:
    """
    Resolve escalation config for an agent.
    Priority: agent-specific → global "*" → hardcoded defaults.
    Returns a plain dict of config values.
    """
    defaults = {
        "auto_ks_enabled": False,
        "auto_ks_block_threshold": 3,
        "auto_ks_risk_threshold": 82,
        "auto_ks_window_size": 10,
        "review_risk_threshold": 70,
        "notify_on_block": True,
        "notify_on_review": True,
        "notify_on_auto_ks": True,
    }

    try:
        with db_session() as session:
            # Try agent-specific first
            if agent_id:
                scope_key = f"agent:{agent_id}"
                row = session.execute(
                    select(EscalationConfig).where(EscalationConfig.scope == scope_key)
                ).scalar_one_or_none()
                if row:
                    return _row_to_dict(row)

            # Fall back to global
            row = session.execute(
                select(EscalationConfig).where(EscalationConfig.scope == "*")
            ).scalar_one_or_none()
            if row:
                return _row_to_dict(row)
    except Exception as exc:
        logger.warning("Failed to load escalation config: %s", exc)

    return defaults


def _row_to_dict(row: EscalationConfig) -> dict:
    return {
        "auto_ks_enabled": row.auto_ks_enabled,
        "auto_ks_block_threshold": row.auto_ks_block_threshold,
        "auto_ks_risk_threshold": row.auto_ks_risk_threshold,
        "auto_ks_window_size": row.auto_ks_window_size,
        "review_risk_threshold": row.review_risk_threshold,
        "notify_on_block": row.notify_on_block,
        "notify_on_review": row.notify_on_review,
        "notify_on_auto_ks": row.notify_on_auto_ks,
    }


# ---------------------------------------------------------------------------
# Severity computation
# ---------------------------------------------------------------------------

def compute_severity(risk_score: int, decision: str, chain_pattern: Optional[str]) -> str:
    """Derive escalation severity from risk + decision + chain detection."""
    if decision == "block" and risk_score >= 90:
        return "critical"
    if decision == "block" or risk_score >= 80:
        return "high"
    if chain_pattern or risk_score >= 50:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Auto-kill-switch check
# ---------------------------------------------------------------------------

def check_auto_kill_switch(
    agent_id: Optional[str],
    config: dict,
) -> Optional[dict]:
    """
    Check if auto-kill-switch thresholds are breached based on
    recent action history from the DB.

    Returns a dict with trigger details if KS should engage, else None.
    """
    if not config.get("auto_ks_enabled"):
        return None

    if is_kill_switch_enabled():
        return None  # already active

    window = config.get("auto_ks_window_size", 10)
    block_threshold = config.get("auto_ks_block_threshold", 3)
    risk_threshold = config.get("auto_ks_risk_threshold", 82)

    try:
        with db_session() as session:
            # Get the N most recent actions
            stmt = (
                select(ActionLog)
                .order_by(ActionLog.created_at.desc())
                .limit(window)
            )
            # If agent_id provided and config is per-agent, scope to that agent
            if agent_id and config.get("_scope_agent"):
                stmt = stmt.where(ActionLog.agent_id == agent_id)

            rows = session.execute(stmt).scalars().all()

            if not rows:
                return None

            recent_blocks = sum(1 for r in rows if r.decision == "block")
            avg_risk = sum(r.risk_score for r in rows) / len(rows)

            # Check block count threshold
            if recent_blocks >= block_threshold:
                return {
                    "trigger": "block_count",
                    "detail": f"{recent_blocks} blocks in last {len(rows)} actions (threshold: {block_threshold})",
                    "recent_blocks": recent_blocks,
                    "avg_risk": round(avg_risk, 1),
                }

            # Check average risk threshold
            if avg_risk >= risk_threshold:
                return {
                    "trigger": "avg_risk",
                    "detail": f"Average risk {avg_risk:.1f}/100 in last {len(rows)} actions (threshold: {risk_threshold})",
                    "recent_blocks": recent_blocks,
                    "avg_risk": round(avg_risk, 1),
                }

    except Exception as exc:
        logger.warning("Auto-KS check failed: %s", exc)

    return None


# ---------------------------------------------------------------------------
# Review queue entry creation
# ---------------------------------------------------------------------------

def create_escalation_event(
    tool: str,
    decision: str,
    risk_score: int,
    explanation: str,
    policy_ids: list[str],
    chain_pattern: Optional[str],
    agent_id: Optional[str],
    session_id: Optional[str],
    trigger: str,
    action_log_id: Optional[int] = None,
) -> Optional[int]:
    """Create a review queue entry. Returns the escalation event ID."""
    severity = compute_severity(risk_score, decision, chain_pattern)

    try:
        with db_session() as session:
            event = EscalationEvent(
                action_log_id=action_log_id,
                tool=tool,
                agent_id=agent_id,
                session_id=session_id,
                trigger=trigger,
                severity=severity,
                decision=decision,
                risk_score=risk_score,
                explanation=explanation,
                policy_ids=",".join(policy_ids) if policy_ids else None,
                chain_pattern=chain_pattern,
                status="pending",
            )
            session.add(event)
            session.flush()
            event_id = event.id
        return event_id
    except Exception as exc:
        logger.error("Failed to create escalation event: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Webhook dispatch (fire-and-forget with timeout)
# ---------------------------------------------------------------------------

def dispatch_webhooks(
    event_type: str,
    payload: dict,
) -> None:
    """
    Send webhook notifications for an escalation event.
    Non-blocking with a short timeout — failures are logged but don't
    block the evaluation pipeline.

    event_type: "block" | "review" | "auto_ks"
    """
    try:
        with db_session() as session:
            stmt = select(EscalationWebhook).where(
                EscalationWebhook.is_active == True  # noqa: E712
            )
            hooks = session.execute(stmt).scalars().all()

            for hook in hooks:
                # Check if this hook should fire for this event type
                if event_type == "block" and not hook.on_block:
                    continue
                if event_type == "review" and not hook.on_review:
                    continue
                if event_type == "auto_ks" and not hook.on_auto_ks:
                    continue

                _fire_webhook(hook.url, hook.auth_header, payload, hook.label)

    except Exception as exc:
        logger.warning("Failed to dispatch webhooks: %s", exc)


def _fire_webhook(
    url: str,
    auth_header: Optional[str],
    payload: dict,
    label: str,
) -> None:
    """Send a single webhook POST. Timeouts and errors are logged, not raised."""
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.warning(
                    "Webhook %r (%s) returned %d: %s",
                    label, url, resp.status_code, resp.text[:200],
                )
            else:
                logger.info("Webhook %r dispatched to %s → %d", label, url, resp.status_code)
    except Exception as exc:
        logger.warning("Webhook %r (%s) failed: %s", label, url, exc)


# ---------------------------------------------------------------------------
# Main escalation handler — called after every evaluation
# ---------------------------------------------------------------------------

def handle_post_evaluation(
    tool: str,
    decision: str,
    risk_score: int,
    explanation: str,
    policy_ids: list[str],
    chain_pattern: Optional[str],
    agent_id: Optional[str],
    session_id: Optional[str],
    action_log_id: Optional[int] = None,
) -> dict:
    """
    Post-evaluation escalation logic. Called from routes_actions after
    the evaluation engine returns a decision.

    Steps:
    1. Load escalation config (per-agent or global)
    2. If decision is block/review → create escalation event in review queue
    3. Check auto-kill-switch thresholds
    4. Dispatch webhook notifications

    Returns a dict summarising what happened (for response enrichment).
    """
    result = {
        "escalation_id": None,
        "auto_ks_triggered": False,
        "auto_ks_reason": None,
        "webhooks_dispatched": False,
        "severity": None,
    }

    config = get_escalation_config(agent_id)

    # ── Step 1: Create escalation event for block/review decisions ──
    if decision in ("block", "review"):
        trigger = "policy_block" if decision == "block" else "policy_review"
        if chain_pattern:
            trigger = "chain_escalation"

        event_id = create_escalation_event(
            tool=tool,
            decision=decision,
            risk_score=risk_score,
            explanation=explanation,
            policy_ids=policy_ids,
            chain_pattern=chain_pattern,
            agent_id=agent_id,
            session_id=session_id,
            trigger=trigger,
            action_log_id=action_log_id,
        )
        result["escalation_id"] = event_id
        result["severity"] = compute_severity(risk_score, decision, chain_pattern)

    # ── Step 2: Check auto-kill-switch ──
    ks_trigger = check_auto_kill_switch(agent_id, config)
    if ks_trigger:
        set_kill_switch(True)
        result["auto_ks_triggered"] = True
        result["auto_ks_reason"] = ks_trigger["detail"]

        # Create an escalation event for the auto-KS itself
        create_escalation_event(
            tool="*",
            decision="block",
            risk_score=100,
            explanation=f"Auto-kill-switch triggered: {ks_trigger['detail']}",
            policy_ids=[],
            chain_pattern=None,
            agent_id=agent_id,
            session_id=session_id,
            trigger="auto_ks",
        )

        # Broadcast SSE event
        action_bus.publish(
            ActionEvent(
                event_type="auto_kill_switch",
                tool="*",
                decision="block",
                risk_score=100,
                explanation=f"Auto-kill-switch triggered: {ks_trigger['detail']}",
                policy_ids=[],
                agent_id=agent_id,
                chain_pattern=None,
            )
        )

        logger.warning(
            "AUTO KILL SWITCH ENGAGED — %s (agent: %s)",
            ks_trigger["detail"], agent_id or "global",
        )

    # ── Step 3: Dispatch webhooks ──
    if decision == "block" and config.get("notify_on_block"):
        dispatch_webhooks("block", _build_webhook_payload(
            "action_blocked", tool, decision, risk_score, explanation,
            policy_ids, chain_pattern, agent_id,
        ))
        result["webhooks_dispatched"] = True

    if decision == "review" and config.get("notify_on_review"):
        dispatch_webhooks("review", _build_webhook_payload(
            "action_review", tool, decision, risk_score, explanation,
            policy_ids, chain_pattern, agent_id,
        ))
        result["webhooks_dispatched"] = True

    if ks_trigger and config.get("notify_on_auto_ks"):
        dispatch_webhooks("auto_ks", {
            "event": "auto_kill_switch",
            "reason": ks_trigger["detail"],
            "trigger": ks_trigger["trigger"],
            "recent_blocks": ks_trigger["recent_blocks"],
            "avg_risk": ks_trigger["avg_risk"],
            "agent_id": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        result["webhooks_dispatched"] = True

    return result


def _build_webhook_payload(
    event_type: str,
    tool: str,
    decision: str,
    risk_score: int,
    explanation: str,
    policy_ids: list[str],
    chain_pattern: Optional[str],
    agent_id: Optional[str],
) -> dict:
    return {
        "event": event_type,
        "tool": tool,
        "decision": decision,
        "risk_score": risk_score,
        "explanation": explanation,
        "policy_ids": policy_ids,
        "chain_pattern": chain_pattern,
        "agent_id": agent_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
