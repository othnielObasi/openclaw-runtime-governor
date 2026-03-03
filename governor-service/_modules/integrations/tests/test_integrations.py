"""
SIEM Webhook + Escalation Connectors — Test Suite
===================================================
Run: pytest tests/test_integrations.py -v
"""
import json
import time
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from siem_webhook import (
    SiemDispatcher, SiemTarget, GovernanceEvent, MockTransport,
    compute_severity, event_from_evaluation,
    _format_splunk_hec, _format_elastic_ecs, _format_syslog_cef,
    _format_sentinel, _format_generic,
    SEVERITY_ORDER,
)
from escalation import (
    EscalationRouter, EscalationTarget, EscalationEvent, EscalationResult,
    MockTransport as EscMockTransport,
    _format_slack, _format_teams, _format_jira,
    _format_servicenow, _format_pagerduty,
)


# ═══ FIXTURES ═══

def _make_gov_event(**overrides) -> GovernanceEvent:
    defaults = dict(
        event_id="evt-test001",
        timestamp="2026-03-01T12:00:00+00:00",
        event_type="evaluation",
        tool="shell",
        decision="block",
        risk_score=85,
        explanation="Injection detected: jailbreak attempt in shell command",
        agent_id="agent_001",
        session_id="sess_abc",
        policy_ids=["pol_sec_1", "pol_inject_1"],
        chain_pattern="credential_then_exfil",
        surge_receipt_id="surge-abc123",
        surge_digest="deadbeef" * 8,
        deviations=[{"deviation_type": "novel_tool", "severity": 25.0, "confidence": 0.85}],
        deployment_id="novtia-uk-001",
        jurisdiction="GB",
        severity="critical",
    )
    defaults.update(overrides)
    return GovernanceEvent(**defaults)


def _make_esc_event(**overrides) -> EscalationEvent:
    defaults = dict(
        event_id="esc-test001",
        timestamp="2026-03-01T12:00:00+00:00",
        tool="http_post",
        decision="block",
        risk_score=92,
        explanation="Credential exfiltration: agent read AWS keys then attempted external POST",
        agent_id="agent_ops_001",
        session_id="sess_xyz",
        policy_ids=["pol_exfil_1"],
        chain_pattern="credential_then_exfil",
        chain_description="Agent read credentials then attempted to send data to external domain",
        deviations=[
            {"deviation_type": "novel_tool", "severity": 25.0, "confidence": 0.9},
            {"deviation_type": "novel_target_domain", "severity": 30.0, "confidence": 0.87},
        ],
        surge_receipt_id="surge-xyz789",
        deployment_id="novtia-uk-001",
        severity="critical",
        dashboard_url="https://governor.novtia.io/dashboard?event=esc-test001",
    )
    defaults.update(overrides)
    return EscalationEvent(**defaults)


# ═══════════════════════════════════════════════════════════
# SIEM WEBHOOK TESTS
# ═══════════════════════════════════════════════════════════

class TestSeverityComputation:

    def test_critical_severity(self):
        assert compute_severity("block", 85, None, []) == "critical"

    def test_high_severity_block(self):
        assert compute_severity("block", 50, None, []) == "high"

    def test_high_severity_chain(self):
        assert compute_severity("allow", 30, "some_pattern", []) == "high"

    def test_medium_severity_review(self):
        assert compute_severity("review", 30, None, []) == "medium"

    def test_medium_severity_risk(self):
        assert compute_severity("allow", 60, None, []) == "medium"

    def test_low_severity(self):
        assert compute_severity("allow", 10, None, []) == "low"


class TestEventFromEvaluation:

    def test_creates_event(self):
        event = event_from_evaluation(
            tool="shell", decision="block", risk_score=90,
            explanation="test", policy_ids=["pol_1"],
        )
        assert event.event_id.startswith("evt-")
        assert event.tool == "shell"
        assert event.severity == "critical"

    def test_with_deviations(self):
        event = event_from_evaluation(
            tool="http_get", decision="allow", risk_score=20,
            explanation="ok", policy_ids=[],
            deviations=[{"deviation_type": "novel_tool", "severity": 25}],
        )
        assert event.severity == "medium"


