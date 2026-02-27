"""
Tests for production policy management: CRUD, PATCH, toggle, regex validation,
is_active filtering in the evaluation pipeline.

Run with: pytest tests/test_policies.py -v
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import db_session
from app.models import PolicyModel
from app.policies.loader import invalidate_policy_cache, load_db_policies


client = TestClient(app)


# ---------------------------------------------------------------------------
# Auth helper — get a JWT for admin (module-scoped to avoid rate limit)
# ---------------------------------------------------------------------------

_cached_token: str | None = None


def _admin_headers() -> dict:
    global _cached_token
    if _cached_token is None:
        resp = client.post("/auth/login", json={"username": "admin", "password": "changeme"})
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        _cached_token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {_cached_token}"}


# ---------------------------------------------------------------------------
# Cleanup fixture — remove test policies after each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def cleanup_test_policies():
    yield
    with db_session() as session:
        from sqlalchemy import delete
        session.execute(
            delete(PolicyModel).where(PolicyModel.policy_id.like("test-%"))
        )
    invalidate_policy_cache()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

class TestCreatePolicy:
    def test_create_returns_201(self):
        h = _admin_headers()
        resp = client.post("/policies", json={
            "policy_id": "test-create-1",
            "description": "Test policy",
            "severity": 50,
            "match_json": {"tool": "shell"},
            "action": "review",
        }, headers=h)
        assert resp.status_code == 201
        data = resp.json()
        assert data["policy_id"] == "test-create-1"
        assert data["is_active"] is True
        assert "created_at" in data

    def test_create_duplicate_rejected(self):
        h = _admin_headers()
        payload = {
            "policy_id": "test-dup",
            "description": "dup",
            "severity": 30,
            "match_json": {"tool": "shell"},
            "action": "allow",
        }
        client.post("/policies", json=payload, headers=h)
        resp = client.post("/policies", json=payload, headers=h)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_create_validates_regex(self):
        h = _admin_headers()
        resp = client.post("/policies", json={
            "policy_id": "test-bad-regex",
            "description": "bad regex",
            "severity": 50,
            "match_json": {"tool": "shell", "args_regex": "[invalid("},
            "action": "block",
        }, headers=h)
        assert resp.status_code == 422
        assert "Invalid regex" in resp.json()["detail"]

    def test_create_validates_url_regex(self):
        h = _admin_headers()
        resp = client.post("/policies", json={
            "policy_id": "test-bad-url-regex",
            "description": "bad url regex",
            "severity": 50,
            "match_json": {"tool": "http_request", "url_regex": "(?P<unterminated"},
            "action": "block",
        }, headers=h)
        assert resp.status_code == 422
        assert "url_regex" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET (single + list)
# ---------------------------------------------------------------------------

class TestGetPolicy:
    def test_get_single_policy(self):
        h = _admin_headers()
        client.post("/policies", json={
            "policy_id": "test-get-single",
            "description": "single",
            "severity": 40,
            "match_json": {"tool": "shell"},
            "action": "allow",
        }, headers=h)
        resp = client.get("/policies/test-get-single", headers=h)
        assert resp.status_code == 200
        assert resp.json()["policy_id"] == "test-get-single"

    def test_get_nonexistent_returns_404(self):
        h = _admin_headers()
        resp = client.get("/policies/nonexistent-policy-xyz", headers=h)
        assert resp.status_code == 404

    def test_list_active_only(self):
        h = _admin_headers()
        # Create two policies
        client.post("/policies", json={
            "policy_id": "test-active-filter-1",
            "description": "active one",
            "severity": 30,
            "match_json": {"tool": "shell"},
            "action": "allow",
        }, headers=h)
        client.post("/policies", json={
            "policy_id": "test-active-filter-2",
            "description": "will disable",
            "severity": 30,
            "match_json": {"tool": "shell"},
            "action": "allow",
        }, headers=h)
        # Disable the second
        client.patch("/policies/test-active-filter-2/toggle", headers=h)

        # List all
        all_resp = client.get("/policies", headers=h)
        all_ids = {p["policy_id"] for p in all_resp.json()}
        assert "test-active-filter-1" in all_ids
        assert "test-active-filter-2" in all_ids

        # List active only
        active_resp = client.get("/policies?active_only=true", headers=h)
        active_ids = {p["policy_id"] for p in active_resp.json()}
        assert "test-active-filter-1" in active_ids
        assert "test-active-filter-2" not in active_ids


# ---------------------------------------------------------------------------
# PATCH (update)
# ---------------------------------------------------------------------------

class TestUpdatePolicy:
    def test_patch_updates_fields(self):
        h = _admin_headers()
        client.post("/policies", json={
            "policy_id": "test-patch",
            "description": "original",
            "severity": 50,
            "match_json": {"tool": "shell"},
            "action": "review",
        }, headers=h)

        resp = client.patch("/policies/test-patch", json={
            "description": "updated description",
            "severity": 80,
            "action": "block",
        }, headers=h)
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "updated description"
        assert data["severity"] == 80
        assert data["action"] == "block"
        assert data["updated_at"] is not None

    def test_patch_partial_update(self):
        h = _admin_headers()
        client.post("/policies", json={
            "policy_id": "test-partial",
            "description": "original",
            "severity": 50,
            "match_json": {"tool": "shell"},
            "action": "review",
        }, headers=h)

        # Only update severity
        resp = client.patch("/policies/test-partial", json={"severity": 90}, headers=h)
        assert resp.status_code == 200
        data = resp.json()
        assert data["severity"] == 90
        assert data["description"] == "original"  # unchanged
        assert data["action"] == "review"          # unchanged

    def test_patch_validates_regex(self):
        h = _admin_headers()
        client.post("/policies", json={
            "policy_id": "test-patch-regex",
            "description": "will patch",
            "severity": 50,
            "match_json": {"tool": "shell"},
            "action": "review",
        }, headers=h)

        resp = client.patch("/policies/test-patch-regex", json={
            "match_json": {"tool": "shell", "args_regex": "[broken("},
        }, headers=h)
        assert resp.status_code == 422
        assert "Invalid regex" in resp.json()["detail"]

    def test_patch_empty_body_rejected(self):
        h = _admin_headers()
        client.post("/policies", json={
            "policy_id": "test-patch-empty",
            "description": "test",
            "severity": 50,
            "match_json": {"tool": "shell"},
            "action": "review",
        }, headers=h)

        resp = client.patch("/policies/test-patch-empty", json={}, headers=h)
        assert resp.status_code == 400
        assert "No fields" in resp.json()["detail"]

    def test_patch_nonexistent_returns_404(self):
        h = _admin_headers()
        resp = client.patch("/policies/nonexistent-xyz", json={"severity": 10}, headers=h)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TOGGLE
# ---------------------------------------------------------------------------

class TestTogglePolicy:
    def test_toggle_disables_and_enables(self):
        h = _admin_headers()
        client.post("/policies", json={
            "policy_id": "test-toggle",
            "description": "toggle me",
            "severity": 50,
            "match_json": {"tool": "shell"},
            "action": "review",
        }, headers=h)

        # Starts active
        resp = client.get("/policies/test-toggle", headers=h)
        assert resp.json()["is_active"] is True

        # Toggle off
        resp = client.patch("/policies/test-toggle/toggle", headers=h)
        assert resp.json()["is_active"] is False

        # Toggle back on
        resp = client.patch("/policies/test-toggle/toggle", headers=h)
        assert resp.json()["is_active"] is True

    def test_toggle_nonexistent_returns_404(self):
        h = _admin_headers()
        resp = client.patch("/policies/nonexistent-xyz/toggle", headers=h)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Pipeline Integration — inactive policies must not evaluate
# ---------------------------------------------------------------------------

class TestInactivePolicyFiltering:
    def test_inactive_policy_excluded_from_loader(self):
        h = _admin_headers()
        # Create and then disable
        client.post("/policies", json={
            "policy_id": "test-inactive-pipe",
            "description": "should not fire",
            "severity": 95,
            "match_json": {"tool": "shell", "args_regex": "test_inactive_marker"},
            "action": "block",
        }, headers=h)
        client.patch("/policies/test-inactive-pipe/toggle", headers=h)

        invalidate_policy_cache()
        policies = load_db_policies()
        ids = [p.id for p in policies]
        assert "test-inactive-pipe" not in ids

    def test_active_policy_included_in_loader(self):
        h = _admin_headers()
        client.post("/policies", json={
            "policy_id": "test-active-pipe",
            "description": "should fire",
            "severity": 95,
            "match_json": {"tool": "shell"},
            "action": "block",
        }, headers=h)

        invalidate_policy_cache()
        policies = load_db_policies()
        ids = [p.id for p in policies]
        assert "test-active-pipe" in ids


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

class TestDeletePolicy:
    def test_delete_removes_policy(self):
        h = _admin_headers()
        client.post("/policies", json={
            "policy_id": "test-delete",
            "description": "delete me",
            "severity": 50,
            "match_json": {"tool": "shell"},
            "action": "review",
        }, headers=h)

        resp = client.delete("/policies/test-delete", headers=h)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # Confirm gone
        resp = client.get("/policies/test-delete", headers=h)
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_404(self):
        h = _admin_headers()
        resp = client.delete("/policies/nonexistent-xyz", headers=h)
        assert resp.status_code == 404
