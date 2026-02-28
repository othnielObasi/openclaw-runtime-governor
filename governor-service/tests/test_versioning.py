"""
Tests for policy versioning (version history + restore) and
multi-channel notification endpoints.

Run with: pytest tests/test_versioning.py -v
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.main import app
from app.database import db_session
from app.models import PolicyModel, PolicyVersion, PolicyAuditLog
from app.escalation.models import NotificationChannel
from app.policies.loader import invalidate_policy_cache

client = TestClient(app)


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

_shared_token: str | None = None


def _admin_headers() -> dict:
    global _shared_token
    if _shared_token is None:
        resp = client.post("/auth/login", json={"username": "admin", "password": "changeme"})
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        _shared_token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {_shared_token}"}


def _set_shared_token(token: str):
    global _shared_token
    _shared_token = token


@pytest.fixture(autouse=True, scope="module")
def _inject_token(admin_token):
    _set_shared_token(admin_token)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def cleanup():
    yield
    with db_session() as session:
        session.execute(delete(PolicyAuditLog).where(PolicyAuditLog.policy_id.like("vtest-%")))
        session.execute(delete(PolicyVersion).where(PolicyVersion.policy_id.like("vtest-%")))
        session.execute(delete(PolicyModel).where(PolicyModel.policy_id.like("vtest-%")))
        session.execute(delete(NotificationChannel).where(NotificationChannel.label.like("test-%")))
    invalidate_policy_cache()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_policy(pid: str = "vtest-sample", severity: int = 50):
    return client.post("/policies", json={
        "policy_id": pid,
        "description": f"Version test policy {pid}",
        "severity": severity,
        "match_json": {"tool": "shell"},
        "action": "block",
    }, headers=_admin_headers())


# ===========================================================================
# POLICY VERSIONING TESTS
# ===========================================================================

class TestPolicyVersionField:
    """New policies should start at version 1 and increment on edit."""

    def test_create_starts_at_version_1(self):
        resp = _create_policy("vtest-v1")
        assert resp.status_code == 201
        data = resp.json()
        assert data["version"] == 1

    def test_edit_increments_version(self):
        _create_policy("vtest-v-inc")
        h = _admin_headers()

        # Edit 1
        resp = client.patch("/policies/vtest-v-inc", json={
            "description": "Updated once",
        }, headers=h)
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

        # Edit 2
        resp = client.patch("/policies/vtest-v-inc", json={
            "severity": 90,
        }, headers=h)
        assert resp.status_code == 200
        assert resp.json()["version"] == 3

    def test_archive_does_not_change_version(self):
        _create_policy("vtest-archive-ver")
        h = _admin_headers()
        resp = client.patch("/policies/vtest-archive-ver/archive", headers=h)
        assert resp.status_code == 200
        assert resp.json()["version"] == 1

    def test_activate_does_not_change_version(self):
        _create_policy("vtest-activate-ver")
        h = _admin_headers()
        client.patch("/policies/vtest-activate-ver/archive", headers=h)
        resp = client.patch("/policies/vtest-activate-ver/activate", headers=h)
        assert resp.status_code == 200
        assert resp.json()["version"] == 1


class TestVersionHistory:
    """GET /{policy_id}/versions returns snapshot history."""

    def test_initial_version_in_history(self):
        _create_policy("vtest-hist-1")
        h = _admin_headers()
        resp = client.get("/policies/vtest-hist-1/versions", headers=h)
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) == 1
        assert versions[0]["version"] == 1
        assert versions[0]["policy_id"] == "vtest-hist-1"
        assert versions[0]["note"] == "Initial creation"

    def test_edit_creates_version_snapshot(self):
        _create_policy("vtest-hist-2")
        h = _admin_headers()
        client.patch("/policies/vtest-hist-2", json={"severity": 80}, headers=h)
        client.patch("/policies/vtest-hist-2", json={"description": "Third version"}, headers=h)

        resp = client.get("/policies/vtest-hist-2/versions", headers=h)
        versions = resp.json()
        assert len(versions) == 3
        # Newest first
        assert versions[0]["version"] == 3
        assert versions[1]["version"] == 2
        assert versions[2]["version"] == 1

    def test_version_preserves_full_state(self):
        _create_policy("vtest-hist-state", severity=40)
        h = _admin_headers()
        client.patch("/policies/vtest-hist-state", json={
            "severity": 95,
            "action": "review",
        }, headers=h)

        resp = client.get("/policies/vtest-hist-state/versions", headers=h)
        versions = resp.json()

        # v1 should have original state
        v1 = [v for v in versions if v["version"] == 1][0]
        assert v1["severity"] == 40
        assert v1["action"] == "block"

        # v2 should have updated state
        v2 = [v for v in versions if v["version"] == 2][0]
        assert v2["severity"] == 95
        assert v2["action"] == "review"

    def test_versions_404_for_missing_policy(self):
        h = _admin_headers()
        resp = client.get("/policies/vtest-nonexistent/versions", headers=h)
        assert resp.status_code == 404

    def test_version_has_created_by(self):
        _create_policy("vtest-hist-user")
        h = _admin_headers()
        resp = client.get("/policies/vtest-hist-user/versions", headers=h)
        versions = resp.json()
        assert versions[0]["created_by"] == "admin"


class TestRestoreVersion:
    """POST /{policy_id}/restore/{version} restores to historical state."""

    def test_restore_creates_new_version(self):
        _create_policy("vtest-restore-1", severity=30)
        h = _admin_headers()

        # Edit to v2
        client.patch("/policies/vtest-restore-1", json={"severity": 90}, headers=h)

        # Restore to v1
        resp = client.post("/policies/vtest-restore-1/restore/1", headers=h)
        assert resp.status_code == 200
        data = resp.json()
        assert data["severity"] == 30  # Original severity restored
        assert data["version"] == 3  # New version created (not rewritten)

    def test_restore_appears_in_history(self):
        _create_policy("vtest-restore-hist", severity=50)
        h = _admin_headers()
        client.patch("/policies/vtest-restore-hist", json={"severity": 80}, headers=h)
        client.post("/policies/vtest-restore-hist/restore/1", headers=h)

        resp = client.get("/policies/vtest-restore-hist/versions", headers=h)
        versions = resp.json()
        assert len(versions) == 3
        # v3 should have "Restored from v1" note
        v3 = versions[0]
        assert v3["version"] == 3
        assert "Restored from v1" in v3["note"]
        assert v3["severity"] == 50  # Original value

    def test_restore_logs_audit(self):
        _create_policy("vtest-restore-audit")
        h = _admin_headers()
        client.patch("/policies/vtest-restore-audit", json={"severity": 90}, headers=h)
        client.post("/policies/vtest-restore-audit/restore/1", headers=h)

        resp = client.get("/policies/audit/trail", params={
            "policy_id": "vtest-restore-audit",
            "action": "restore",
        }, headers=h)
        assert resp.status_code == 200
        audits = resp.json()
        assert len(audits) >= 1
        assert audits[0]["action"] == "restore"

    def test_restore_404_invalid_version(self):
        _create_policy("vtest-restore-404")
        h = _admin_headers()
        resp = client.post("/policies/vtest-restore-404/restore/999", headers=h)
        assert resp.status_code == 404

    def test_restore_404_missing_policy(self):
        h = _admin_headers()
        resp = client.post("/policies/vtest-ghost/restore/1", headers=h)
        assert resp.status_code == 404

    def test_restore_restores_all_fields(self):
        """Ensure description, severity, match_json, action, is_active are all restored."""
        _create_policy("vtest-restore-full", severity=25)
        h = _admin_headers()

        # Edit everything
        client.patch("/policies/vtest-restore-full", json={
            "description": "Completely changed",
            "severity": 99,
            "action": "review",
            "match_json": {"tool": "file_write"},
        }, headers=h)

        # Verify v2 is the edited state
        resp = client.get("/policies/vtest-restore-full", headers=h)
        assert resp.json()["severity"] == 99
        assert resp.json()["action"] == "review"

        # Restore to v1
        resp = client.post("/policies/vtest-restore-full/restore/1", headers=h)
        data = resp.json()
        assert data["severity"] == 25
        assert data["action"] == "block"
        assert data["match_json"] == {"tool": "shell"}
        assert "Version test policy" in data["description"]


# ===========================================================================
# NOTIFICATION CHANNEL TESTS
# ===========================================================================

class TestNotificationChannelCRUD:
    """CRUD operations for /notifications endpoints."""

    def test_list_empty(self):
        h = _admin_headers()
        resp = client.get("/notifications", headers=h)
        assert resp.status_code == 200
        # May contain channels from other tests, just ensure it's a list
        assert isinstance(resp.json(), list)

    def test_create_email_channel(self):
        h = _admin_headers()
        resp = client.post("/notifications", json={
            "label": "test-email-1",
            "channel_type": "email",
            "config_json": {
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "from_addr": "alerts@example.com",
                "to_addrs": ["admin@example.com"],
                "use_tls": True,
            },
            "on_block": True,
            "on_review": True,
            "on_auto_ks": True,
        }, headers=h)
        assert resp.status_code == 201
        data = resp.json()
        assert data["channel_type"] == "email"
        assert data["label"] == "test-email-1"
        assert data["is_active"] is True
        assert data["config_json"]["smtp_host"] == "smtp.example.com"

    def test_create_slack_channel(self):
        h = _admin_headers()
        resp = client.post("/notifications", json={
            "label": "test-slack-1",
            "channel_type": "slack",
            "config_json": {
                "webhook_url": "https://hooks.slack.com/services/T000/B000/xxxx",
            },
        }, headers=h)
        assert resp.status_code == 201
        assert resp.json()["channel_type"] == "slack"

    def test_create_whatsapp_channel(self):
        h = _admin_headers()
        resp = client.post("/notifications", json={
            "label": "test-whatsapp-1",
            "channel_type": "whatsapp",
            "config_json": {
                "phone_number_id": "123456",
                "access_token": "EAAxxxx",
                "to_numbers": ["+1234567890"],
            },
        }, headers=h)
        assert resp.status_code == 201
        assert resp.json()["channel_type"] == "whatsapp"

    def test_create_jira_channel(self):
        h = _admin_headers()
        resp = client.post("/notifications", json={
            "label": "test-jira-1",
            "channel_type": "jira",
            "config_json": {
                "base_url": "https://myorg.atlassian.net",
                "project_key": "GOV",
                "issue_type": "Task",
                "email": "bot@myorg.com",
                "api_token": "ATATTxxx",
            },
        }, headers=h)
        assert resp.status_code == 201
        assert resp.json()["channel_type"] == "jira"

    def test_create_webhook_channel(self):
        h = _admin_headers()
        resp = client.post("/notifications", json={
            "label": "test-webhook-1",
            "channel_type": "webhook",
            "config_json": {
                "url": "https://example.com/hook",
                "auth_header": "Bearer token123",
            },
        }, headers=h)
        assert resp.status_code == 201
        assert resp.json()["channel_type"] == "webhook"

    def test_invalid_channel_type(self):
        h = _admin_headers()
        resp = client.post("/notifications", json={
            "label": "test-invalid",
            "channel_type": "telegram",
            "config_json": {},
        }, headers=h)
        assert resp.status_code == 422

    def test_get_channel_by_id(self):
        h = _admin_headers()
        create_resp = client.post("/notifications", json={
            "label": "test-get-1",
            "channel_type": "email",
            "config_json": {"smtp_host": "localhost", "to_addrs": ["x@x.com"]},
        }, headers=h)
        cid = create_resp.json()["id"]

        resp = client.get(f"/notifications/{cid}", headers=h)
        assert resp.status_code == 200
        assert resp.json()["id"] == cid

    def test_update_channel(self):
        h = _admin_headers()
        create_resp = client.post("/notifications", json={
            "label": "test-update-1",
            "channel_type": "email",
            "config_json": {"smtp_host": "old.host.com", "to_addrs": ["a@b.com"]},
        }, headers=h)
        cid = create_resp.json()["id"]

        resp = client.patch(f"/notifications/{cid}", json={
            "label": "test-update-1-renamed",
            "on_block": False,
        }, headers=h)
        assert resp.status_code == 200
        assert resp.json()["label"] == "test-update-1-renamed"
        assert resp.json()["on_block"] is False

    def test_delete_channel(self):
        h = _admin_headers()
        create_resp = client.post("/notifications", json={
            "label": "test-delete-1",
            "channel_type": "webhook",
            "config_json": {"url": "https://example.com/delete-me"},
        }, headers=h)
        cid = create_resp.json()["id"]

        resp = client.delete(f"/notifications/{cid}", headers=h)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # Verify it's gone
        resp = client.get(f"/notifications/{cid}", headers=h)
        assert resp.status_code == 404

    def test_404_missing_channel(self):
        h = _admin_headers()
        resp = client.get("/notifications/99999", headers=h)
        assert resp.status_code == 404


class TestNotificationChannelConfig:
    """Event filtering and config persistence."""

    def test_on_policy_change_default_false(self):
        h = _admin_headers()
        resp = client.post("/notifications", json={
            "label": "test-pol-change",
            "channel_type": "email",
            "config_json": {"smtp_host": "localhost", "to_addrs": ["a@b.com"]},
        }, headers=h)
        assert resp.json()["on_policy_change"] is False

    def test_enable_on_policy_change(self):
        h = _admin_headers()
        resp = client.post("/notifications", json={
            "label": "test-pol-change-on",
            "channel_type": "slack",
            "config_json": {"webhook_url": "https://hooks.slack.com/x"},
            "on_policy_change": True,
        }, headers=h)
        assert resp.json()["on_policy_change"] is True

    def test_deactivate_channel(self):
        h = _admin_headers()
        create_resp = client.post("/notifications", json={
            "label": "test-deactivate",
            "channel_type": "webhook",
            "config_json": {"url": "https://example.com/deactivate"},
        }, headers=h)
        cid = create_resp.json()["id"]

        resp = client.patch(f"/notifications/{cid}", json={"is_active": False}, headers=h)
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_error_count_starts_at_zero(self):
        h = _admin_headers()
        resp = client.post("/notifications", json={
            "label": "test-err-count",
            "channel_type": "email",
            "config_json": {"smtp_host": "localhost", "to_addrs": ["a@b.com"]},
        }, headers=h)
        assert resp.json()["error_count"] == 0

    def test_update_config_json(self):
        h = _admin_headers()
        create_resp = client.post("/notifications", json={
            "label": "test-cfg-update",
            "channel_type": "email",
            "config_json": {"smtp_host": "old.com", "to_addrs": ["a@b.com"]},
        }, headers=h)
        cid = create_resp.json()["id"]

        resp = client.patch(f"/notifications/{cid}", json={
            "config_json": {"smtp_host": "new.com", "to_addrs": ["x@y.com"]},
        }, headers=h)
        assert resp.status_code == 200
        assert resp.json()["config_json"]["smtp_host"] == "new.com"
