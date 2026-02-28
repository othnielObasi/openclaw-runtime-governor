"""
escalation/channels.py — Multi-channel notification dispatch
=============================================================

Dispatches notifications to configured channels:
  - Email   (SMTP / SendGrid / SES)
  - Slack   (Incoming webhook or Bot API)
  - WhatsApp (Meta Cloud API)
  - Jira    (Create issue via REST API)
  - Webhook (Generic HTTP POST — existing path)

Each channel type has a dedicated dispatcher that reads its
config_json and sends the notification.  Failures are logged
but never block the evaluation pipeline.
"""
from __future__ import annotations

import json
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import httpx
from sqlalchemy import select

from ..database import db_session
from ..encryption import decrypt_value
from .models import NotificationChannel

logger = logging.getLogger("governor.channels")


# ---------------------------------------------------------------------------
# Channel dispatchers
# ---------------------------------------------------------------------------

def _send_email(config: dict, payload: dict, label: str) -> bool:
    """Send notification via SMTP email."""
    try:
        host = config.get("smtp_host", "localhost")
        port = int(config.get("smtp_port", 587))
        from_addr = config.get("from_addr", "governor@openclaw.dev")
        to_addrs = config.get("to_addrs", [])
        use_tls = config.get("use_tls", True)
        username = config.get("username")
        password = config.get("password")

        if not to_addrs:
            logger.warning("Email channel %r has no to_addrs configured", label)
            return False

        subject = f"[OpenClaw Governor] {payload.get('event', 'Notification')}"
        body_lines = [
            f"Event: {payload.get('event', 'unknown')}",
            f"Tool: {payload.get('tool', 'N/A')}",
            f"Decision: {payload.get('decision', 'N/A')}",
            f"Risk Score: {payload.get('risk_score', 'N/A')}",
            f"Explanation: {payload.get('explanation', '')}",
            f"Agent: {payload.get('agent_id', 'N/A')}",
            f"Timestamp: {payload.get('timestamp', '')}",
        ]
        if payload.get("policy_ids"):
            body_lines.append(f"Policies: {', '.join(payload['policy_ids'])}")
        if payload.get("chain_pattern"):
            body_lines.append(f"Chain Pattern: {payload['chain_pattern']}")
        if payload.get("reason"):
            body_lines.append(f"Reason: {payload['reason']}")

        msg = MIMEMultipart()
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)
        msg["Subject"] = subject
        msg.attach(MIMEText("\n".join(body_lines), "plain"))

        if use_tls:
            server = smtplib.SMTP(host, port, timeout=10)
            server.starttls()
        else:
            server = smtplib.SMTP(host, port, timeout=10)

        if username and password:
            server.login(username, password)
        server.sendmail(from_addr, to_addrs, msg.as_string())
        server.quit()

        logger.info("Email channel %r sent to %s", label, to_addrs)
        return True
    except Exception as exc:
        logger.warning("Email channel %r failed: %s", label, exc)
        return False


def _send_slack(config: dict, payload: dict, label: str) -> bool:
    """Send notification via Slack incoming webhook or Bot API."""
    try:
        webhook_url = config.get("webhook_url")
        bot_token = config.get("bot_token")
        channel = config.get("channel")

        event = payload.get("event", "notification")
        text_lines = [
            f":rotating_light: *OpenClaw Governor — {event}*",
            f"*Tool:* {payload.get('tool', 'N/A')}",
            f"*Decision:* {payload.get('decision', 'N/A')}",
            f"*Risk Score:* {payload.get('risk_score', 'N/A')}",
            f"*Explanation:* {payload.get('explanation', '')}",
        ]
        if payload.get("agent_id"):
            text_lines.append(f"*Agent:* {payload['agent_id']}")
        if payload.get("reason"):
            text_lines.append(f"*Reason:* {payload['reason']}")
        text = "\n".join(text_lines)

        with httpx.Client(timeout=10.0) as client:
            if webhook_url:
                resp = client.post(webhook_url, json={"text": text})
            elif bot_token and channel:
                resp = client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={"channel": channel, "text": text},
                )
            else:
                logger.warning("Slack channel %r missing webhook_url or bot_token+channel", label)
                return False

            if resp.status_code >= 400:
                logger.warning("Slack channel %r returned %d", label, resp.status_code)
                return False

        logger.info("Slack channel %r dispatched", label)
        return True
    except Exception as exc:
        logger.warning("Slack channel %r failed: %s", label, exc)
        return False


