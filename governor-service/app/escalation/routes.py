"""
escalation/routes.py — API endpoints for the escalation subsystem
==================================================================

Covers:
- Escalation config (CRUD) — admin sets thresholds per-agent or global
- Review queue (list / approve / reject / stats)
- Webhook management (CRUD)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func

from ..auth.dependencies import require_admin, require_operator, require_any
from ..database import db_session
from ..models import User
from .models import EscalationConfig, EscalationEvent, EscalationWebhook

router = APIRouter(prefix="/escalation", tags=["escalation"])


# ═══════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════

# ── Config ──

class EscalationConfigCreate(BaseModel):
    scope: str = Field("*", description="'*' for global, 'agent:<id>' for per-agent")
    auto_ks_enabled: bool = False
    auto_ks_block_threshold: int = Field(3, ge=1, le=100)
    auto_ks_risk_threshold: int = Field(82, ge=1, le=100)
    auto_ks_window_size: int = Field(10, ge=1, le=200)
    review_risk_threshold: int = Field(70, ge=0, le=100)
    notify_on_block: bool = True
    notify_on_review: bool = True
    notify_on_auto_ks: bool = True


class EscalationConfigUpdate(BaseModel):
    auto_ks_enabled: Optional[bool] = None
    auto_ks_block_threshold: Optional[int] = Field(None, ge=1, le=100)
    auto_ks_risk_threshold: Optional[int] = Field(None, ge=1, le=100)
    auto_ks_window_size: Optional[int] = Field(None, ge=1, le=200)
    review_risk_threshold: Optional[int] = Field(None, ge=0, le=100)
    notify_on_block: Optional[bool] = None
    notify_on_review: Optional[bool] = None
    notify_on_auto_ks: Optional[bool] = None


class EscalationConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: str
    auto_ks_enabled: bool
    auto_ks_block_threshold: int
    auto_ks_risk_threshold: int
    auto_ks_window_size: int
    review_risk_threshold: int
    notify_on_block: bool
    notify_on_review: bool
    notify_on_auto_ks: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── Review Queue ──

class EscalationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    action_log_id: Optional[int] = None
    tool: str
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    trigger: str
    severity: str
    decision: str
    risk_score: int
    explanation: str
    policy_ids: List[str] = []
    chain_pattern: Optional[str] = None
    status: str
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None


class EscalationResolve(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    note: Optional[str] = Field(None, max_length=2000)


class EscalationStats(BaseModel):
    total: int
    pending: int
    approved: int
    rejected: int
    expired: int
    auto_resolved: int
    critical: int
    high: int
    medium: int
    low: int


# ── Webhooks ──

class WebhookCreate(BaseModel):
    url: str = Field(..., min_length=1, max_length=1024)
    label: str = Field("", max_length=256)
    on_block: bool = True
    on_review: bool = True
    on_auto_ks: bool = True
    auth_header: Optional[str] = Field(None, max_length=512)


class WebhookUpdate(BaseModel):
    url: Optional[str] = Field(None, max_length=1024)
    label: Optional[str] = Field(None, max_length=256)
    on_block: Optional[bool] = None
    on_review: Optional[bool] = None
    on_auto_ks: Optional[bool] = None
    auth_header: Optional[str] = Field(None, max_length=512)
    is_active: Optional[bool] = None


class WebhookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    label: str
    on_block: bool
    on_review: bool
    on_auto_ks: bool
    is_active: bool
    created_at: Optional[datetime] = None


# ═══════════════════════════════════════════════════════════════════════════
# Config endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/config", response_model=List[EscalationConfigRead])
def list_configs(_user: User = Depends(require_any)):
    """List all escalation configurations (global + per-agent)."""
    with db_session() as session:
        rows = session.execute(
            select(EscalationConfig).order_by(EscalationConfig.scope)
        ).scalars().all()
        return [EscalationConfigRead.model_validate(r) for r in rows]


@router.get("/config/{scope}", response_model=EscalationConfigRead)
def get_config(scope: str, _user: User = Depends(require_any)):
    """Get escalation config for a specific scope ('*' or 'agent:<id>')."""
    with db_session() as session:
        row = session.execute(
            select(EscalationConfig).where(EscalationConfig.scope == scope)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(404, f"No escalation config for scope '{scope}'")
        return EscalationConfigRead.model_validate(row)


@router.post("/config", response_model=EscalationConfigRead, status_code=201)
def create_config(body: EscalationConfigCreate, _user: User = Depends(require_admin)):
    """Create an escalation configuration. Scope must be unique."""
    with db_session() as session:
        existing = session.execute(
            select(EscalationConfig).where(EscalationConfig.scope == body.scope)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(409, f"Config for scope '{body.scope}' already exists. Use PUT to update.")

        row = EscalationConfig(**body.model_dump())
        session.add(row)
        session.flush()
        return EscalationConfigRead.model_validate(row)


@router.put("/config/{scope}", response_model=EscalationConfigRead)
def update_config(scope: str, body: EscalationConfigUpdate, _user: User = Depends(require_admin)):
    """Update escalation config for a scope. Only provided fields are changed."""
    with db_session() as session:
        row = session.execute(
            select(EscalationConfig).where(EscalationConfig.scope == scope)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(404, f"No escalation config for scope '{scope}'")

        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(row, field, value)

        session.flush()
        return EscalationConfigRead.model_validate(row)


@router.delete("/config/{scope}", status_code=204)
def delete_config(scope: str, _user: User = Depends(require_admin)):
    """Delete an escalation configuration."""
    with db_session() as session:
        row = session.execute(
            select(EscalationConfig).where(EscalationConfig.scope == scope)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(404, f"No escalation config for scope '{scope}'")
        session.delete(row)


# ═══════════════════════════════════════════════════════════════════════════
# Review queue endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/queue", response_model=List[EscalationEventRead])
def list_queue(
    status: Optional[str] = Query(None, description="Filter: pending|approved|rejected|expired|auto_resolved"),
    severity: Optional[str] = Query(None, description="Filter: critical|high|medium|low"),
    agent_id: Optional[str] = Query(None),
    trigger: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    _user: User = Depends(require_any),
):
    """List escalation events (review queue). Default: most recent first."""
    with db_session() as session:
        stmt = select(EscalationEvent).order_by(EscalationEvent.created_at.desc())
        if status:
            stmt = stmt.where(EscalationEvent.status == status)
        if severity:
            stmt = stmt.where(EscalationEvent.severity == severity)
        if agent_id:
            stmt = stmt.where(EscalationEvent.agent_id == agent_id)
        if trigger:
            stmt = stmt.where(EscalationEvent.trigger == trigger)
        stmt = stmt.limit(limit)

        rows = session.execute(stmt).scalars().all()
        return [_event_to_read(r) for r in rows]


@router.get("/queue/stats", response_model=EscalationStats)
def queue_stats(_user: User = Depends(require_any)):
    """Summary statistics for the escalation review queue."""
    with db_session() as session:
        total = session.execute(select(func.count(EscalationEvent.id))).scalar() or 0

        def _count_by(col, val):
            return session.execute(
                select(func.count(EscalationEvent.id)).where(col == val)
            ).scalar() or 0

        return EscalationStats(
            total=total,
            pending=_count_by(EscalationEvent.status, "pending"),
            approved=_count_by(EscalationEvent.status, "approved"),
            rejected=_count_by(EscalationEvent.status, "rejected"),
            expired=_count_by(EscalationEvent.status, "expired"),
            auto_resolved=_count_by(EscalationEvent.status, "auto_resolved"),
            critical=_count_by(EscalationEvent.severity, "critical"),
            high=_count_by(EscalationEvent.severity, "high"),
            medium=_count_by(EscalationEvent.severity, "medium"),
            low=_count_by(EscalationEvent.severity, "low"),
        )


@router.get("/queue/{event_id}", response_model=EscalationEventRead)
def get_event(event_id: int, _user: User = Depends(require_any)):
    """Get a single escalation event by ID."""
    with db_session() as session:
        row = session.get(EscalationEvent, event_id)
        if not row:
            raise HTTPException(404, f"Escalation event {event_id} not found")
        return _event_to_read(row)


@router.post("/queue/{event_id}/resolve", response_model=EscalationEventRead)
def resolve_event(
    event_id: int,
    body: EscalationResolve,
    user: User = Depends(require_operator),
):
    """
    Approve or reject a pending escalation event.

    - approved: Operator confirms the action can proceed (or was investigated)
    - rejected: Operator confirms the block was correct and no further action needed
    """
    with db_session() as session:
        row = session.get(EscalationEvent, event_id)
        if not row:
            raise HTTPException(404, f"Escalation event {event_id} not found")
        if row.status != "pending":
            raise HTTPException(
                409, f"Event {event_id} is already resolved (status: {row.status})"
            )

        row.status = body.status
        row.resolved_by = user.username
        row.resolved_at = datetime.now(timezone.utc)
        row.resolution_note = body.note

        session.flush()
        return _event_to_read(row)


@router.post("/queue/bulk-resolve", response_model=dict)
def bulk_resolve(
    event_ids: List[int],
    body: EscalationResolve,
    user: User = Depends(require_operator),
):
    """Resolve multiple escalation events at once."""
    resolved = 0
    skipped = 0
    with db_session() as session:
        for eid in event_ids:
            row = session.get(EscalationEvent, eid)
            if not row or row.status != "pending":
                skipped += 1
                continue
            row.status = body.status
            row.resolved_by = user.username
            row.resolved_at = datetime.now(timezone.utc)
            row.resolution_note = body.note
            resolved += 1
    return {"resolved": resolved, "skipped": skipped}


# ═══════════════════════════════════════════════════════════════════════════
# Webhook endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/webhooks", response_model=List[WebhookRead])
def list_webhooks(_user: User = Depends(require_operator)):
    """List all registered escalation webhooks."""
    with db_session() as session:
        rows = session.execute(
            select(EscalationWebhook).order_by(EscalationWebhook.created_at.desc())
        ).scalars().all()
        return [WebhookRead.model_validate(r) for r in rows]


@router.post("/webhooks", response_model=WebhookRead, status_code=201)
def create_webhook(body: WebhookCreate, _user: User = Depends(require_admin)):
    """Register a new escalation webhook endpoint."""
    with db_session() as session:
        row = EscalationWebhook(**body.model_dump())
        session.add(row)
        session.flush()
        return WebhookRead.model_validate(row)


@router.put("/webhooks/{webhook_id}", response_model=WebhookRead)
def update_webhook(
    webhook_id: int, body: WebhookUpdate, _user: User = Depends(require_admin)
):
    """Update a webhook configuration."""
    with db_session() as session:
        row = session.get(EscalationWebhook, webhook_id)
        if not row:
            raise HTTPException(404, f"Webhook {webhook_id} not found")
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        session.flush()
        return WebhookRead.model_validate(row)


@router.delete("/webhooks/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: int, _user: User = Depends(require_admin)):
    """Delete a webhook."""
    with db_session() as session:
        row = session.get(EscalationWebhook, webhook_id)
        if not row:
            raise HTTPException(404, f"Webhook {webhook_id} not found")
        session.delete(row)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _event_to_read(row: EscalationEvent) -> EscalationEventRead:
    return EscalationEventRead(
        id=row.id,
        created_at=row.created_at,
        action_log_id=row.action_log_id,
        tool=row.tool,
        agent_id=row.agent_id,
        session_id=row.session_id,
        trigger=row.trigger,
        severity=row.severity,
        decision=row.decision,
        risk_score=row.risk_score,
        explanation=row.explanation,
        policy_ids=[p for p in (row.policy_ids or "").split(",") if p],
        chain_pattern=row.chain_pattern,
        status=row.status,
        resolved_by=row.resolved_by,
        resolved_at=row.resolved_at,
        resolution_note=row.resolution_note,
    )
