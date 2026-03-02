"""
Impact Assessment — Test Suite
================================
Run: pytest tests/test_impact.py -v
"""
import time
import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from impact_assessment import (
    ImpactAssessmentEngine, AssessmentPeriod,
    _compute_risk_distribution, _classify_risk_level, _generate_recommendations,
)


@pytest.fixture
def engine():
    return ImpactAssessmentEngine()


@pytest.fixture
def loaded_engine(engine):
    """Engine with realistic evaluation data across 3 agents and 5 tools."""
    now = time.time()
    # Agent 1: well-behaved, mostly reads and summarises
    for i in range(100):
        engine.record(
            tool=["read_file", "summarize", "respond"][i % 3],
            decision="allow", risk_score=5 + (i % 10),
            agent_id="agent_good", session_id=f"sess_{i // 10}",
            policy_ids=["pol_base"], timestamp=now - (100 - i) * 300,
        )

    # Agent 2: risky, triggers blocks and chains
    for i in range(60):
        decision = "block" if i % 5 == 0 else ("review" if i % 7 == 0 else "allow")
        engine.record(
            tool=["shell", "http_post", "read_file", "write_file"][i % 4],
            decision=decision,
            risk_score=30 + (i % 50),
            agent_id="agent_risky", session_id=f"rsess_{i // 8}",
            policy_ids=["pol_sec_1", "pol_inject_1"] if decision == "block" else ["pol_base"],
            chain_pattern="credential_then_exfil" if i % 15 == 0 else None,
            deviation_types=["novel_tool"] if i % 10 == 0 else [],
            explanation="Injection detected" if decision == "block" else "Normal",
            timestamp=now - (60 - i) * 500,
        )

    # Agent 3: moderate, some deviations
    for i in range(40):
        engine.record(
            tool=["search", "respond", "http_get"][i % 3],
            decision="allow" if i % 8 != 0 else "review",
            risk_score=15 + (i % 25),
            agent_id="agent_mid", session_id=f"msess_{i // 5}",
            policy_ids=["pol_base"],
            deviation_types=["sequence_anomaly"] if i % 12 == 0 else [],
            timestamp=now - (40 - i) * 400,
        )

    engine.register_policy("pol_base")
    engine.register_policy("pol_sec_1")
    engine.register_policy("pol_inject_1")
    engine.register_policy("pol_unused")

    return engine


# ═══ STATISTICS HELPERS ═══

class TestRiskDistribution:

    def test_empty_scores(self):
        dist = _compute_risk_distribution([])
        assert dist.count == 0
        assert dist.mean == 0.0

    def test_single_score(self):
        dist = _compute_risk_distribution([50])
        assert dist.count == 1
        assert dist.mean == 50.0
        assert dist.median == 50.0

    def test_distribution_stats(self):
        scores = list(range(0, 101))  # 0 to 100
        dist = _compute_risk_distribution(scores)
        assert dist.count == 101
        assert dist.mean == 50.0
        assert dist.median == 50.0
        assert dist.min == 0
        assert dist.max == 100
        assert dist.p90 >= 89
        assert dist.p95 >= 94

    def test_buckets(self):
        scores = [5, 15, 30, 60, 80, 95]
        dist = _compute_risk_distribution(scores)
        assert dist.buckets["0-10"] == 1
        assert dist.buckets["11-25"] == 1
        assert dist.buckets["26-50"] == 1
        assert dist.buckets["51-75"] == 1
        assert dist.buckets["76-90"] == 1
        assert dist.buckets["91-100"] == 1


class TestRiskClassification:

    def test_minimal_risk(self):
        assert _classify_risk_level(0, 5, 0, 0, 100) == "minimal"

    def test_low_risk(self):
        assert _classify_risk_level(2, 15, 1, 0, 100) == "low"

    def test_moderate_risk(self):
        assert _classify_risk_level(3, 20, 2, 1, 100) == "moderate"

    def test_high_risk(self):
        assert _classify_risk_level(6, 35, 3, 2, 100) == "high"

    def test_critical_risk(self):
        assert _classify_risk_level(20, 60, 20, 15, 100) == "critical"

    def test_zero_evaluations(self):
        assert _classify_risk_level(0, 0, 0, 0, 0) == "minimal"