class TestSiemFormatters:

    def test_splunk_hec_format(self):
        event = _make_gov_event()
        target = SiemTarget(name="test", target_type="splunk_hec")
        result = _format_splunk_hec(event, target)
        assert "time" in result
        assert "event" in result
        assert result["source"] == "novtia_governor"
        assert result["event"]["tool"] == "shell"

    def test_elastic_ecs_format(self):
        event = _make_gov_event()
        target = SiemTarget(name="test", target_type="elastic")
        result = _format_elastic_ecs(event, target)
        assert "@timestamp" in result
        assert result["event"]["kind"] == "alert"
        assert result["event"]["type"] == ["denied"]
        assert result["agent"]["id"] == "agent_001"

    def test_elastic_ecs_allow_event(self):
        event = _make_gov_event(decision="allow", severity="low")
        target = SiemTarget(name="test", target_type="elastic")
        result = _format_elastic_ecs(event, target)
        assert result["event"]["kind"] == "event"
        assert result["event"]["outcome"] == "success"

    def test_sentinel_format(self):
        event = _make_gov_event()
        target = SiemTarget(name="test", target_type="sentinel")
        result = _format_sentinel(event, target)
        assert result["TimeGenerated"] == event.timestamp
        assert result["Severity"] == "CRITICAL"

    def test_cef_format(self):
        event = _make_gov_event()
        target = SiemTarget(name="test", target_type="syslog")
        result = _format_syslog_cef(event, target)
        assert result.startswith("CEF:0|NOVTIA|Governor|")
        assert "act=block" in result
        assert "risk=85" in result
        assert "cs1=shell" in result

    def test_generic_format(self):
        event = _make_gov_event()
        target = SiemTarget(name="test", target_type="generic_webhook")
        result = _format_generic(event, target)
        assert result["event_id"] == "evt-test001"


