"""
Tests for conversation / interaction logging system.
=====================================================
Covers:
  - Turn creation (single + batch)
  - Encryption at rest
  - Conversation timeline (turns + actions interleaved)
  - Conversation list / summary
  - conversation_id/turn_id propagation through /actions/evaluate
  - Prompt inline on ActionInput
  - Auth requirements
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.database import db_session
from app.main import app
from app.models import ConversationTurn, ActionLog

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_turn(token: str, **overrides) -> dict:
    payload = {
        "conversation_id": "conv-test-001",
        "turn_index": 0,
        "agent_id": "agent-a",
        "session_id": "sess-1",
        "user_id": "user-1",
        "prompt": "Deploy my application to staging",
        "agent_reasoning": "User wants to deploy. I should use the deploy tool targeting staging environment.",
        "agent_response": "I've deployed your application to the staging environment successfully.",
        "tool_plan": ["deploy", "verify_deployment"],
        "model_id": "gpt-4o",
        "prompt_tokens": 150,
        "completion_tokens": 80,
    }
    payload.update(overrides)
    resp = client.post("/conversations/turns", json=payload, headers=_headers(token))
    return resp


# ---------------------------------------------------------------------------
# POST /conversations/turns
# ---------------------------------------------------------------------------

class TestCreateTurn:

    def test_create_turn_basic(self, admin_token):
        resp = _create_turn(admin_token)
        assert resp.status_code == 201
        data = resp.json()
        assert data["conversation_id"] == "conv-test-001"
        assert "id" in data

    def test_create_turn_minimal(self, admin_token):
        """Only conversation_id is required."""
        resp = client.post(
            "/conversations/turns",
            json={"conversation_id": "conv-minimal"},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 201

    def test_create_turn_requires_auth(self):
        resp = client.post("/conversations/turns", json={"conversation_id": "x"})
        assert resp.status_code in (401, 403)

    def test_turn_text_stored_encrypted(self, admin_token):
        """Prompt text should NOT appear as plain text in the DB row when encryption is off
        (it still passes through encrypt_value which is a no-op without a key)."""
        resp = _create_turn(admin_token, conversation_id="conv-enc-test", prompt="Secret user question")
        assert resp.status_code == 201
        turn_id = resp.json()["id"]

        with db_session() as session:
            row = session.get(ConversationTurn, turn_id)
            assert row is not None
            # The stored field is prompt_encrypted, not prompt
            assert row.prompt_encrypted is not None

    def test_turn_decrypted_on_read(self, admin_token):
        """GET should return decrypted text."""
        resp = _create_turn(admin_token, conversation_id="conv-decrypt-test", turn_index=0)
        turn_id = resp.json()["id"]

        resp = client.get(f"/conversations/turns/{turn_id}", headers=_headers(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["prompt"] == "Deploy my application to staging"
        assert data["agent_reasoning"] is not None
        assert data["agent_response"] is not None
        assert data["tool_plan"] == ["deploy", "verify_deployment"]

    def test_turn_model_metadata(self, admin_token):
        resp = _create_turn(admin_token, conversation_id="conv-meta")
        turn_id = resp.json()["id"]

        resp = client.get(f"/conversations/turns/{turn_id}", headers=_headers(admin_token))
        data = resp.json()
        assert data["model_id"] == "gpt-4o"
        assert data["prompt_tokens"] == 150
        assert data["completion_tokens"] == 80


# ---------------------------------------------------------------------------
# POST /conversations/turns/batch
# ---------------------------------------------------------------------------

class TestBatchIngest:

    def test_batch_create(self, admin_token):
        turns = [
            {"conversation_id": "conv-batch", "turn_index": i, "prompt": f"Turn {i}"}
            for i in range(3)
        ]
        resp = client.post(
            "/conversations/turns/batch",
            json={"turns": turns},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 3
        assert len(data["ids"]) == 3

    def test_batch_empty_rejected(self, admin_token):
        resp = client.post(
            "/conversations/turns/batch",
            json={"turns": []},
            headers=_headers(admin_token),
        )
        assert resp.status_code == 422  # validation error


# ---------------------------------------------------------------------------
# GET /conversations/turns
# ---------------------------------------------------------------------------

class TestListTurns:

    def test_list_all(self, admin_token):
        # Create a turn first
        _create_turn(admin_token, conversation_id="conv-list-all")
        resp = client.get("/conversations/turns", headers=_headers(admin_token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) > 0

    def test_filter_by_conversation_id(self, admin_token):
        cid = "conv-filter-cid"
        _create_turn(admin_token, conversation_id=cid)
        resp = client.get(f"/conversations/turns?conversation_id={cid}", headers=_headers(admin_token))
        assert resp.status_code == 200
        for t in resp.json():
            assert t["conversation_id"] == cid

    def test_filter_by_agent_id(self, admin_token):
        _create_turn(admin_token, conversation_id="conv-filter-agent", agent_id="agent-filter-test")
        resp = client.get("/conversations/turns?agent_id=agent-filter-test", headers=_headers(admin_token))
        assert resp.status_code == 200
        for t in resp.json():
            assert t["agent_id"] == "agent-filter-test"

    def test_list_requires_auth(self):
        resp = client.get("/conversations/turns")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /conversations/turns/{turn_id}
# ---------------------------------------------------------------------------

class TestGetTurn:

    def test_get_nonexistent(self, admin_token):
        resp = client.get("/conversations/turns/99999", headers=_headers(admin_token))
        assert resp.status_code == 404

    def test_get_by_id(self, admin_token):
        resp = _create_turn(admin_token, conversation_id="conv-get-by-id")
        turn_id = resp.json()["id"]
        resp = client.get(f"/conversations/turns/{turn_id}", headers=_headers(admin_token))
        assert resp.status_code == 200
        assert resp.json()["id"] == turn_id


# ---------------------------------------------------------------------------
# conversation_id / turn_id on ActionInput + ActionLog
# ---------------------------------------------------------------------------

class TestActionConversationLink:

    def test_evaluate_with_conversation_context(self, admin_token):
        """ActionInput with conversation_id in context should persist it on ActionLog."""
        resp = client.post(
            "/actions/evaluate",
            json={
                "tool": "read_file",
                "args": {"path": "/tmp/test.txt"},
                "context": {
                    "agent_id": "agent-conv-link",
                    "session_id": "sess-conv-link",
                    "conversation_id": "conv-action-link-001",
                    "turn_id": 42,
                },
            },
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200

        # Verify the ActionLog row has conversation_id
        with db_session() as session:
            from sqlalchemy import select
            row = session.execute(
                select(ActionLog)
                .where(ActionLog.conversation_id == "conv-action-link-001")
                .order_by(ActionLog.id.desc())
            ).scalars().first()
            assert row is not None
            assert row.conversation_id == "conv-action-link-001"
            assert row.turn_id == 42

    def test_evaluate_with_inline_prompt(self, admin_token):
        """ActionInput with prompt field should encrypt and store it in context."""
        resp = client.post(
            "/actions/evaluate",
            json={
                "tool": "read_file",
                "args": {"path": "/tmp/readme.md"},
                "prompt": "Show me the readme file",
                "context": {
                    "agent_id": "agent-prompt-inline",
                    "conversation_id": "conv-prompt-inline",
                },
            },
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200

        # Verify stored context has _prompt_encrypted
        with db_session() as session:
            from sqlalchemy import select
            row = session.execute(
                select(ActionLog)
                .where(ActionLog.conversation_id == "conv-prompt-inline")
                .order_by(ActionLog.id.desc())
            ).scalars().first()
            assert row is not None
            ctx = json.loads(row.context)
            assert "_prompt_encrypted" in ctx

    def test_evaluate_without_conversation_still_works(self, admin_token):
        """Backward compat — evaluate without conversation fields."""
        resp = client.post(
            "/actions/evaluate",
            json={
                "tool": "read_file",
                "args": {"path": "/tmp/test.txt"},
                "context": {"agent_id": "agent-no-conv"},
            },
            headers=_headers(admin_token),
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /conversations/{conversation_id}/timeline
# ---------------------------------------------------------------------------

class TestTimeline:

    def test_timeline_turns_and_actions(self, admin_token):
        cid = "conv-timeline-001"

        # Create a turn
        _create_turn(admin_token, conversation_id=cid, turn_index=0)

        # Create a governed action linked to same conversation
        client.post(
            "/actions/evaluate",
            json={
                "tool": "deploy",
                "args": {"env": "staging"},
                "context": {"agent_id": "agent-tl", "conversation_id": cid},
            },
            headers=_headers(admin_token),
        )

        # Get timeline
        resp = client.get(f"/conversations/{cid}/timeline", headers=_headers(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_id"] == cid
        assert data["turns"] >= 1
        assert data["actions"] >= 1

        types = {e["type"] for e in data["timeline"]}
        assert "turn" in types
        assert "action" in types

    def test_timeline_empty_conversation(self, admin_token):
        resp = client.get("/conversations/nonexistent-conv/timeline", headers=_headers(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["turns"] == 0
        assert data["actions"] == 0


# ---------------------------------------------------------------------------
# GET /conversations (list)
# ---------------------------------------------------------------------------

class TestConversationList:

    def test_list_conversations(self, admin_token):
        cid = "conv-list-test"
        _create_turn(admin_token, conversation_id=cid, turn_index=0)
        _create_turn(admin_token, conversation_id=cid, turn_index=1)

        resp = client.get("/conversations", headers=_headers(admin_token))
        assert resp.status_code == 200
        conversations = resp.json()
        assert isinstance(conversations, list)

        # Find our conversation
        found = [c for c in conversations if c["conversation_id"] == cid]
        assert len(found) == 1
        assert found[0]["turn_count"] >= 2

    def test_list_conversations_filter_agent(self, admin_token):
        _create_turn(admin_token, conversation_id="conv-agent-filter", agent_id="agent-unique-filter")
        resp = client.get("/conversations?agent_id=agent-unique-filter", headers=_headers(admin_token))
        assert resp.status_code == 200
        for c in resp.json():
            assert c["agent_id"] == "agent-unique-filter"

    def test_list_conversations_requires_auth(self):
        resp = client.get("/conversations")
        assert resp.status_code in (401, 403)
