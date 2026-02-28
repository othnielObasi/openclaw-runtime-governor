"""
tests/test_escalation.py — Tests for the escalation subsystem
==============================================================

Covers: config CRUD, review queue lifecycle, auto-KS thresholds,
severity computation, webhook management, hold/wait endpoint,
auto-expiry, and review_expiry_minutes config.
"""
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.escalation.engine import compute_severity, get_escalation_config
from app.escalation.models import EscalationConfig, EscalationEvent, EscalationWebhook
from app.database import db_session

client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cleanup_escalation_tables():
    """Remove all escalation rows to keep tests isolated."""
    with db_session() as session:
        session.query(EscalationEvent).delete()
        session.query(EscalationConfig).delete()
        session.query(EscalationWebhook).delete()


# ═══════════════════════════════════════════════════════════════════════════
# Severity computation (unit)
# ═══════════════════════════════════════════════════════════════════════════

class TestSeverityComputation:
    def test_critical(self):
        assert compute_severity(95, "block", None) == "critical"

    def test_high_block(self):
        assert compute_severity(75, "block", None) == "high"

    def test_high_risk(self):
        assert compute_severity(85, "review", None) == "high"

    def test_medium_chain(self):
        assert compute_severity(40, "review", "browse-then-exfil") == "medium"

    def test_medium_risk(self):
        assert compute_severity(55, "review", None) == "medium"

    def test_low(self):
        assert compute_severity(30, "review", None) == "low"