class TestRecommendations:

    def test_high_block_rate(self):
        recs = _generate_recommendations(20.0, 30.0, {}, {}, [], 100)
        assert any("block rate" in r.lower() for r in recs)

    def test_chain_pattern_warning(self):
        recs = _generate_recommendations(5.0, 20.0, {"cred_exfil": 8}, {}, [], 100)
        assert any("chain pattern" in r.lower() for r in recs)

    def test_deviation_warning(self):
        recs = _generate_recommendations(5.0, 20.0, {}, {"novel_tool": 12}, [], 100)
        assert any("deviation" in r.lower() for r in recs)

    def test_smooth_operation(self):
        recs = _generate_recommendations(0.5, 5.0, {}, {}, [], 200)
        assert any("smoothly" in r.lower() for r in recs)

    def test_no_data(self):
        recs = _generate_recommendations(0, 0, {}, {}, [], 0)
        assert len(recs) >= 1


# ═══ FULL ASSESSMENT ═══

class TestFullAssessment:

    def test_empty_assessment(self, engine):
        report = engine.assess()
        assert report.total_evaluations == 0
        assert report.overall_risk_level == "minimal"

    def test_assessment_totals(self, loaded_engine):
        report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        assert report.total_evaluations == 200  # 100 + 60 + 40
        assert report.unique_agents == 3
        assert report.unique_tools >= 5

    def test_decision_breakdown(self, loaded_engine):
        report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        assert "allow" in report.decision_breakdown
        assert "block" in report.decision_breakdown
        assert sum(report.decision_breakdown.values()) == 200

    def test_risk_distribution_present(self, loaded_engine):
        report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        dist = report.risk_distribution
        assert dist["count"] == 200
        assert dist["mean"] > 0
        assert "buckets" in dist

    def test_chain_patterns_detected(self, loaded_engine):
        report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        assert "credential_then_exfil" in report.chain_patterns

    def test_deviation_types_detected(self, loaded_engine):
        report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        assert "novel_tool" in report.deviation_types

    def test_top_risk_agents(self, loaded_engine):
        report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        assert len(report.top_risk_agents) >= 1
        # agent_risky should be highest risk
        agent_ids = [a["agent_id"] for a in report.top_risk_agents]
        assert "agent_risky" in agent_ids

    def test_top_risk_tools(self, loaded_engine):
        report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        assert len(report.top_risk_tools) >= 1

    def test_daily_trends(self, loaded_engine):
        report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        assert len(report.daily_trends) >= 1
        for trend in report.daily_trends:
            assert "evaluations" in trend
            assert "blocks" in trend
            assert "avg_risk" in trend

    def test_policy_effectiveness(self, loaded_engine):
        report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        assert "pol_base" in report.policy_hit_counts
        assert "pol_unused" in report.policies_never_triggered

    def test_recommendations_present(self, loaded_engine):
        report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        assert len(report.recommendations) >= 1

    def test_compliance_coverage(self, loaded_engine):
        report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        assert "iso_42001_clause_6" in report.compliance_coverage
        assert "nist_map_5" in report.compliance_coverage
        assert "eu_ai_act_art_9" in report.compliance_coverage

    def test_serializable(self, loaded_engine):
        report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        json_str = json.dumps(report.to_dict())
        parsed = json.loads(json_str)
        assert parsed["total_evaluations"] == 200

    def test_period_filtering(self, loaded_engine):
        all_report = loaded_engine.assess(period=AssessmentPeriod.ALL_TIME)
        day_report = loaded_engine.assess(period=AssessmentPeriod.LAST_24H)
        # 24h should have fewer or equal evaluations
        assert day_report.total_evaluations <= all_report.total_evaluations


# ═══ AGENT ASSESSMENT ═══

