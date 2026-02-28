"""
api/routes_notifications.py — Notification channel CRUD + test
===============================================================

Manage multi-channel notification endpoints (email, Slack, WhatsApp,
Jira, webhook) that receive alerts on governance events.
"""
from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..auth.dependencies import require_any, require_operator
from ..database import db_session
from ..encryption import encrypt_value, decrypt_value
from ..escalation.models import NotificationChannel
from ..escalation.channels import test_notification_channel
from ..schemas import (
    NotificationChannelCreate,
    NotificationChannelRead,
    NotificationChannelUpdate,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _row_to_read(ch: NotificationChannel) -> NotificationChannelRead:
    raw = ch.config_json
    if isinstance(raw, str):
        raw = decrypt_value(raw)
        raw = json.loads(raw)
    return NotificationChannelRead(
        id=ch.id,
        label=ch.label,
        channel_type=ch.channel_type,
        config_json=raw,
        on_block=ch.on_block,
        on_review=ch.on_review,
        on_auto_ks=ch.on_auto_ks,
        on_policy_change=ch.on_policy_change,
        is_active=ch.is_active,
        created_at=ch.created_at,
        last_sent_at=ch.last_sent_at,
        error_count=ch.error_count,
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=List[NotificationChannelRead])
def list_channels(
    _user=Depends(require_any),
) -> List[NotificationChannelRead]:
    """List all notification channels."""
    with db_session() as session:
        rows = session.execute(
            select(NotificationChannel).order_by(NotificationChannel.created_at.desc())
        ).scalars().all()
        return [_row_to_read(ch) for ch in rows]


@router.post("", response_model=NotificationChannelRead, status_code=201)
def create_channel(
    payload: NotificationChannelCreate,
    _user=Depends(require_operator),
) -> NotificationChannelRead:
    """Register a new notification channel."""
    with db_session() as session:
        ch = NotificationChannel(
            label=payload.label,
            channel_type=payload.channel_type,
            config_json=encrypt_value(json.dumps(payload.config_json)),
            on_block=payload.on_block,
            on_review=payload.on_review,
            on_auto_ks=payload.on_auto_ks,
            on_policy_change=payload.on_policy_change,
        )
        session.add(ch)
        session.flush()
        return _row_to_read(ch)


@router.get("/{channel_id}", response_model=NotificationChannelRead)
def get_channel(
    channel_id: int,
    _user=Depends(require_any),
) -> NotificationChannelRead:
    """Get a single notification channel by ID."""
    with db_session() as session:
        ch = session.get(NotificationChannel, channel_id)
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found.")
        return _row_to_read(ch)


@router.patch("/{channel_id}", response_model=NotificationChannelRead)
def update_channel(
    channel_id: int,
    payload: NotificationChannelUpdate,
    _user=Depends(require_operator),
) -> NotificationChannelRead:
    """Update a notification channel configuration."""
    with db_session() as session:
        ch = session.get(NotificationChannel, channel_id)
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found.")

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(status_code=400, detail="No fields to update.")

        if "config_json" in changes:
            changes["config_json"] = encrypt_value(json.dumps(changes["config_json"]))

        for field, value in changes.items():
            setattr(ch, field, value)

        session.flush()
        return _row_to_read(ch)


@router.delete("/{channel_id}")
def delete_channel(
    channel_id: int,
    _user=Depends(require_operator),
) -> dict:
    """Delete a notification channel."""
    with db_session() as session:
        ch = session.get(NotificationChannel, channel_id)
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found.")
        session.delete(ch)
        return {"status": "deleted", "channel_id": channel_id}


@router.post("/{channel_id}/test")
def test_channel(
    channel_id: int,
    _user=Depends(require_operator),
) -> dict:
    """Send a test notification through a channel to verify configuration."""
    return test_notification_channel(channel_id)