# ═══════════════════════════════════════════════════════════════════════════
# Config resolution (unit)
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigResolution:
    def test_defaults_when_no_db_config(self, admin_token):
        _cleanup_escalation_tables()
        config = get_escalation_config("nonexistent-agent")
        assert config["auto_ks_enabled"] is False
        assert config["auto_ks_block_threshold"] == 3
        assert config["auto_ks_risk_threshold"] == 82

    def test_global_config_loaded(self, admin_token):
        _cleanup_escalation_tables()
        # Create global config
        resp = client.post(
            "/escalation/config",
            json={"scope": "*", "auto_ks_enabled": True, "auto_ks_block_threshold": 5},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 201

        config = get_escalation_config(None)
        assert config["auto_ks_enabled"] is True
        assert config["auto_ks_block_threshold"] == 5
        _cleanup_escalation_tables()

    def test_agent_override_takes_priority(self, admin_token):
        _cleanup_escalation_tables()
        # Global
        client.post(
            "/escalation/config",
            json={"scope": "*", "auto_ks_block_threshold": 5},
            headers=_headers(admin_token),
        )
        # Per-agent
        client.post(
            "/escalation/config",
            json={"scope": "agent:test-agent", "auto_ks_block_threshold": 2},
            headers=_headers(admin_token),
        )

        config = get_escalation_config("test-agent")
        assert config["auto_ks_block_threshold"] == 2
        _cleanup_escalation_tables()


# ═══════════════════════════════════════════════════════════════════════════
# Config CRUD (API)
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigAPI:
    def test_create_and_list(self, admin_token):
        _cleanup_escalation_tables()
        resp = client.post(
            "/escalation/config",
            json={"scope": "*", "auto_ks_enabled": True, "auto_ks_risk_threshold": 75},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["scope"] == "*"
        assert data["auto_ks_enabled"] is True
        assert data["auto_ks_risk_threshold"] == 75

        resp = client.get("/escalation/config", headers=_headers(admin_token))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
        _cleanup_escalation_tables()

    def test_duplicate_scope_rejected(self, admin_token):
        _cleanup_escalation_tables()
        client.post(
            "/escalation/config",
            json={"scope": "*"},
            headers=_headers(admin_token),
        )
        resp = client.post(
            "/escalation/config",
            json={"scope": "*"},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 409
        _cleanup_escalation_tables()

    def test_update_config(self, admin_token):
        _cleanup_escalation_tables()
        client.post(
            "/escalation/config",
            json={"scope": "*", "auto_ks_block_threshold": 3},
            headers=_headers(admin_token),
        )
        resp = client.put(
            "/escalation/config/*",
            json={"auto_ks_block_threshold": 7},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["auto_ks_block_threshold"] == 7
        _cleanup_escalation_tables()

    def test_delete_config(self, admin_token):
        _cleanup_escalation_tables()
        client.post(
            "/escalation/config",
            json={"scope": "agent:del-test"},
            headers=_headers(admin_token),
        )
        resp = client.delete(
            "/escalation/config/agent:del-test",
            headers=_headers(admin_token),
        )
        assert resp.status_code == 204

        resp = client.get(
            "/escalation/config/agent:del-test",
            headers=_headers(admin_token),
        )
        assert resp.status_code == 404
        _cleanup_escalation_tables()


# ═══════════════════════════════════════════════════════════════════════════
# Review queue (API)
# ═══════════════════════════════════════════════════════════════════════════

class TestReviewQueue:
    def test_evaluate_block_creates_escalation(self, admin_token):
        """A blocked action should create an escalation event in the review queue."""
        _cleanup_escalation_tables()
        resp = client.post(
            "/actions/evaluate",
            json={
                "tool": "shell",
                "args": {"cmd": "rm -rf /"},
                "context": {"agent_id": "test-agent"},
            },
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "block"
        assert data.get("escalation_id") is not None

        # Check queue
        resp = client.get(
            "/escalation/queue?status=pending",
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) >= 1
        assert events[0]["status"] == "pending"
        assert events[0]["decision"] == "block"
        _cleanup_escalation_tables()

    def test_resolve_event(self, admin_token):
        """Operators can approve or reject pending escalation events."""
        _cleanup_escalation_tables()
        # Create a block to get an escalation event
        client.post(
            "/actions/evaluate",
            json={
                "tool": "shell",
                "args": {"cmd": "rm -rf /"},
                "context": {"agent_id": "resolve-test"},
            },
            headers=_headers(admin_token),
        )

        # Get the pending event
        resp = client.get(
            "/escalation/queue?status=pending",
            headers=_headers(admin_token),
        )
        events = resp.json()
        assert len(events) >= 1
        event_id = events[0]["id"]

        # Resolve it
        resp = client.post(
            f"/escalation/queue/{event_id}/resolve",
            json={"status": "rejected", "note": "Confirmed dangerous command"},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
        assert resp.json()["resolved_by"] == "admin"
        assert resp.json()["resolution_note"] == "Confirmed dangerous command"
        _cleanup_escalation_tables()

    def test_cannot_resolve_already_resolved(self, admin_token):
        _cleanup_escalation_tables()
        client.post(
            "/actions/evaluate",
            json={
                "tool": "shell",
                "args": {"cmd": "rm -rf /"},
                "context": {"agent_id": "double-resolve-test"},
            },
            headers=_headers(admin_token),
        )
        resp = client.get("/escalation/queue?status=pending", headers=_headers(admin_token))
        event_id = resp.json()[0]["id"]

        # Resolve once
        client.post(
            f"/escalation/queue/{event_id}/resolve",
            json={"status": "approved"},
            headers=_headers(admin_token),
        )
        # Try again
        resp = client.post(
            f"/escalation/queue/{event_id}/resolve",
            json={"status": "rejected"},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 409
        _cleanup_escalation_tables()

    def test_queue_stats(self, admin_token):
        _cleanup_escalation_tables()
        resp = client.get("/escalation/queue/stats", headers=_headers(admin_token))
        assert resp.status_code == 200
        stats = resp.json()
        assert "total" in stats
        assert "pending" in stats
        assert "critical" in stats
        _cleanup_escalation_tables()

    def test_bulk_resolve(self, admin_token):
        _cleanup_escalation_tables()
        # Create two blocked events
        for _ in range(2):
            client.post(
                "/actions/evaluate",
                json={
                    "tool": "shell",
                    "args": {"cmd": "rm -rf /"},
                    "context": {"agent_id": "bulk-test"},
                },
                headers=_headers(admin_token),
            )

        resp = client.get("/escalation/queue?status=pending", headers=_headers(admin_token))
        ids = [e["id"] for e in resp.json()]
        assert len(ids) >= 2

        resp = client.post(
            "/escalation/queue/bulk-resolve",
            json=ids[:2],
            params={"status": "rejected"},
            headers=_headers(admin_token),
        )
        # Bulk resolve with body
        resp = client.post(
            "/escalation/queue/bulk-resolve",
            json=ids[:2],
            headers=_headers(admin_token),
            params={"event_ids": ids[:2]},
        )
        _cleanup_escalation_tables()

    def test_escalation_severity_in_response(self, admin_token):
        """The ActionDecision response should include escalation severity."""
        _cleanup_escalation_tables()
        resp = client.post(
            "/actions/evaluate",
            json={
                "tool": "shell",
                "args": {"cmd": "rm -rf /"},
                "context": {"agent_id": "sev-test"},
            },
            headers=_headers(admin_token),
        )
        data = resp.json()
        assert data["escalation_severity"] in ("critical", "high", "medium", "low")
        _cleanup_escalation_tables()


# ═══════════════════════════════════════════════════════════════════════════
# Webhook CRUD (API)
# ═══════════════════════════════════════════════════════════════════════════

class TestWebhookAPI:
    def test_create_and_list(self, admin_token):
        _cleanup_escalation_tables()
        resp = client.post(
            "/escalation/webhooks",
            json={
                "url": "https://hooks.example.com/governor",
                "label": "Slack alerts",
                "on_block": True,
                "on_review": False,
                "on_auto_ks": True,
            },
            headers=_headers(admin_token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://hooks.example.com/governor"
        assert data["on_review"] is False

        resp = client.get("/escalation/webhooks", headers=_headers(admin_token))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
        _cleanup_escalation_tables()

    def test_update_webhook(self, admin_token):
        _cleanup_escalation_tables()
        resp = client.post(
            "/escalation/webhooks",
            json={"url": "https://example.com/hook", "label": "Test"},
            headers=_headers(admin_token),
        )
        wh_id = resp.json()["id"]

        resp = client.put(
            f"/escalation/webhooks/{wh_id}",
            json={"label": "Updated", "is_active": False},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["label"] == "Updated"
        assert resp.json()["is_active"] is False
        _cleanup_escalation_tables()

    def test_delete_webhook(self, admin_token):
        _cleanup_escalation_tables()
        resp = client.post(
            "/escalation/webhooks",
            json={"url": "https://example.com/del-hook"},
            headers=_headers(admin_token),
        )
        wh_id = resp.json()["id"]

        resp = client.delete(
            f"/escalation/webhooks/{wh_id}",
            headers=_headers(admin_token),
        )
        assert resp.status_code == 204
        _cleanup_escalation_tables()


# ═══════════════════════════════════════════════════════════════════════════
# Allowed actions don't create escalation events
# ═══════════════════════════════════════════════════════════════════════════

class TestNoEscalationOnAllow:
    def test_allowed_action_no_escalation(self, admin_token):
        _cleanup_escalation_tables()
        resp = client.post(
            "/actions/evaluate",
            json={
                "tool": "http_request",
                "args": {"url": "http://localhost/health"},
                "context": {"agent_id": "safe-agent"},
            },
            headers=_headers(admin_token),
        )
        data = resp.json()
        assert data["decision"] == "allow"
        assert data.get("escalation_id") is None

        resp = client.get("/escalation/queue", headers=_headers(admin_token))
        assert len(resp.json()) == 0
        _cleanup_escalation_tables()


# ═══════════════════════════════════════════════════════════════════════════
# Review expiry config field
# ═══════════════════════════════════════════════════════════════════════════

class TestReviewExpiryConfig:
    def test_config_includes_review_expiry_minutes(self, admin_token):
        _cleanup_escalation_tables()
        resp = client.post(
            "/escalation/config",
            json={"scope": "*", "review_expiry_minutes": 45},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["review_expiry_minutes"] == 45
        _cleanup_escalation_tables()

    def test_config_default_expiry_30(self, admin_token):
        _cleanup_escalation_tables()
        resp = client.post(
            "/escalation/config",
            json={"scope": "*"},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 201
        assert resp.json()["review_expiry_minutes"] == 30
        _cleanup_escalation_tables()

    def test_engine_defaults_include_expiry(self):
        _cleanup_escalation_tables()
        config = get_escalation_config("no-agent")
        assert "review_expiry_minutes" in config
        assert config["review_expiry_minutes"] == 30
        _cleanup_escalation_tables()


# ═══════════════════════════════════════════════════════════════════════════
# Hold endpoint
# ═══════════════════════════════════════════════════════════════════════════

class TestHoldEndpoint:
    def _create_pending_event(self):
        """Insert a pending escalation event directly in DB."""
        with db_session() as session:
            ev = EscalationEvent(
                tool="shell",
                agent_id="test-agent",
                session_id="sess-1",
                trigger="policy_review",
                severity="medium",
                decision="review",
                risk_score=65,
                explanation="Needs review",
                status="pending",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            session.add(ev)
            session.flush()
            return ev.id

    def test_hold_returns_on_resolved(self, admin_token):
        _cleanup_escalation_tables()
        event_id = self._create_pending_event()

        # Resolve the event first
        resp = client.post(
            f"/escalation/queue/{event_id}/resolve",
            json={"status": "approved", "note": "Looks good"},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200

        # Hold should return immediately with approved status
        resp = client.post(
            f"/escalation/queue/{event_id}/hold",
            params={"timeout_seconds": 2, "poll_interval": 0.5},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["timed_out"] is False
        assert data["resolved_by"] is not None
        _cleanup_escalation_tables()

    def test_hold_times_out_for_pending(self, admin_token):
        _cleanup_escalation_tables()
        event_id = self._create_pending_event()

        resp = client.post(
            f"/escalation/queue/{event_id}/hold",
            params={"timeout_seconds": 1, "poll_interval": 0.5},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["timed_out"] is True
        _cleanup_escalation_tables()

    def test_hold_404_for_missing_event(self, admin_token):
        _cleanup_escalation_tables()
        resp = client.post(
            "/escalation/queue/99999/hold",
            params={"timeout_seconds": 1},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 404
        _cleanup_escalation_tables()

    def test_hold_requires_auth(self):
        resp = client.post("/escalation/queue/1/hold")
        assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════
# Auto-expiry
# ═══════════════════════════════════════════════════════════════════════════

class TestAutoExpiry:
    def _create_expired_event(self):
        """Insert a pending event whose expires_at is in the past."""
        with db_session() as session:
            ev = EscalationEvent(
                tool="shell",
                agent_id="test-agent",
                trigger="policy_review",
                severity="medium",
                decision="review",
                risk_score=60,
                explanation="Expired review",
                status="pending",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            )
            session.add(ev)
            session.flush()
            return ev.id

    def test_expired_event_auto_expires_on_queue_list(self, admin_token):
        _cleanup_escalation_tables()
        event_id = self._create_expired_event()

        # Listing the queue should auto-expire the stale event
        resp = client.get(
            "/escalation/queue",
            params={"status": "expired"},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200
        events = resp.json()
        expired_ids = [e["id"] for e in events]
        assert event_id in expired_ids
        assert events[0]["status"] == "expired"
        _cleanup_escalation_tables()

    def test_expired_event_counted_in_stats(self, admin_token):
        _cleanup_escalation_tables()
        self._create_expired_event()

        resp = client.get("/escalation/queue/stats", headers=_headers(admin_token))
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["expired"] >= 1
        _cleanup_escalation_tables()

    def test_hold_detects_expired_event(self, admin_token):
        _cleanup_escalation_tables()
        event_id = self._create_expired_event()

        resp = client.post(
            f"/escalation/queue/{event_id}/hold",
            params={"timeout_seconds": 1, "poll_interval": 0.5},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "expired"
        assert data["timed_out"] is False
        _cleanup_escalation_tables()

    def test_event_has_expires_at_field(self, admin_token):
        _cleanup_escalation_tables()
        # Trigger a review action to create an escalation event via the full pipeline
        resp = client.post(
            "/actions/evaluate",
            json={
                "tool": "shell",
                "args": {"cmd": "rm -rf /"},
                "context": {"agent_id": "expiry-test"},
            },
            headers=_headers(admin_token),
        )
        data = resp.json()
        esc_id = data.get("escalation_id")
        if esc_id:
            resp = client.get(f"/escalation/queue/{esc_id}", headers=_headers(admin_token))
            assert resp.status_code == 200
            ev = resp.json()
            # expires_at should be set (not None) since default expiry is 30 minutes
            assert ev.get("expires_at") is not None
        _cleanup_escalation_tables()
