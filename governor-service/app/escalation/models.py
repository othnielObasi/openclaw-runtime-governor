"""
escalation/models.py — DB models for the escalation subsystem
==============================================================

EscalationConfig  — per-agent or global threshold configuration
EscalationEvent   — review queue items (actions awaiting human review)
EscalationWebhook — registered webhook endpoints for notifications
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Integer, String, DateTime, Text, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class EscalationConfig(Base):
    """
    Configurable thresholds for auto-escalation and auto-kill-switch.

    scope = "*"       → global default
    scope = "agent:<id>" → per-agent override

    An admin can set:
    - auto_ks_block_threshold: how many blocks in the window trigger auto-kill-switch
    - auto_ks_risk_threshold:  average risk score that triggers auto-kill-switch
    - auto_ks_window_size:     how many recent actions to consider
    - review_risk_threshold:   risk score at which "allow" promotes to "review"
    - escalation_webhook_url:  optional webhook to hit on escalation (deprecated — use EscalationWebhook)
    """

    __tablename__ = "escalation_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scope: Mapped[str] = mapped_column(String(256), unique=True, index=True, default="*")

    auto_ks_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_ks_block_threshold: Mapped[int] = mapped_column(Integer, default=3)
    auto_ks_risk_threshold: Mapped[int] = mapped_column(Integer, default=82)
    auto_ks_window_size: Mapped[int] = mapped_column(Integer, default=10)

    review_risk_threshold: Mapped[int] = mapped_column(Integer, default=70)

    # Review auto-expiry: pending events expire after this many minutes (0 = never)
    review_expiry_minutes: Mapped[int] = mapped_column(Integer, default=30)

    notify_on_block: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_review: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_auto_ks: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class EscalationEvent(Base):
    """
    Review queue item — created when a decision is "block" or "review".

    Human operators approve or reject these to close the escalation.
    status: pending | approved | rejected | expired | auto_resolved
    severity: critical | high | medium | low
    """

    __tablename__ = "escalation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    # Link to original action
    action_log_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    tool: Mapped[str] = mapped_column(String(128), index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Escalation details
    trigger: Mapped[str] = mapped_column(String(64), index=True)
    # triggers: "policy_block" | "policy_review" | "auto_ks" | "chain_escalation" | "risk_threshold" | "manual"
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    # severity: critical | high | medium | low
    decision: Mapped[str] = mapped_column(String(32))  # the original decision
    risk_score: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    policy_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chain_pattern: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Resolution
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    # status: pending | approved | rejected | expired | auto_resolved
    resolved_by: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Auto-expiry: if set, pending events older than this are auto-expired
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)


class EscalationWebhook(Base):
    """
    Registered webhook endpoints — notified on escalation events.

    Admins register URLs that receive POST payloads when actions are
    blocked, sent for review, or the kill switch auto-engages.
    """

    __tablename__ = "escalation_webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    url: Mapped[str] = mapped_column(String(1024))
    label: Mapped[str] = mapped_column(String(256), default="")

    # What to notify on
    on_block: Mapped[bool] = mapped_column(Boolean, default=True)
    on_review: Mapped[bool] = mapped_column(Boolean, default=True)
    on_auto_ks: Mapped[bool] = mapped_column(Boolean, default=True)

    # Auth header (e.g. "Bearer <token>") — encrypted at rest in production
    auth_header: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class NotificationChannel(Base):
    """
    Multi-channel notification endpoint — supports email, Slack, WhatsApp, Jira,
    and generic webhook.

    channel_type: "email" | "slack" | "whatsapp" | "jira" | "webhook"
    config_json stores channel-specific configuration:

    Email:    {"smtp_host","smtp_port","from_addr","to_addrs":[...],"use_tls":true}
    Slack:    {"webhook_url":"https://hooks.slack.com/..."} or {"bot_token":"xoxb-...","channel":"#alerts"}
    WhatsApp: {"api_url":"https://graph.facebook.com/v17.0/...","phone_number_id":"...","access_token":"...","to_numbers":[...]}
    Jira:     {"base_url":"https://myorg.atlassian.net","project_key":"GOV","issue_type":"Task","email":"...","api_token":"..."}
    Webhook:  {"url":"...","auth_header":"Bearer ..."}
    """

    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    label: Mapped[str] = mapped_column(String(256), default="")
    channel_type: Mapped[str] = mapped_column(String(32), index=True)
    # channel_type: email | slack | whatsapp | jira | webhook

    config_json: Mapped[str] = mapped_column(Text)  # JSON — channel-specific config

    # What to notify on
    on_block: Mapped[bool] = mapped_column(Boolean, default=True)
    on_review: Mapped[bool] = mapped_column(Boolean, default=True)
    on_auto_ks: Mapped[bool] = mapped_column(Boolean, default=True)
    on_policy_change: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    last_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