def _send_whatsapp(config: dict, payload: dict, label: str) -> bool:
    """Send notification via WhatsApp Business Cloud API (Meta)."""
    try:
        api_url = config.get("api_url")
        phone_number_id = config.get("phone_number_id")
        access_token = config.get("access_token")
        to_numbers = config.get("to_numbers", [])

        if not access_token or not to_numbers:
            logger.warning("WhatsApp channel %r missing access_token or to_numbers", label)
            return False

        # Build message
        event = payload.get("event", "notification")
        body = (
            f"🔒 OpenClaw Governor — {event}\n"
            f"Tool: {payload.get('tool', 'N/A')}\n"
            f"Decision: {payload.get('decision', 'N/A')}\n"
            f"Risk: {payload.get('risk_score', 'N/A')}\n"
            f"Explanation: {payload.get('explanation', '')}"
        )
        if payload.get("reason"):
            body += f"\nReason: {payload['reason']}"

        url = api_url or f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=10.0) as client:
            for number in to_numbers:
                resp = client.post(
                    url,
                    headers=headers,
                    json={
                        "messaging_product": "whatsapp",
                        "to": number,
                        "type": "text",
                        "text": {"body": body},
                    },
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "WhatsApp channel %r to %s returned %d: %s",
                        label, number, resp.status_code, resp.text[:200],
                    )

        logger.info("WhatsApp channel %r dispatched to %d numbers", label, len(to_numbers))
        return True
    except Exception as exc:
        logger.warning("WhatsApp channel %r failed: %s", label, exc)
        return False


def _create_jira_ticket(config: dict, payload: dict, label: str) -> bool:
    """Create a Jira issue for a governance event."""
    try:
        base_url = config.get("base_url", "").rstrip("/")
        project_key = config.get("project_key")
        issue_type = config.get("issue_type", "Task")
        email = config.get("email")
        api_token = config.get("api_token")

        if not all([base_url, project_key, email, api_token]):
            logger.warning("Jira channel %r missing required config", label)
            return False

        event = payload.get("event", "notification")
        summary = f"[OpenClaw Governor] {event} — {payload.get('tool', 'unknown')}"

        desc_lines = [
            f"*Event:* {event}",
            f"*Tool:* {payload.get('tool', 'N/A')}",
            f"*Decision:* {payload.get('decision', 'N/A')}",
            f"*Risk Score:* {payload.get('risk_score', 'N/A')}",
            f"*Explanation:* {payload.get('explanation', '')}",
            f"*Agent:* {payload.get('agent_id', 'N/A')}",
            f"*Timestamp:* {payload.get('timestamp', '')}",
        ]
        if payload.get("policy_ids"):
            desc_lines.append(f"*Policies:* {', '.join(payload['policy_ids'])}")
        if payload.get("chain_pattern"):
            desc_lines.append(f"*Chain Pattern:* {payload['chain_pattern']}")
        if payload.get("reason"):
            desc_lines.append(f"*Kill-switch reason:* {payload['reason']}")

        description = "\n".join(desc_lines)

        # Determine priority from risk score
        risk = payload.get("risk_score", 50)
        if risk >= 80:
            priority = "Critical"
        elif risk >= 60:
            priority = "High"
        elif risk >= 40:
            priority = "Medium"
        else:
            priority = "Low"

        jira_payload = {
            "fields": {
                "project": {"key": project_key},
                "issuetype": {"name": issue_type},
                "summary": summary,
                "description": description,
                "priority": {"name": priority},
                "labels": ["openclaw-governor", "automated"],
            }
        }

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{base_url}/rest/api/2/issue",
                auth=(email, api_token),
                json=jira_payload,
            )
            if resp.status_code >= 400:
                logger.warning(
                    "Jira channel %r returned %d: %s",
                    label, resp.status_code, resp.text[:300],
                )
                return False
            issue_key = resp.json().get("key", "unknown")
            logger.info("Jira channel %r created issue %s", label, issue_key)
            return True
    except Exception as exc:
        logger.warning("Jira channel %r failed: %s", label, exc)
        return False