class TestAgentAssessment:

    def test_good_agent(self, loaded_engine):
        profile = loaded_engine.assess_agent("agent_good", AssessmentPeriod.ALL_TIME)
        assert profile.total_evaluations == 100
        assert profile.block_rate_pct == 0.0
        assert profile.risk_level in ("minimal", "low")

    def test_risky_agent(self, loaded_engine):
        profile = loaded_engine.assess_agent("agent_risky", AssessmentPeriod.ALL_TIME)
        assert profile.total_evaluations == 60
        assert profile.block_rate_pct > 0
        assert "credential_then_exfil" in profile.chain_patterns_detected
        assert "novel_tool" in profile.deviation_types
        assert len(profile.top_blocked_tools) >= 1

    def test_unknown_agent(self, loaded_engine):
        profile = loaded_engine.assess_agent("nonexistent", AssessmentPeriod.ALL_TIME)
        assert profile.total_evaluations == 0
        assert profile.risk_level == "minimal"

    def test_agent_active_hours(self, loaded_engine):
        profile = loaded_engine.assess_agent("agent_good", AssessmentPeriod.ALL_TIME)
        assert profile.active_hours > 0

    def test_agent_serializable(self, loaded_engine):
        profile = loaded_engine.assess_agent("agent_risky", AssessmentPeriod.ALL_TIME)
        json_str = json.dumps(profile.to_dict())
        parsed = json.loads(json_str)
        assert parsed["agent_id"] == "agent_risky"


# ═══ TOOL ASSESSMENT ═══

class TestToolAssessment:

    def test_safe_tool(self, loaded_engine):
        profile = loaded_engine.assess_tool("respond", AssessmentPeriod.ALL_TIME)
        assert profile.total_evaluations > 0
        assert profile.block_rate_pct == 0.0

    def test_risky_tool(self, loaded_engine):
        profile = loaded_engine.assess_tool("shell", AssessmentPeriod.ALL_TIME)
        assert profile.total_evaluations > 0
        assert profile.block_rate_pct > 0

    def test_tool_agents_count(self, loaded_engine):
        profile = loaded_engine.assess_tool("read_file", AssessmentPeriod.ALL_TIME)
        assert profile.agents_using >= 1

    def test_unknown_tool(self, loaded_engine):
        profile = loaded_engine.assess_tool("nonexistent", AssessmentPeriod.ALL_TIME)
        assert profile.total_evaluations == 0

    def test_tool_serializable(self, loaded_engine):
        profile = loaded_engine.assess_tool("shell", AssessmentPeriod.ALL_TIME)
        json_str = json.dumps(profile.to_dict())
        parsed = json.loads(json_str)
        assert parsed["tool"] == "shell"


# ═══ QUERY ═══

class TestQueries:

    def test_list_agents(self, loaded_engine):
        agents = loaded_engine.list_agents()
        assert "agent_good" in agents
        assert "agent_risky" in agents
        assert "agent_mid" in agents

    def test_list_tools(self, loaded_engine):
        tools = loaded_engine.list_tools()
        assert "shell" in tools
        assert "respond" in tools

    def test_total_records(self, loaded_engine):
        assert loaded_engine.total_records == 200


# ═══ EDGE CASES ═══

class TestEdgeCases:

    def test_single_record(self, engine):
        engine.record(tool="test", decision="allow", risk_score=50)
        report = engine.assess(AssessmentPeriod.ALL_TIME)
        assert report.total_evaluations == 1
        assert report.risk_distribution["mean"] == 50.0

    def test_all_blocks(self, engine):
        for i in range(20):
            engine.record(tool="shell", decision="block", risk_score=90,
                          agent_id="bad_agent", explanation="Blocked")
        report = engine.assess(AssessmentPeriod.ALL_TIME)
        assert report.block_rate_pct == 100.0
        assert report.overall_risk_level in ("high", "critical")

    def test_max_records_pruning(self):
        engine = ImpactAssessmentEngine(max_records=50)
        for i in range(100):
            engine.record(tool="test", decision="allow", risk_score=10)
        assert engine.total_records == 50