class TestSiemDispatcher:

    def test_add_and_list_targets(self):
        dispatcher = SiemDispatcher()
        dispatcher.add_target(SiemTarget(name="t1", target_type="generic_webhook", url="http://test"))
        dispatcher.add_target(SiemTarget(name="t2", target_type="splunk_hec", url="http://splunk"))
        targets = dispatcher.list_targets()
        assert len(targets) == 2

    def test_dispatch_and_deliver(self):
        mock = MockTransport()
        dispatcher = SiemDispatcher(transport=mock)
        dispatcher.add_target(SiemTarget(
            name="test", target_type="generic_webhook",
            url="http://siem.test/events",
            batch_size=1,  # Flush immediately
        ))

        event = _make_gov_event()
        results = dispatcher.dispatch(event)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].events_sent == 1
        assert len(mock.sent) == 1
        assert mock.sent[0]["url"] == "http://siem.test/events"

    def test_batch_flushing(self):
        mock = MockTransport()
        dispatcher = SiemDispatcher(transport=mock)
        dispatcher.add_target(SiemTarget(
            name="test", target_type="generic_webhook",
            url="http://siem.test/events",
            batch_size=3,
            flush_interval_seconds=999,  # Disable time-based flush
        ))

        # Dispatch 2 events — shouldn't flush yet
        dispatcher.dispatch(_make_gov_event(event_id="1"))
        dispatcher.dispatch(_make_gov_event(event_id="2"))
        assert len(mock.sent) == 0

        # 3rd event triggers batch flush
        dispatcher.dispatch(_make_gov_event(event_id="3"))
        assert len(mock.sent) == 1

    def test_severity_filtering(self):
        mock = MockTransport()
        dispatcher = SiemDispatcher(transport=mock)
        dispatcher.add_target(SiemTarget(
            name="high_only", target_type="generic_webhook",
            url="http://siem.test/events",
            min_severity="high",
            batch_size=1,
        ))

        # Low severity — filtered
        dispatcher.dispatch(_make_gov_event(severity="low"))
        assert len(mock.sent) == 0
        assert dispatcher.stats.total_filtered == 1

        # Critical — delivered
        dispatcher.dispatch(_make_gov_event(severity="critical"))
        assert len(mock.sent) == 1

    def test_decision_filtering(self):
        mock = MockTransport()
        dispatcher = SiemDispatcher(transport=mock)
        dispatcher.add_target(SiemTarget(
            name="blocks_only", target_type="generic_webhook",
            url="http://siem.test/events",
            decision_filter={"block"},
            batch_size=1,
        ))

        dispatcher.dispatch(_make_gov_event(decision="allow", severity="low"))
        assert len(mock.sent) == 0

        dispatcher.dispatch(_make_gov_event(decision="block"))
        assert len(mock.sent) == 1

    def test_retry_on_failure(self):
        mock = MockTransport()
        mock.fail_next = 2  # Fail first 2 attempts
        dispatcher = SiemDispatcher(transport=mock)
        dispatcher.add_target(SiemTarget(
            name="flaky", target_type="generic_webhook",
            url="http://siem.test/events",
            batch_size=1,
            max_retries=3,
            retry_delay_seconds=0.01,
        ))

        results = dispatcher.dispatch(_make_gov_event())
        assert results[0].success is True
        assert results[0].retries_used == 2

    def test_dead_letter_after_max_retries(self):
        mock = MockTransport()
        mock.fail_next = 10  # Always fail
        dispatcher = SiemDispatcher(transport=mock)
        dispatcher.add_target(SiemTarget(
            name="dead", target_type="generic_webhook",
            url="http://siem.test/events",
            batch_size=1,
            max_retries=2,
            retry_delay_seconds=0.01,
        ))

        results = dispatcher.dispatch(_make_gov_event())
        assert results[0].success is False
        assert len(dispatcher.get_dead_letter()) == 1
        assert dispatcher.stats.dead_letter_count == 1

    def test_flush_on_shutdown(self):
        mock = MockTransport()
        dispatcher = SiemDispatcher(transport=mock)
        dispatcher.add_target(SiemTarget(
            name="test", target_type="generic_webhook",
            url="http://test", batch_size=100,
        ))

        dispatcher.dispatch(_make_gov_event())
        dispatcher.dispatch(_make_gov_event())
        assert len(mock.sent) == 0  # Not yet flushed

        results = dispatcher.flush()
        assert len(mock.sent) == 1  # Flushed as batch
        assert results[0].events_sent == 2

    def test_splunk_hec_auth_header(self):
        mock = MockTransport()
        dispatcher = SiemDispatcher(transport=mock)
        dispatcher.add_target(SiemTarget(
            name="splunk", target_type="splunk_hec",
            url="http://splunk:8088/services/collector",
            auth_token="my-hec-token",
            batch_size=1,
        ))

        dispatcher.dispatch(_make_gov_event())
        assert mock.sent[0]["headers"]["Authorization"] == "Splunk my-hec-token"

    def test_remove_target_flushes(self):
        mock = MockTransport()
        dispatcher = SiemDispatcher(transport=mock)
        dispatcher.add_target(SiemTarget(
            name="test", target_type="generic_webhook",
            url="http://test", batch_size=100,
        ))
        dispatcher.dispatch(_make_gov_event())
        dispatcher.remove_target("test")
        assert len(mock.sent) == 1  # Flushed on remove

    def test_stats_tracking(self):
        mock = MockTransport()
        dispatcher = SiemDispatcher(transport=mock)
        dispatcher.add_target(SiemTarget(
            name="test", target_type="generic_webhook",
            url="http://test", batch_size=1,
        ))

        dispatcher.dispatch(_make_gov_event())
        dispatcher.dispatch(_make_gov_event())

        stats = dispatcher.stats
        assert stats.total_dispatched == 2
        assert stats.total_delivered == 2


