"""
tests/test_escalation.py — Tests for the escalation subsystem
==============================================================

Covers: config CRUD, review queue lifecycle, auto-KS thresholds,
severity computation, and webhook management.
"""
import pytest
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
