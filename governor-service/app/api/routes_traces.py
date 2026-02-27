"""
routes_traces.py — Agent trace ingestion and correlation
=========================================================
Provides endpoints for:
  - Batch ingestion of agent trace spans (POST /traces/ingest)
  - Listing traces with filters (GET /traces)
  - Full trace detail with correlated governance decisions (GET /traces/{trace_id})

Trace correlation: when an agent includes trace_id in the context of a
POST /actions/evaluate call, the governance decision is automatically
linked. GET /traces/{trace_id} merges trace spans with governance
decisions from action_logs to produce a unified timeline.
"""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, distinct, case, or_

from ..auth.dependencies import require_any, require_operator
from ..database import db_session
from ..models import ActionLog, TraceSpan, User
from ..schemas import (
    SpanCreate,
    SpanBatchCreate,
    SpanRead,
    TraceListItem,
    TraceDetail,
    ActionLogRead,
)

router = APIRouter(prefix="/traces", tags=["traces"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _span_to_read(row: TraceSpan) -> SpanRead:
    """Convert a TraceSpan ORM row to the SpanRead schema."""
    attrs = None
    if row.attributes_json:
        try:
            attrs = json.loads(row.attributes_json)
        except (json.JSONDecodeError, TypeError):
            attrs = None

    events = None
    if row.events_json:
        try:
            events = json.loads(row.events_json)
        except (json.JSONDecodeError, TypeError):
            events = None

    return SpanRead(
        id=row.id,
        trace_id=row.trace_id,
        span_id=row.span_id,
        parent_span_id=row.parent_span_id,
        kind=row.kind,
        name=row.name,
        status=row.status,
        start_time=row.start_time,
        end_time=row.end_time,
        duration_ms=row.duration_ms,
        agent_id=row.agent_id,
        session_id=row.session_id,
        attributes=attrs,
        input=row.input_text,
        output=row.output_text,
        events=events,
        created_at=row.created_at,
    )


def _action_to_read(row: ActionLog) -> ActionLogRead:
    return ActionLogRead(
        id=row.id,
        created_at=row.created_at,
        tool=row.tool,
        decision=row.decision,
        risk_score=row.risk_score,
        explanation=row.explanation,
        policy_ids=[p for p in (row.policy_ids or "").split(",") if p],
        agent_id=row.agent_id,
        session_id=row.session_id,
        user_id=row.user_id,
        channel=row.channel,
        trace_id=row.trace_id,
        span_id=row.span_id,
    )


# ---------------------------------------------------------------------------
# POST /traces/ingest — batch span ingestion
# ---------------------------------------------------------------------------

@router.post("/ingest", status_code=201)
def ingest_spans(
    body: SpanBatchCreate,
    _user: User = Depends(require_operator),
) -> dict:
    """
    Ingest a batch of trace spans.

    Spans can come from any agent framework — the only requirement is a
    consistent trace_id to group spans into a trace. Duplicate span_ids
    are silently skipped (idempotent).
    """
    inserted = 0
    skipped = 0

    with db_session() as session:
        # Check existing span_ids for idempotency
        incoming_ids = [s.span_id for s in body.spans]
        existing = set()
        if incoming_ids:
            rows = session.execute(
                select(TraceSpan.span_id).where(TraceSpan.span_id.in_(incoming_ids))
            ).scalars().all()
            existing = set(rows)

        for span in body.spans:
            if span.span_id in existing:
                skipped += 1
                continue

            # Compute duration_ms if not provided but both times present
            dur = span.duration_ms
            if dur is None and span.end_time and span.start_time:
                dur = (span.end_time - span.start_time).total_seconds() * 1000

            row = TraceSpan(
                trace_id=span.trace_id,
                span_id=span.span_id,
                parent_span_id=span.parent_span_id,
                kind=span.kind,
                name=span.name,
                status=span.status,
                start_time=span.start_time,
                end_time=span.end_time,
                duration_ms=dur,
                agent_id=span.agent_id,
                session_id=span.session_id,
                attributes_json=json.dumps(span.attributes) if span.attributes else None,
                input_text=span.input,
                output_text=span.output,
                events_json=json.dumps(span.events) if span.events else None,
            )
            session.add(row)
            inserted += 1

    return {"inserted": inserted, "skipped": skipped, "total": len(body.spans)}


# ---------------------------------------------------------------------------
# GET /traces — list traces (grouped by trace_id)
# ---------------------------------------------------------------------------

@router.get("", response_model=List[TraceListItem])
def list_traces(
    limit: int = Query(50, ge=1, le=200),
    agent_id: Optional[str] = Query(None, description="Filter by agent_id"),
    session_id: Optional[str] = Query(None, description="Filter by session_id"),
    has_blocks: Optional[bool] = Query(None, description="Only traces that triggered governance blocks"),
    _user: User = Depends(require_any),
) -> List[TraceListItem]:
    """List traces with summary information, ordered by most recent first."""
    with db_session() as session:
        # Get distinct trace_ids with summary stats
        stmt = (
            select(
                TraceSpan.trace_id,
                func.count(TraceSpan.id).label("span_count"),
                func.min(TraceSpan.start_time).label("start_time"),
                func.max(TraceSpan.end_time).label("end_time"),
                func.max(TraceSpan.agent_id).label("agent_id"),
                func.max(TraceSpan.session_id).label("session_id"),
                func.sum(case((TraceSpan.status == "error", 1), else_=0)).label("error_count"),
            )
            .group_by(TraceSpan.trace_id)
            .order_by(func.max(TraceSpan.start_time).desc())
            .limit(limit)
        )

        if agent_id:
            stmt = stmt.where(TraceSpan.agent_id == agent_id)
        if session_id:
            stmt = stmt.where(TraceSpan.session_id == session_id)

        trace_rows = session.execute(stmt).all()

        if not trace_rows:
            return []

        # Get governance counts per trace_id from action_logs
        trace_ids = [r.trace_id for r in trace_rows]
        gov_stmt = (
            select(
                ActionLog.trace_id,
                func.count(ActionLog.id).label("gov_count"),
                func.sum(case((ActionLog.decision == "block", 1), else_=0)).label("block_count"),
            )
            .where(ActionLog.trace_id.in_(trace_ids))
            .group_by(ActionLog.trace_id)
        )
        gov_rows = {r.trace_id: r for r in session.execute(gov_stmt).all()}

        # Get root span names (spans with no parent)
        root_stmt = (
            select(TraceSpan.trace_id, TraceSpan.name)
            .where(TraceSpan.trace_id.in_(trace_ids))
            .where(or_(TraceSpan.parent_span_id == None, TraceSpan.parent_span_id == ""))
        )
        root_names = {r.trace_id: r.name for r in session.execute(root_stmt).all()}

        results = []
        for r in trace_rows:
            gov = gov_rows.get(r.trace_id)
            gov_count = gov.gov_count if gov else 0
            block_count = gov.block_count if gov else 0

            dur = None
            if r.end_time and r.start_time:
                dur = (r.end_time - r.start_time).total_seconds() * 1000

            item = TraceListItem(
                trace_id=r.trace_id,
                agent_id=r.agent_id,
                session_id=r.session_id,
                span_count=r.span_count,
                governance_count=gov_count,
                root_span_name=root_names.get(r.trace_id),
                start_time=r.start_time,
                end_time=r.end_time,
                total_duration_ms=dur,
                has_errors=r.error_count > 0,
                has_blocks=block_count > 0,
            )
            results.append(item)

        # Post-filter by has_blocks if requested
        if has_blocks is True:
            results = [r for r in results if r.has_blocks]
        elif has_blocks is False:
            results = [r for r in results if not r.has_blocks]

        return results


# ---------------------------------------------------------------------------
# GET /traces/{trace_id} — full trace with governance correlation
# ---------------------------------------------------------------------------

@router.get("/{trace_id}", response_model=TraceDetail)
def get_trace(
    trace_id: str,
    _user: User = Depends(require_any),
) -> TraceDetail:
    """
    Get a full trace with all spans and correlated governance decisions.

    Merges agent-reported spans (from /traces/ingest) with governance
    decisions (from /actions/evaluate) that share the same trace_id.
    """
    with db_session() as session:
        # Get all spans for this trace
        spans_stmt = (
            select(TraceSpan)
            .where(TraceSpan.trace_id == trace_id)
            .order_by(TraceSpan.start_time.asc())
        )
        span_rows = session.execute(spans_stmt).scalars().all()

        if not span_rows:
            raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

        # Get correlated governance decisions
        gov_stmt = (
            select(ActionLog)
            .where(ActionLog.trace_id == trace_id)
            .order_by(ActionLog.created_at.asc())
        )
        gov_rows = session.execute(gov_stmt).scalars().all()

        spans = [_span_to_read(r) for r in span_rows]
        decisions = [_action_to_read(r) for r in gov_rows]

        # Compute summary
        start = min(s.start_time for s in spans) if spans else None
        end_times = [s.end_time for s in spans if s.end_time]
        end = max(end_times) if end_times else None
        dur = (end - start).total_seconds() * 1000 if end and start else None

        return TraceDetail(
            trace_id=trace_id,
            agent_id=span_rows[0].agent_id if span_rows else None,
            session_id=span_rows[0].session_id if span_rows else None,
            spans=spans,
            governance_decisions=decisions,
            span_count=len(spans),
            governance_count=len(decisions),
            start_time=start,
            end_time=end,
            total_duration_ms=dur,
            has_errors=any(s.status == "error" for s in spans),
            has_blocks=any(d.decision == "block" for d in decisions),
        )


# ---------------------------------------------------------------------------
# DELETE /traces/{trace_id} — delete a trace and all its spans
# ---------------------------------------------------------------------------

@router.delete("/{trace_id}")
def delete_trace(
    trace_id: str,
    _user: User = Depends(require_operator),
) -> dict:
    """Delete all spans for a trace. Governance decisions in action_logs are not deleted."""
    with db_session() as session:
        count = session.query(TraceSpan).filter(TraceSpan.trace_id == trace_id).delete()
        if count == 0:
            raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")
    return {"status": "deleted", "trace_id": trace_id, "spans_deleted": count}