# ═══════════════════════════════════════════════════════════
# ESCALATION CONNECTOR TESTS
# ═══════════════════════════════════════════════════════════

class TestEscalationFormatters:

    def test_slack_format(self):
        event = _make_esc_event()
        target = EscalationTarget(name="test", target_type="slack")
        result = _format_slack(event, target)
        assert "blocks" in result
        # Should have header, section with fields, explanation, chain pattern, deviations
        assert len(result["blocks"]) >= 4

    def test_slack_kill_switch(self):
        event = _make_esc_event(is_kill_switch=True)
        target = EscalationTarget(name="test", target_type="slack")
        result = _format_slack(event, target)
        blocks_text = json.dumps(result)
        assert "KILL SWITCH" in blocks_text

    def test_teams_format(self):
        event = _make_esc_event()
        target = EscalationTarget(name="test", target_type="teams")
        result = _format_teams(event, target)
        assert "@type" in result
        assert result["@type"] == "MessageCard"
        assert "sections" in result

    def test_jira_format(self):
        event = _make_esc_event()
        target = EscalationTarget(name="test", target_type="jira", jira_project_key="SEC")
        result = _format_jira(event, target)
        assert result["fields"]["project"]["key"] == "SEC"
        assert "BLOCK" in result["fields"]["summary"]
        assert "novtia-governor" in result["fields"]["labels"]

    def test_servicenow_format(self):
        event = _make_esc_event()
        target = EscalationTarget(name="test", target_type="servicenow")
        result = _format_servicenow(event, target)
        assert "short_description" in result
        assert "AI Governor" in result["short_description"]
        assert result["category"] == "AI Security"

    def test_pagerduty_format(self):
        event = _make_esc_event()
        target = EscalationTarget(name="test", target_type="pagerduty",
                                   pagerduty_routing_key="R123")
        result = _format_pagerduty(event, target)
        assert result["routing_key"] == "R123"
        assert result["event_action"] == "trigger"
        assert result["payload"]["severity"] == "critical"


