"""
routes_conversations.py — Conversation & interaction logging for SaaS audit trails
====================================================================================
Opt-in endpoints that let agent SDKs push full conversation context —
user prompts, agent reasoning, and final responses — so SaaS customers
get complete forensic audit trails.

The Governor's core evaluation path (POST /actions/evaluate) is unchanged.
These endpoints add *supplementary* context that enriches investigations:

  User asked X → Agent reasoned Y → Chose tool Z → Governor decided → Result W

Prompt and response text is encrypted at rest when GOVERNOR_ENCRYPTION_KEY is set.
"""
import json
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc

from ..auth.dependencies import require_any, require_operator
from ..database import db_session
from ..encryption import encrypt_value, decrypt_value
from ..models import ConversationTurn, ActionLog, User
from ..schemas import (
    ConversationTurnCreate,
    ConversationTurnBatch,
    ConversationTurnRead,
    ConversationSummary,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ---------------------------------------------------------------------------
# Ingest a conversation turn
# ---------------------------------------------------------------------------

@router.post("/turns", status_code=201)
def create_turn(
    payload: ConversationTurnCreate,
    _user: User = Depends(require_operator),
) -> dict:
    """Record a conversation turn — user prompt, agent reasoning, agent response.

    All text fields (prompt, agent_reasoning, agent_response) are encrypted at
    rest when GOVERNOR_ENCRYPTION_KEY is configured.

    Requires operator or admin credentials.
    """
    now = datetime.now(timezone.utc)

    with db_session() as session:
        row = ConversationTurn(
            conversation_id=payload.conversation_id,
            turn_index=payload.turn_index or 0,
            agent_id=payload.agent_id,
            session_id=payload.session_id,
            user_id=payload.user_id,
            channel=payload.channel,
            # Encrypt PII / sensitive text at rest
            prompt_encrypted=encrypt_value(payload.prompt) if payload.prompt else None,
            agent_reasoning_encrypted=encrypt_value(payload.agent_reasoning) if payload.agent_reasoning else None,
            agent_response_encrypted=encrypt_value(payload.agent_response) if payload.agent_response else None,
            tool_plan_json=json.dumps(payload.tool_plan) if payload.tool_plan else None,
            model_id=payload.model_id,
            prompt_tokens=payload.prompt_tokens,
            completion_tokens=payload.completion_tokens,
            created_at=now,
        )
        session.add(row)
        session.flush()
        turn_id = row.id

    return {"id": turn_id, "conversation_id": payload.conversation_id, "created_at": now.isoformat()}


# ---------------------------------------------------------------------------
# Batch ingest
# ---------------------------------------------------------------------------

@router.post("/turns/batch", status_code=201)
def create_turns_batch(
    payload: ConversationTurnBatch,
    _user: User = Depends(require_operator),
) -> dict:
    """Batch-ingest multiple conversation turns in one call."""
    now = datetime.now(timezone.utc)
    ids: list[int] = []

    with db_session() as session:
        for t in payload.turns:
            row = ConversationTurn(
                conversation_id=t.conversation_id,
                turn_index=t.turn_index or 0,
                agent_id=t.agent_id,
                session_id=t.session_id,
                user_id=t.user_id,
                channel=t.channel,
                prompt_encrypted=encrypt_value(t.prompt) if t.prompt else None,
                agent_reasoning_encrypted=encrypt_value(t.agent_reasoning) if t.agent_reasoning else None,
                agent_response_encrypted=encrypt_value(t.agent_response) if t.agent_response else None,
                tool_plan_json=json.dumps(t.tool_plan) if t.tool_plan else None,
                model_id=t.model_id,
                prompt_tokens=t.prompt_tokens,
                completion_tokens=t.completion_tokens,
                created_at=now,
            )
            session.add(row)
            session.flush()
            ids.append(row.id)

    return {"created": len(ids), "ids": ids}


# ---------------------------------------------------------------------------
# List / search turns
# ---------------------------------------------------------------------------

@router.get("/turns", response_model=List[ConversationTurnRead])
def list_turns(
    conversation_id: Optional[str] = Query(None, description="Filter by conversation ID"),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: User = Depends(require_any),
) -> list:
    """List conversation turns with optional filters. Text is decrypted on read."""
    with db_session() as session:
        stmt = select(ConversationTurn).order_by(desc(ConversationTurn.created_at))
        if conversation_id:
            stmt = stmt.where(ConversationTurn.conversation_id == conversation_id)
        if agent_id:
            stmt = stmt.where(ConversationTurn.agent_id == agent_id)
        if session_id:
            stmt = stmt.where(ConversationTurn.session_id == session_id)
        if user_id:
            stmt = stmt.where(ConversationTurn.user_id == user_id)
        stmt = stmt.offset(offset).limit(limit)

        rows = session.execute(stmt).scalars().all()
        return [_turn_to_read(r) for r in rows]


# ---------------------------------------------------------------------------
# Get one turn
# ---------------------------------------------------------------------------

@router.get("/turns/{turn_id}", response_model=ConversationTurnRead)
def get_turn(
    turn_id: int,
    _user: User = Depends(require_any),
) -> dict:
    """Get a single conversation turn by ID."""
    with db_session() as session:
        row = session.get(ConversationTurn, turn_id)
        if not row:
            raise HTTPException(404, "Turn not found")
        return _turn_to_read(row)


# ---------------------------------------------------------------------------
# Conversation timeline — turns + governed actions interleaved
# ---------------------------------------------------------------------------

@router.get("/{conversation_id}/timeline")
def conversation_timeline(
    conversation_id: str,
    _user: User = Depends(require_any),
) -> dict:
    """Return a chronological timeline of conversation turns and governed actions
    for a conversation, interleaved by timestamp.

    This is the key forensic view — shows exactly:
      User said X → Agent planned Y → Governor evaluated Z → Agent responded W
    """
    with db_session() as session:
        # Get turns
        turns = (
            session.execute(
                select(ConversationTurn)
                .where(ConversationTurn.conversation_id == conversation_id)
                .order_by(ConversationTurn.created_at)
            )
            .scalars()
            .all()
        )

        # Get related actions — match by conversation_id stored on ActionLog
        actions = (
            session.execute(
                select(ActionLog)
                .where(ActionLog.conversation_id == conversation_id)
                .order_by(ActionLog.created_at)
            )
            .scalars()
            .all()
        )

        timeline: list[dict] = []

        for t in turns:
            timeline.append({
                "type": "turn",
                "timestamp": t.created_at.isoformat() if t.created_at else None,
                "turn_id": t.id,
                "turn_index": t.turn_index,
                "prompt": decrypt_value(t.prompt_encrypted) if t.prompt_encrypted else None,
                "agent_reasoning": decrypt_value(t.agent_reasoning_encrypted) if t.agent_reasoning_encrypted else None,
                "agent_response": decrypt_value(t.agent_response_encrypted) if t.agent_response_encrypted else None,
                "tool_plan": json.loads(t.tool_plan_json) if t.tool_plan_json else None,
                "model_id": t.model_id,
            })

        for a in actions:
            timeline.append({
                "type": "action",
                "timestamp": a.created_at.isoformat() if a.created_at else None,
                "action_id": a.id,
                "tool": a.tool,
                "decision": a.decision,
                "risk_score": a.risk_score,
                "explanation": a.explanation,
                "agent_id": a.agent_id,
            })

        # Sort by timestamp
        timeline.sort(key=lambda e: e.get("timestamp") or "")

        return {
            "conversation_id": conversation_id,
            "turns": len(turns),
            "actions": len(actions),
            "timeline": timeline,
        }


# ---------------------------------------------------------------------------
# Conversation list (grouped)
# ---------------------------------------------------------------------------

@router.get("", response_model=List[ConversationSummary])
def list_conversations(
    agent_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: User = Depends(require_any),
) -> list:
    """List distinct conversations with turn counts and time range."""
    with db_session() as session:
        stmt = (
            select(
                ConversationTurn.conversation_id,
                ConversationTurn.agent_id,
                ConversationTurn.user_id,
                ConversationTurn.session_id,
                func.count(ConversationTurn.id).label("turn_count"),
                func.min(ConversationTurn.created_at).label("first_turn_at"),
                func.max(ConversationTurn.created_at).label("last_turn_at"),
            )
            .group_by(
                ConversationTurn.conversation_id,
                ConversationTurn.agent_id,
                ConversationTurn.user_id,
                ConversationTurn.session_id,
            )
            .order_by(desc("last_turn_at"))
        )
        if agent_id:
            stmt = stmt.where(ConversationTurn.agent_id == agent_id)
        if user_id:
            stmt = stmt.where(ConversationTurn.user_id == user_id)
        stmt = stmt.offset(offset).limit(limit)

        rows = session.execute(stmt).all()

        # Count governed actions per conversation
        result = []
        for r in rows:
            action_count = session.scalar(
                select(func.count(ActionLog.id))
                .where(ActionLog.conversation_id == r.conversation_id)
            ) or 0

            result.append(
                ConversationSummary(
                    conversation_id=r.conversation_id,
                    agent_id=r.agent_id,
                    user_id=r.user_id,
                    session_id=r.session_id,
                    turn_count=r.turn_count,
                    action_count=action_count,
                    first_turn_at=r.first_turn_at,
                    last_turn_at=r.last_turn_at,
                )
            )
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _turn_to_read(row: ConversationTurn) -> ConversationTurnRead:
    """Convert a DB row to a read schema, decrypting text fields."""
    return ConversationTurnRead(
        id=row.id,
        conversation_id=row.conversation_id,
        turn_index=row.turn_index,
        agent_id=row.agent_id,
        session_id=row.session_id,
        user_id=row.user_id,
        channel=row.channel,
        prompt=decrypt_value(row.prompt_encrypted) if row.prompt_encrypted else None,
        agent_reasoning=decrypt_value(row.agent_reasoning_encrypted) if row.agent_reasoning_encrypted else None,
        agent_response=decrypt_value(row.agent_response_encrypted) if row.agent_response_encrypted else None,
        tool_plan=json.loads(row.tool_plan_json) if row.tool_plan_json else None,
        model_id=row.model_id,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        created_at=row.created_at,
    )



