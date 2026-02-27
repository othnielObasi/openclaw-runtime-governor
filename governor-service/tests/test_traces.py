"""
Tests for agent trace ingestion, correlation, and governance span auto-creation.

Run with: pytest tests/test_traces.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import db_session
from app.models import TraceSpan, ActionLog


client = TestClient(app)

# ---------------------------------------------------------------------------
# Auth helper — uses session-scoped token from conftest
# ---------------------------------------------------------------------------

_shared_token: str | None = None


def _admin_headers() -> dict:
    global _shared_token
    assert _shared_token is not None, "Token not injected — conftest admin_token fixture missing?"
    return {"Authorization": f"Bearer {_shared_token}"}


def _set_shared_token(token: str):
    global _shared_token
    _shared_token = token


@pytest.fixture(autouse=True, scope="module")
def _inject_token(admin_token):
    """Inject the session-scoped admin token to avoid extra login calls."""
    _set_shared_token(admin_token)


# ---------------------------------------------------------------------------
# Cleanup fixture — remove test trace spans and related action_logs after each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def cleanup_test_traces():
    yield
    with db_session() as session:
        from sqlalchemy import delete
        session.execute(
            delete(TraceSpan).where(TraceSpan.trace_id.like("test-trace-%"))
        )
        session.execute(
            delete(ActionLog).where(ActionLog.trace_id.like("test-trace-%"))
        )


# ═══════════════════════════════════════════════════════════
# INGEST TESTS
# ═══════════════════════════════════════════════════════════

class TestIngestSpans:
    """POST /traces/ingest"""

    def test_ingest_single_span(self):
        now = datetime.now(timezone.utc).isoformat()
        resp = client.post("/traces/ingest", json={
            "spans": [{
                "trace_id": "test-trace-001",
                "span_id": "span-a",
                "kind": "agent",
                "name": "run-task",
                "start_time": now,
                "agent_id": "agent-x",
            }]
        }, headers=_admin_headers())
        assert resp.status_code == 201
        data = resp.json()
        assert data["inserted"] == 1
        assert data["skipped"] == 0

    def test_ingest_batch(self):
        now = datetime.now(timezone.utc)
        spans = []
        for i in range(5):
            spans.append({
                "trace_id": "test-trace-002",
                "span_id": f"span-batch-{i}",
                "kind": "llm",
                "name": f"llm-call-{i}",
                "start_time": (now + timedelta(seconds=i)).isoformat(),
                "end_time": (now + timedelta(seconds=i, milliseconds=200)).isoformat(),
                "agent_id": "agent-batch",
            })
        resp = client.post("/traces/ingest", json={"spans": spans}, headers=_admin_headers())
        assert resp.status_code == 201
        assert resp.json()["inserted"] == 5

    def test_ingest_idempotent(self):
        now = datetime.now(timezone.utc).isoformat()
        payload = {"spans": [{
            "trace_id": "test-trace-003",
            "span_id": "span-idem",
            "kind": "tool",
            "name": "file_read",
            "start_time": now,
        }]}
        resp1 = client.post("/traces/ingest", json=payload, headers=_admin_headers())
        assert resp1.json()["inserted"] == 1
        resp2 = client.post("/traces/ingest", json=payload, headers=_admin_headers())
        assert resp2.json()["inserted"] == 0
        assert resp2.json()["skipped"] == 1

    def test_ingest_invalid_kind_rejected(self):
        now = datetime.now(timezone.utc).isoformat()
        resp = client.post("/traces/ingest", json={
            "spans": [{
                "trace_id": "test-trace-004",
                "span_id": "span-bad-kind",
                "kind": "invalid_kind",
                "name": "bad",
                "start_time": now,
            }]
        }, headers=_admin_headers())
        assert resp.status_code == 422

    def test_ingest_duration_auto_calculated(self):
        start = datetime.now(timezone.utc)
        end = start + timedelta(milliseconds=150)
        resp = client.post("/traces/ingest", json={
            "spans": [{
                "trace_id": "test-trace-005",
                "span_id": "span-dur",
                "kind": "retrieval",
                "name": "fetch-docs",
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            }]
        }, headers=_admin_headers())
        assert resp.status_code == 201
        # Verify duration was calculated
        detail = client.get("/traces/test-trace-005", headers=_admin_headers())
        span = detail.json()["spans"][0]
        assert span["duration_ms"] is not None
        assert 140 <= span["duration_ms"] <= 160

    def test_ingest_with_attributes_and_io(self):
        now = datetime.now(timezone.utc).isoformat()
        resp = client.post("/traces/ingest", json={
            "spans": [{
                "trace_id": "test-trace-006",
                "span_id": "span-attrs",
                "kind": "llm",
                "name": "gpt-4o",
                "start_time": now,
                "attributes": {"model": "gpt-4o", "tokens": 450, "cost": 0.003},
                "input": "What is the meaning of life?",
                "output": "42",
                "events": [{"time": now, "name": "token_start"}],
            }]
        }, headers=_admin_headers())
        assert resp.status_code == 201
        detail = client.get("/traces/test-trace-006", headers=_admin_headers())
        span = detail.json()["spans"][0]
        assert span["attributes"]["model"] == "gpt-4o"
        assert span["input"] == "What is the meaning of life?"
        assert span["output"] == "42"
        assert len(span["events"]) == 1


# ═══════════════════════════════════════════════════════════
# TRACE LISTING TESTS
# ═══════════════════════════════════════════════════════════

class TestListTraces:
    """GET /traces"""

    def test_list_empty(self):
        resp = client.get("/traces", headers=_admin_headers())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_after_ingest(self):
        now = datetime.now(timezone.utc).isoformat()
        client.post("/traces/ingest", json={
            "spans": [
                {"trace_id": "test-trace-010", "span_id": "span-l1", "kind": "agent", "name": "root", "start_time": now},
                {"trace_id": "test-trace-010", "span_id": "span-l2", "kind": "llm", "name": "child", "start_time": now, "parent_span_id": "span-l1"},
            ]
        }, headers=_admin_headers())
        resp = client.get("/traces", headers=_admin_headers())
        traces = [t for t in resp.json() if t["trace_id"] == "test-trace-010"]
        assert len(traces) == 1
        assert traces[0]["span_count"] == 2
        assert traces[0]["root_span_name"] == "root"

    def test_list_filter_agent_id(self):
        now = datetime.now(timezone.utc).isoformat()
        client.post("/traces/ingest", json={
            "spans": [
                {"trace_id": "test-trace-011", "span_id": "span-f1", "kind": "agent", "name": "a", "start_time": now, "agent_id": "filter-agent-x"},
            ]
        }, headers=_admin_headers())
        resp = client.get("/traces?agent_id=filter-agent-x", headers=_admin_headers())
        assert any(t["trace_id"] == "test-trace-011" for t in resp.json())
        resp2 = client.get("/traces?agent_id=nonexistent", headers=_admin_headers())
        assert not any(t["trace_id"] == "test-trace-011" for t in resp2.json())


# ═══════════════════════════════════════════════════════════
# TRACE DETAIL TESTS
# ═══════════════════════════════════════════════════════════

class TestGetTrace:
    """GET /traces/{trace_id}"""

    def test_get_trace_detail(self):
        now = datetime.now(timezone.utc).isoformat()
        client.post("/traces/ingest", json={
            "spans": [
                {"trace_id": "test-trace-020", "span_id": "span-d1", "kind": "agent", "name": "root", "start_time": now, "agent_id": "agent-d"},
                {"trace_id": "test-trace-020", "span_id": "span-d2", "kind": "tool", "name": "shell", "start_time": now, "parent_span_id": "span-d1"},
            ]
        }, headers=_admin_headers())
        resp = client.get("/traces/test-trace-020", headers=_admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == "test-trace-020"
        assert data["span_count"] == 2
        assert data["agent_id"] == "agent-d"

    def test_get_trace_404(self):
        resp = client.get("/traces/nonexistent-trace-id", headers=_admin_headers())
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════
# GOVERNANCE SPAN AUTO-CREATION TESTS
# ═══════════════════════════════════════════════════════════

class TestGovernanceSpanCreation:
    """When trace_id is in action context, a governance span should be auto-created."""

    def test_evaluate_with_trace_id_creates_governance_span(self):
        # First ingest an agent span
        now = datetime.now(timezone.utc).isoformat()
        client.post("/traces/ingest", json={
            "spans": [{
                "trace_id": "test-trace-030",
                "span_id": "span-gov-parent",
                "kind": "agent",
                "name": "task-runner",
                "start_time": now,
                "agent_id": "agent-gov",
            }]
        }, headers=_admin_headers())

        # Evaluate with trace_id in context — should auto-create governance span
        resp = client.post("/actions/evaluate", json={
            "tool": "file_read",
            "args": {"path": "/etc/config"},
            "context": {
                "agent_id": "agent-gov",
                "trace_id": "test-trace-030",
                "span_id": "span-gov-parent",
            }
        }, headers=_admin_headers())
        assert resp.status_code == 200
        decision = resp.json()
        assert decision["decision"] in ("allow", "block", "review")

        # Now fetch the trace — should have 2 spans: the agent span + the governance span
        detail = client.get("/traces/test-trace-030", headers=_admin_headers())
        assert detail.status_code == 200
        data = detail.json()
        assert data["span_count"] >= 2  # original + governance
        gov_spans = [s for s in data["spans"] if s["kind"] == "governance"]
        assert len(gov_spans) == 1

        gov = gov_spans[0]
        assert gov["name"] == "governor.evaluate(file_read)"
        assert gov["parent_span_id"] == "span-gov-parent"
        assert gov["attributes"]["governor.decision"] == decision["decision"]
        assert gov["attributes"]["governor.risk_score"] == decision["risk_score"]
        assert gov["attributes"]["governor.tool"] == "file_read"
        assert gov["duration_ms"] is not None

    def test_evaluate_without_trace_id_no_span(self):
        """Evaluating without trace_id in context should NOT create any trace span."""
        # Count existing spans
        with db_session() as session:
            from sqlalchemy import func, select
            before = session.execute(select(func.count(TraceSpan.id))).scalar()

        client.post("/actions/evaluate", json={
            "tool": "http_request",
            "args": {"url": "https://example.com"},
            "context": {"agent_id": "agent-no-trace"}
        }, headers=_admin_headers())

        with db_session() as session:
            after = session.execute(select(func.count(TraceSpan.id))).scalar()
        # No new spans should have been created
        assert after == before

    def test_governance_decisions_correlated(self):
        """Governance decisions in action_logs should have trace_id set."""
        now = datetime.now(timezone.utc).isoformat()
        client.post("/traces/ingest", json={
            "spans": [{
                "trace_id": "test-trace-031",
                "span_id": "span-cor",
                "kind": "agent",
                "name": "corr-test",
                "start_time": now,
            }]
        }, headers=_admin_headers())

        client.post("/actions/evaluate", json={
            "tool": "file_write",
            "args": {"path": "/tmp/test.txt"},
            "context": {"trace_id": "test-trace-031", "span_id": "span-cor"}
        }, headers=_admin_headers())

        # Check trace detail has governance_decisions
        detail = client.get("/traces/test-trace-031", headers=_admin_headers())
        data = detail.json()
        assert data["governance_count"] >= 1
        decisions = data["governance_decisions"]
        assert any(d["tool"] == "file_write" for d in decisions)


# ═══════════════════════════════════════════════════════════
# DELETE TRACE TESTS
# ═══════════════════════════════════════════════════════════

class TestDeleteTrace:
    """DELETE /traces/{trace_id}"""

    def test_delete_trace(self):
        now = datetime.now(timezone.utc).isoformat()
        client.post("/traces/ingest", json={
            "spans": [
                {"trace_id": "test-trace-040", "span_id": "span-del1", "kind": "agent", "name": "to-delete", "start_time": now},
                {"trace_id": "test-trace-040", "span_id": "span-del2", "kind": "llm", "name": "child", "start_time": now, "parent_span_id": "span-del1"},
            ]
        }, headers=_admin_headers())
        resp = client.delete("/traces/test-trace-040", headers=_admin_headers())
        assert resp.status_code == 200
        assert resp.json()["spans_deleted"] == 2
        # Verify gone
        resp2 = client.get("/traces/test-trace-040", headers=_admin_headers())
        assert resp2.status_code == 404

    def test_delete_trace_404(self):
        resp = client.delete("/traces/nonexistent-trace", headers=_admin_headers())
        assert resp.status_code == 404