def _send_generic_webhook(config: dict, payload: dict, label: str) -> bool:
    """Send generic HTTP POST webhook."""
    url = config.get("url")
    auth_header = config.get("auth_header")
    if not url:
        logger.warning("Webhook channel %r has no url configured", label)
        return False

    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.warning(
                    "Webhook channel %r (%s) returned %d",
                    label, url, resp.status_code,
                )
                return False
            logger.info("Webhook channel %r dispatched → %d", label, resp.status_code)
            return True
    except Exception as exc:
        logger.warning("Webhook channel %r (%s) failed: %s", label, url, exc)
        return False


# ---------------------------------------------------------------------------
# Channel dispatcher map
# ---------------------------------------------------------------------------

_DISPATCHERS = {
    "email": _send_email,
    "slack": _send_slack,
    "whatsapp": _send_whatsapp,
    "jira": _create_jira_ticket,
    "webhook": _send_generic_webhook,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def dispatch_notification_channels(
    event_type: str,
    payload: dict,
) -> int:
    """
    Send notifications to all active channels matching the event type.

    event_type: "block" | "review" | "auto_ks" | "policy_change"

    Returns the number of channels that succeeded.
    """
    sent = 0
    try:
        with db_session() as session:
            stmt = select(NotificationChannel).where(
                NotificationChannel.is_active == True  # noqa: E712
            )
            channels = session.execute(stmt).scalars().all()

            for ch in channels:
                # Filter by event type
                if event_type == "block" and not ch.on_block:
                    continue
                if event_type == "review" and not ch.on_review:
                    continue
                if event_type == "auto_ks" and not ch.on_auto_ks:
                    continue
                if event_type == "policy_change" and not ch.on_policy_change:
                    continue

                config = json.loads(ch.config_json) if isinstance(ch.config_json, str) else ch.config_json
                # Decrypt secrets if encryption is enabled
                raw = ch.config_json if isinstance(ch.config_json, str) else json.dumps(ch.config_json)
                decrypted = decrypt_value(raw)
                try:
                    config = json.loads(decrypted)
                except (json.JSONDecodeError, TypeError):
                    pass  # config already parsed above
                dispatcher = _DISPATCHERS.get(ch.channel_type)
                if not dispatcher:
                    logger.warning("Unknown channel type %r for channel %r", ch.channel_type, ch.label)
                    continue

                success = dispatcher(config, payload, ch.label)

                # Track last_sent_at and error_count
                if success:
                    ch.last_sent_at = datetime.now(timezone.utc)
                    sent += 1
                else:
                    ch.error_count = (ch.error_count or 0) + 1

    except Exception as exc:
        logger.warning("Failed to dispatch notification channels: %s", exc)

    return sent


def test_notification_channel(channel_id: int) -> dict:
    """Send a test notification to a specific channel. Returns success status."""
    test_payload = {
        "event": "test_notification",
        "tool": "test",
        "decision": "allow",
        "risk_score": 0,
        "explanation": "This is a test notification from OpenClaw Governor.",
        "agent_id": "governor-test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with db_session() as session:
        ch = session.get(NotificationChannel, channel_id)
        if not ch:
            return {"success": False, "error": "Channel not found"}

        config = json.loads(ch.config_json) if isinstance(ch.config_json, str) else ch.config_json
        # Decrypt secrets if encryption is enabled
        raw = ch.config_json if isinstance(ch.config_json, str) else json.dumps(ch.config_json)
        raw = decrypt_value(raw)
        try:
            config = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass  # already parsed above
        dispatcher = _DISPATCHERS.get(ch.channel_type)
        if not dispatcher:
            return {"success": False, "error": f"Unknown channel type: {ch.channel_type}"}

        success = dispatcher(config, test_payload, ch.label)
        if success:
            ch.last_sent_at = datetime.now(timezone.utc)

        return {
            "success": success,
            "channel_id": channel_id,
            "channel_type": ch.channel_type,
            "label": ch.label,
        }