class TestEscalationRouter:

    def test_basic_escalation(self):
        mock = EscMockTransport()
        router = EscalationRouter(transport=mock)
        router.add_target(EscalationTarget(
            name="slack", target_type="slack",
            url="http://slack.test/webhook",
        ))

        event = _make_esc_event()
        results = router.escalate(event)

        assert len(results) == 1
        assert results[0].success is True
        assert len(mock.sent) == 1

    def test_trigger_on_filter(self):
        mock = EscMockTransport()
        router = EscalationRouter(transport=mock)
        router.add_target(EscalationTarget(
            name="blocks_only", target_type="generic",
            url="http://test",
            trigger_on={"block"},
        ))

        # Review — should be filtered
        router.escalate(_make_esc_event(decision="review"))
        assert len(mock.sent) == 0

        # Block — should escalate
        router.escalate(_make_esc_event(decision="block"))
        assert len(mock.sent) == 1

    def test_risk_score_threshold(self):
        mock = EscMockTransport()
        router = EscalationRouter(transport=mock)
        router.add_target(EscalationTarget(
            name="high_risk", target_type="generic",
            url="http://test",
            min_risk_score=70,
            trigger_on_chain_pattern=False,
            trigger_on_deviations=False,
        ))

        # Low risk — filtered
        router.escalate(_make_esc_event(risk_score=30, chain_pattern=None, deviations=[]))
        assert len(mock.sent) == 0

        # High risk — escalated
        router.escalate(_make_esc_event(risk_score=85, chain_pattern=None, deviations=[]))
        assert len(mock.sent) == 1

    def test_chain_pattern_triggers_below_threshold(self):
        mock = EscMockTransport()
        router = EscalationRouter(transport=mock)
        router.add_target(EscalationTarget(
            name="chain_aware", target_type="generic",
            url="http://test",
            min_risk_score=90,  # High threshold
            trigger_on_chain_pattern=True,
        ))

        # Below threshold but has chain pattern — should trigger
        router.escalate(_make_esc_event(risk_score=50, chain_pattern="credential_then_exfil"))
        assert len(mock.sent) == 1

    def test_deviation_triggers_below_threshold(self):
        mock = EscMockTransport()
        router = EscalationRouter(transport=mock)
        router.add_target(EscalationTarget(
            name="deviation_aware", target_type="generic",
            url="http://test",
            min_risk_score=90,
            trigger_on_deviations=True,
        ))

        router.escalate(_make_esc_event(
            risk_score=50, chain_pattern=None,
            deviations=[{"deviation_type": "novel_tool", "severity": 25}],
        ))
        assert len(mock.sent) == 1

    def test_kill_switch_always_triggers(self):
        mock = EscMockTransport()
        router = EscalationRouter(transport=mock)
        router.add_target(EscalationTarget(
            name="test", target_type="generic",
            url="http://test",
            trigger_on={"block"},  # Only blocks
            min_risk_score=99,     # Very high threshold
        ))

        # Kill switch overrides all filters
        router.escalate(_make_esc_event(
            decision="review", risk_score=10,
            is_kill_switch=True, chain_pattern=None, deviations=[],
        ))
        assert len(mock.sent) == 1

    def test_multiple_targets(self):
        mock = EscMockTransport()
        router = EscalationRouter(transport=mock)
        router.add_target(EscalationTarget(name="slack", target_type="slack", url="http://slack"))
        router.add_target(EscalationTarget(name="jira", target_type="jira", url="http://jira",
                                            jira_project_key="SEC"))
        router.add_target(EscalationTarget(name="pd", target_type="pagerduty", url="http://pd",
                                            pagerduty_routing_key="R1"))

        results = router.escalate(_make_esc_event())
        assert len(results) == 3
        assert all(r.success for r in results)
        assert len(mock.sent) == 3

    def test_retry_on_failure(self):
        mock = EscMockTransport()
        mock.fail_next = 1
        router = EscalationRouter(transport=mock)
        router.add_target(EscalationTarget(
            name="flaky", target_type="generic",
            url="http://test",
            max_retries=2,
            retry_delay_seconds=0.01,
        ))

        results = router.escalate(_make_esc_event())
        assert results[0].success is True
        assert results[0].retries_used == 1

    def test_stats_tracking(self):
        mock = EscMockTransport()
        router = EscalationRouter(transport=mock)
        router.add_target(EscalationTarget(
            name="test", target_type="generic", url="http://test",
            trigger_on={"block"},
        ))

        router.escalate(_make_esc_event(decision="block"))
        router.escalate(_make_esc_event(decision="allow"))  # Filtered
        router.escalate(_make_esc_event(decision="block"))

        stats = router.stats
        assert stats.total_events == 3
        assert stats.total_escalated == 2
        assert stats.total_filtered == 1

    def test_disabled_target_skipped(self):
        mock = EscMockTransport()
        router = EscalationRouter(transport=mock)
        router.add_target(EscalationTarget(
            name="disabled", target_type="generic",
            url="http://test", enabled=False,
        ))

        router.escalate(_make_esc_event())
        assert len(mock.sent) == 0

    def test_list_targets(self):
        router = EscalationRouter()
        router.add_target(EscalationTarget(name="s1", target_type="slack", url="http://s1"))
        router.add_target(EscalationTarget(name="j1", target_type="jira", url="http://j1",
                                            jira_project_key="AI"))
        targets = router.list_targets()
        assert len(targets) == 2
        assert targets[0]["type"] == "slack"
        assert targets[1]["type"] == "jira"
