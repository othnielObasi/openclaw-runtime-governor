"""
NOVTIA Governor — Impact Assessment Engine
============================================
Aggregates governance data into structured risk reports for compliance
teams to complete their AI impact assessments using real production data.

Covers:
  - ISO 42001 Clause 6 (Planning — risk assessment)
  - NIST AI RMF MAP-5 (Impact assessment)
  - EU AI Act Art.9 (Risk management system — continuous assessment)

The engine doesn't invent data. It summarises what the Governor already
records: every evaluation's risk score, decision, tool, agent, policy,
chain pattern, and fingerprint deviation.

Integration:
    from impact_assessment import ImpactAssessmentEngine, AssessmentPeriod

    engine = ImpactAssessmentEngine()

    # Feed evaluations (or connect to your existing evaluation store)
    engine.record(tool, decision, risk_score, agent_id, ...)

    # Generate assessment
    report = engine.assess(period=AssessmentPeriod.LAST_30_DAYS)
    report = engine.assess_agent("agent_001")
    report = engine.assess_tool("shell")
"""
from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from enum import Enum


# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

class AssessmentPeriod(str, Enum):
    LAST_24H = "24h"
    LAST_7D = "7d"
    LAST_30D = "30d"
    LAST_90D = "90d"
    ALL_TIME = "all"


class RiskLevel(str, Enum):
    MINIMAL = "minimal"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


PERIOD_SECONDS = {
    AssessmentPeriod.LAST_24H: 86400,
    AssessmentPeriod.LAST_7D: 604800,
    AssessmentPeriod.LAST_30D: 2592000,
    AssessmentPeriod.LAST_90D: 7776000,
    AssessmentPeriod.ALL_TIME: None,
}


# ═══════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════

@dataclass
class EvaluationRecord:
    """Single evaluation record for assessment aggregation."""
    timestamp: float
    tool: str
    decision: str
    risk_score: int
    agent_id: str
    session_id: str
    policy_ids: List[str]
    chain_pattern: Optional[str] = None
    deviation_types: List[str] = field(default_factory=list)
    explanation: str = ""


@dataclass
class RiskDistribution:
    """Risk score distribution statistics."""
    count: int = 0
    mean: float = 0.0
    median: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    max: float = 0.0
    min: float = 0.0
    std_dev: float = 0.0
    buckets: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "mean": round(self.mean, 2),
            "median": round(self.median, 2),
            "p90": round(self.p90, 2),
            "p95": round(self.p95, 2),
            "p99": round(self.p99, 2),
            "max": round(self.max, 2),
            "min": round(self.min, 2),
            "std_dev": round(self.std_dev, 2),
            "buckets": self.buckets,
        }


@dataclass
class TrendPoint:
    """Single point in a time series."""
    period_start: str
    period_end: str
    evaluations: int
    blocks: int
    reviews: int
    avg_risk: float
    chain_patterns: int
    deviations: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "evaluations": self.evaluations,
            "blocks": self.blocks,
            "reviews": self.reviews,
            "avg_risk": round(self.avg_risk, 2),
            "chain_patterns": self.chain_patterns,
            "deviations": self.deviations,
        }


@dataclass
class AgentRiskProfile:
    """Risk assessment for a single agent."""
    agent_id: str
    total_evaluations: int
    risk_level: str
    risk_distribution: Dict[str, Any]
    decision_breakdown: Dict[str, int]
    block_rate_pct: float
    top_blocked_tools: List[Tuple[str, int]]
    chain_patterns_detected: Dict[str, int]
    deviation_types: Dict[str, int]
    unique_tools: int
    active_hours: float
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "total_evaluations": self.total_evaluations,
            "risk_level": self.risk_level,
            "risk_distribution": self.risk_distribution,
            "decision_breakdown": self.decision_breakdown,
            "block_rate_pct": round(self.block_rate_pct, 2),
            "top_blocked_tools": [{"tool": t, "count": c} for t, c in self.top_blocked_tools],
            "chain_patterns_detected": self.chain_patterns_detected,
            "deviation_types": self.deviation_types,
            "unique_tools": self.unique_tools,
            "active_hours": round(self.active_hours, 1),
            "recommendations": self.recommendations,
        }


@dataclass
class ToolRiskProfile:
    """Risk assessment for a single tool."""
    tool: str
    total_evaluations: int
    risk_level: str
    risk_distribution: Dict[str, Any]
    decision_breakdown: Dict[str, int]
    block_rate_pct: float
    agents_using: int
    chain_patterns_involving: Dict[str, int]
    common_block_reasons: List[Tuple[str, int]]
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "total_evaluations": self.total_evaluations,
            "risk_level": self.risk_level,
            "risk_distribution": self.risk_distribution,
            "decision_breakdown": self.decision_breakdown,
            "block_rate_pct": round(self.block_rate_pct, 2),
            "agents_using": self.agents_using,
            "chain_patterns_involving": self.chain_patterns_involving,
            "common_block_reasons": [{"reason": r, "count": c} for r, c in self.common_block_reasons],
            "recommendations": self.recommendations,
        }


@dataclass
class ImpactAssessmentReport:
    """Full impact assessment report."""
    generated_at: str
    period: str
    period_start: str
    period_end: str

    # Overview
    total_evaluations: int
    unique_agents: int
    unique_tools: int
    unique_sessions: int

    # Overall risk
    overall_risk_level: str
    risk_distribution: Dict[str, Any]
    decision_breakdown: Dict[str, int]
    block_rate_pct: float

    # Threat landscape
    chain_patterns: Dict[str, int]
    deviation_types: Dict[str, int]
    top_risk_agents: List[Dict[str, Any]]
    top_risk_tools: List[Dict[str, Any]]

    # Trends
    daily_trends: List[Dict[str, Any]]

    # Policy effectiveness
    policy_hit_counts: Dict[str, int]
    policies_never_triggered: List[str]

    # Compliance
    compliance_coverage: Dict[str, Any]

    # Recommendations
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "period": self.period,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_evaluations": self.total_evaluations,
            "unique_agents": self.unique_agents,
            "unique_tools": self.unique_tools,
            "unique_sessions": self.unique_sessions,
            "overall_risk_level": self.overall_risk_level,
            "risk_distribution": self.risk_distribution,
            "decision_breakdown": self.decision_breakdown,
            "block_rate_pct": round(self.block_rate_pct, 2),
            "chain_patterns": self.chain_patterns,
            "deviation_types": self.deviation_types,
            "top_risk_agents": self.top_risk_agents,
            "top_risk_tools": self.top_risk_tools,
            "daily_trends": self.daily_trends,
            "policy_hit_counts": self.policy_hit_counts,
            "policies_never_triggered": self.policies_never_triggered,
            "compliance_coverage": self.compliance_coverage,
            "recommendations": self.recommendations,
        }


# ═══════════════════════════════════════════════════════════
# STATISTICS HELPERS
# ═══════════════════════════════════════════════════════════

def _compute_risk_distribution(scores: List[int]) -> RiskDistribution:
    """Compute statistical distribution of risk scores."""
    if not scores:
        return RiskDistribution()

    sorted_scores = sorted(scores)
    n = len(sorted_scores)

    mean = sum(sorted_scores) / n
    variance = sum((s - mean) ** 2 for s in sorted_scores) / max(n - 1, 1)
    std_dev = math.sqrt(variance)

    def percentile(p):
        idx = (p / 100) * (n - 1)
        lower = int(math.floor(idx))
        upper = min(lower + 1, n - 1)
        frac = idx - lower
        return sorted_scores[lower] + frac * (sorted_scores[upper] - sorted_scores[lower])

    buckets = {
        "0-10": sum(1 for s in sorted_scores if s <= 10),
        "11-25": sum(1 for s in sorted_scores if 11 <= s <= 25),
        "26-50": sum(1 for s in sorted_scores if 26 <= s <= 50),
        "51-75": sum(1 for s in sorted_scores if 51 <= s <= 75),
        "76-90": sum(1 for s in sorted_scores if 76 <= s <= 90),
        "91-100": sum(1 for s in sorted_scores if s >= 91),
    }

    return RiskDistribution(
        count=n,
        mean=mean,
        median=percentile(50),
        p90=percentile(90),
        p95=percentile(95),
        p99=percentile(99),
        max=sorted_scores[-1],
        min=sorted_scores[0],
        std_dev=std_dev,
        buckets=buckets,
    )


def _classify_risk_level(block_rate: float, avg_risk: float, chain_count: int,
                          deviation_count: int, total: int) -> str:
    """Classify overall risk level from aggregated metrics."""
    if total == 0:
        return "minimal"

    score = 0
    score += min(block_rate * 2, 30)         # Block rate contributes up to 30
    score += min(avg_risk / 2, 25)            # Avg risk contributes up to 25
    score += min(chain_count / max(total, 1) * 500, 25)  # Chain rate up to 25
    score += min(deviation_count / max(total, 1) * 300, 20)  # Deviation rate up to 20

    if score >= 60:
        return "critical"
    elif score >= 40:
        return "high"
    elif score >= 20:
        return "moderate"
    elif score >= 8:
        return "low"
    return "minimal"


def _generate_recommendations(block_rate: float, avg_risk: float,
                                chain_patterns: Dict[str, int],
                                deviation_types: Dict[str, int],
                                top_blocked_tools: List[Tuple[str, int]],
                                total: int) -> List[str]:
    """Generate actionable recommendations from assessment data."""
    recs = []

    if block_rate > 15:
        recs.append(
            f"Block rate is {block_rate:.1f}%, significantly above the 5% baseline. "
            f"Review blocked tool configurations — high block rates may indicate "
            f"overly restrictive policies or agents attempting unauthorized actions."
        )
    elif block_rate > 5:
        recs.append(
            f"Block rate is {block_rate:.1f}%, above the 5% baseline. "
            f"Monitor for trends — rising block rates suggest policy tightening or agent misconfiguration."
        )

    if avg_risk > 40:
        recs.append(
            f"Average risk score is {avg_risk:.1f}/100. Consider reviewing agents with "
            f"consistently high risk scores for scope reduction or additional policy constraints."
        )

    if chain_patterns:
        top_pattern = max(chain_patterns.items(), key=lambda x: x[1])
        recs.append(
            f"Chain pattern '{top_pattern[0]}' detected {top_pattern[1]} times. "
            f"This indicates multi-step attack sequences — review the agents and sessions involved."
        )

    if deviation_types:
        top_dev = max(deviation_types.items(), key=lambda x: x[1])
        recs.append(
            f"Fingerprint deviation '{top_dev[0]}' occurred {top_dev[1]} times. "
            f"If legitimate, consider updating agent baselines. If unexpected, investigate."
        )

    if top_blocked_tools:
        tool_name, count = top_blocked_tools[0]
        recs.append(
            f"Tool '{tool_name}' was blocked {count} times (most blocked). "
            f"Evaluate whether this tool should be removed from agent scope or policies adjusted."
        )

    if total > 100 and block_rate < 1 and avg_risk < 10:
        recs.append(
            "Very low block rate and risk scores across a significant evaluation volume. "
            "Governance is operating smoothly. Consider reviewing policies to ensure "
            "they are not under-detecting — run a red team exercise to validate."
        )

    if not recs:
        recs.append("No specific concerns identified in this assessment period.")

    return recs


# ═══════════════════════════════════════════════════════════
# IMPACT ASSESSMENT ENGINE
# ═══════════════════════════════════════════════════════════

class ImpactAssessmentEngine:
    """
    Aggregates governance data into structured impact assessments.

    Supports two modes:
    - In-memory: records stored in self._records (for tests / standalone)
    - DB-backed: query_backend callable returns records from ActionLog

    Usage:
        engine = ImpactAssessmentEngine()

        # Mode 1: In-memory
        engine.record(tool, decision, risk_score, agent_id, ...)
        report = engine.assess(period=AssessmentPeriod.LAST_30D)

        # Mode 2: DB-backed
        engine.set_query_backend(db_query_fn)
        report = engine.assess(period=AssessmentPeriod.LAST_30D)
    """

    def __init__(self, max_records: int = 100000):
        self._records: List[EvaluationRecord] = []
        self._max_records = max_records
        self._all_policy_ids: Set[str] = set()
        self._query_backend: Optional[Any] = None

    def set_query_backend(self, backend_fn):
        """Set a DB query backend.

        backend_fn(period: AssessmentPeriod) -> List[EvaluationRecord]

        When set, _filter_by_period uses the backend instead of _records.
        """
        self._query_backend = backend_fn

    def record(
        self,
        tool: str,
        decision: str,
        risk_score: int,
        agent_id: str = "unknown",
        session_id: str = "default",
        policy_ids: Optional[List[str]] = None,
        chain_pattern: Optional[str] = None,
        deviation_types: Optional[List[str]] = None,
        explanation: str = "",
        timestamp: Optional[float] = None,
    ):
        """Record an evaluation for impact assessment."""
        policy_ids = policy_ids or []
        self._all_policy_ids.update(policy_ids)

        rec = EvaluationRecord(
            timestamp=timestamp or time.time(),
            tool=tool,
            decision=decision,
            risk_score=risk_score,
            agent_id=agent_id,
            session_id=session_id,
            policy_ids=policy_ids,
            chain_pattern=chain_pattern,
            deviation_types=deviation_types or [],
            explanation=explanation,
        )
        self._records.append(rec)

        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

    def register_policy(self, policy_id: str):
        """Register a policy ID so we can track never-triggered policies."""
        self._all_policy_ids.add(policy_id)

    def _filter_by_period(self, period: AssessmentPeriod) -> List[EvaluationRecord]:
        """Filter records by time period. Uses DB backend when available."""
        if self._query_backend:
            try:
                return self._query_backend(period)
            except Exception:
                pass  # Fall back to in-memory

        cutoff_secs = PERIOD_SECONDS.get(period)
        if cutoff_secs is None:
            return list(self._records)
        cutoff = time.time() - cutoff_secs
        return [r for r in self._records if r.timestamp >= cutoff]

    # ─── FULL ASSESSMENT ───

    def assess(self, period: AssessmentPeriod = AssessmentPeriod.LAST_30D) -> ImpactAssessmentReport:
        """Generate a full impact assessment report."""
        records = self._filter_by_period(period)
        now = datetime.now(timezone.utc)

        cutoff_secs = PERIOD_SECONDS.get(period)
        if cutoff_secs:
            period_start = (now - timedelta(seconds=cutoff_secs)).isoformat()
        elif records:
            period_start = datetime.fromtimestamp(records[0].timestamp, tz=timezone.utc).isoformat()
        else:
            period_start = now.isoformat()

        total = len(records)
        if total == 0:
            return ImpactAssessmentReport(
                generated_at=now.isoformat(),
                period=period.value,
                period_start=period_start,
                period_end=now.isoformat(),
                total_evaluations=0, unique_agents=0, unique_tools=0, unique_sessions=0,
                overall_risk_level="minimal",
                risk_distribution=RiskDistribution().to_dict(),
                decision_breakdown={}, block_rate_pct=0.0,
                chain_patterns={}, deviation_types={},
                top_risk_agents=[], top_risk_tools=[],
                daily_trends=[], policy_hit_counts={},
                policies_never_triggered=list(self._all_policy_ids),
                compliance_coverage={}, recommendations=["No data in this period."],
            )

        # Basic aggregations
        agents = set()
        tools = set()
        sessions = set()
        decisions: Dict[str, int] = defaultdict(int)
        risk_scores: List[int] = []
        chain_patterns: Dict[str, int] = defaultdict(int)
        deviation_types: Dict[str, int] = defaultdict(int)
        policy_hits: Dict[str, int] = defaultdict(int)
        agent_risks: Dict[str, List[int]] = defaultdict(list)
        agent_blocks: Dict[str, int] = defaultdict(int)
        agent_totals: Dict[str, int] = defaultdict(int)
        tool_risks: Dict[str, List[int]] = defaultdict(list)
        tool_blocks: Dict[str, int] = defaultdict(int)
        tool_totals: Dict[str, int] = defaultdict(int)
        tool_agents: Dict[str, Set[str]] = defaultdict(set)

        for r in records:
            agents.add(r.agent_id)
            tools.add(r.tool)
            sessions.add(r.session_id)
            decisions[r.decision] += 1
            risk_scores.append(r.risk_score)

            if r.chain_pattern:
                chain_patterns[r.chain_pattern] += 1

            for dt in r.deviation_types:
                deviation_types[dt] += 1

            for pid in r.policy_ids:
                policy_hits[pid] += 1

            agent_risks[r.agent_id].append(r.risk_score)
            agent_totals[r.agent_id] += 1
            if r.decision == "block":
                agent_blocks[r.agent_id] += 1

            tool_risks[r.tool].append(r.risk_score)
            tool_totals[r.tool] += 1
            tool_agents[r.tool].add(r.agent_id)
            if r.decision == "block":
                tool_blocks[r.tool] += 1

        block_count = decisions.get("block", 0)
        block_rate = (block_count / total) * 100
        avg_risk = sum(risk_scores) / total

        risk_dist = _compute_risk_distribution(risk_scores)
        risk_level = _classify_risk_level(
            block_rate, avg_risk,
            sum(chain_patterns.values()),
            sum(deviation_types.values()),
            total,
        )

        # Top risk agents (by avg risk score)
        top_agents = sorted(
            agent_risks.items(),
            key=lambda x: sum(x[1]) / len(x[1]),
            reverse=True,
        )[:10]
        top_risk_agents = [
            {
                "agent_id": aid,
                "evaluations": agent_totals[aid],
                "avg_risk": round(sum(scores) / len(scores), 2),
                "block_rate_pct": round(agent_blocks.get(aid, 0) / agent_totals[aid] * 100, 2),
                "max_risk": max(scores),
            }
            for aid, scores in top_agents
        ]

        # Top risk tools
        top_tools = sorted(
            tool_risks.items(),
            key=lambda x: sum(x[1]) / len(x[1]),
            reverse=True,
        )[:10]
        top_risk_tools = [
            {
                "tool": t,
                "evaluations": tool_totals[t],
                "avg_risk": round(sum(scores) / len(scores), 2),
                "block_rate_pct": round(tool_blocks.get(t, 0) / tool_totals[t] * 100, 2),
                "agents_using": len(tool_agents[t]),
            }
            for t, scores in top_tools
        ]

        # Daily trends
        daily_trends = self._compute_daily_trends(records)

        # Policy effectiveness
        triggered_policies = set(policy_hits.keys())
        never_triggered = sorted(self._all_policy_ids - triggered_policies)

        # Top blocked tools for recommendations
        blocked_per_tool = sorted(tool_blocks.items(), key=lambda x: -x[1])[:5]

        # Compliance coverage
        compliance = {
            "iso_42001_clause_6": "Evidence generated: risk distributions, agent profiles, tool assessments, trend analysis",
            "nist_map_5": "Evidence generated: impact data per agent/tool, risk classification, recommendations",
            "eu_ai_act_art_9": "Evidence generated: continuous risk assessment with statistical distributions and trends",
        }

        # Recommendations
        recommendations = _generate_recommendations(
            block_rate, avg_risk, dict(chain_patterns),
            dict(deviation_types), blocked_per_tool, total,
        )

        return ImpactAssessmentReport(
            generated_at=now.isoformat(),
            period=period.value,
            period_start=period_start,
            period_end=now.isoformat(),
            total_evaluations=total,
            unique_agents=len(agents),
            unique_tools=len(tools),
            unique_sessions=len(sessions),
            overall_risk_level=risk_level,
            risk_distribution=risk_dist.to_dict(),
            decision_breakdown=dict(decisions),
            block_rate_pct=block_rate,
            chain_patterns=dict(chain_patterns),
            deviation_types=dict(deviation_types),
            top_risk_agents=top_risk_agents,
            top_risk_tools=top_risk_tools,
            daily_trends=[t.to_dict() for t in daily_trends],
            policy_hit_counts=dict(policy_hits),
            policies_never_triggered=never_triggered,
            compliance_coverage=compliance,
            recommendations=recommendations,
        )

    def _compute_daily_trends(self, records: List[EvaluationRecord]) -> List[TrendPoint]:
        """Compute daily aggregated trends."""
        if not records:
            return []

        # Group by day
        daily: Dict[str, List[EvaluationRecord]] = defaultdict(list)
        for r in records:
            day = datetime.fromtimestamp(r.timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
            daily[day].append(r)

        trends = []
        for day in sorted(daily.keys()):
            recs = daily[day]
            trends.append(TrendPoint(
                period_start=f"{day}T00:00:00Z",
                period_end=f"{day}T23:59:59Z",
                evaluations=len(recs),
                blocks=sum(1 for r in recs if r.decision == "block"),
                reviews=sum(1 for r in recs if r.decision == "review"),
                avg_risk=sum(r.risk_score for r in recs) / len(recs),
                chain_patterns=sum(1 for r in recs if r.chain_pattern),
                deviations=sum(len(r.deviation_types) for r in recs),
            ))

        return trends

    # ─── AGENT ASSESSMENT ───

    def assess_agent(self, agent_id: str,
                     period: AssessmentPeriod = AssessmentPeriod.LAST_30D) -> AgentRiskProfile:
        """Generate risk profile for a specific agent."""
        records = [r for r in self._filter_by_period(period) if r.agent_id == agent_id]
        total = len(records)

        if total == 0:
            return AgentRiskProfile(
                agent_id=agent_id, total_evaluations=0, risk_level="minimal",
                risk_distribution=RiskDistribution().to_dict(),
                decision_breakdown={}, block_rate_pct=0.0,
                top_blocked_tools=[], chain_patterns_detected={},
                deviation_types={}, unique_tools=0, active_hours=0.0,
                recommendations=["No data for this agent in the selected period."],
            )

        scores = [r.risk_score for r in records]
        decisions: Dict[str, int] = defaultdict(int)
        tools = set()
        blocked_tools: Dict[str, int] = defaultdict(int)
        chains: Dict[str, int] = defaultdict(int)
        devs: Dict[str, int] = defaultdict(int)

        for r in records:
            decisions[r.decision] += 1
            tools.add(r.tool)
            if r.decision == "block":
                blocked_tools[r.tool] += 1
            if r.chain_pattern:
                chains[r.chain_pattern] += 1
            for dt in r.deviation_types:
                devs[dt] += 1

        block_rate = decisions.get("block", 0) / total * 100
        avg_risk = sum(scores) / total
        risk_dist = _compute_risk_distribution(scores)

        timestamps = [r.timestamp for r in records]
        active_hours = (max(timestamps) - min(timestamps)) / 3600 if len(timestamps) > 1 else 0

        risk_level = _classify_risk_level(
            block_rate, avg_risk, sum(chains.values()), sum(devs.values()), total,
        )

        top_blocked = sorted(blocked_tools.items(), key=lambda x: -x[1])[:5]

        recs = _generate_recommendations(
            block_rate, avg_risk, dict(chains), dict(devs), top_blocked, total,
        )

        return AgentRiskProfile(
            agent_id=agent_id,
            total_evaluations=total,
            risk_level=risk_level,
            risk_distribution=risk_dist.to_dict(),
            decision_breakdown=dict(decisions),
            block_rate_pct=block_rate,
            top_blocked_tools=top_blocked,
            chain_patterns_detected=dict(chains),
            deviation_types=dict(devs),
            unique_tools=len(tools),
            active_hours=active_hours,
            recommendations=recs,
        )

    # ─── TOOL ASSESSMENT ───

    def assess_tool(self, tool: str,
                    period: AssessmentPeriod = AssessmentPeriod.LAST_30D) -> ToolRiskProfile:
        """Generate risk profile for a specific tool."""
        records = [r for r in self._filter_by_period(period) if r.tool == tool]
        total = len(records)

        if total == 0:
            return ToolRiskProfile(
                tool=tool, total_evaluations=0, risk_level="minimal",
                risk_distribution=RiskDistribution().to_dict(),
                decision_breakdown={}, block_rate_pct=0.0,
                agents_using=0, chain_patterns_involving={},
                common_block_reasons=[], recommendations=["No data for this tool."],
            )

        scores = [r.risk_score for r in records]
        decisions: Dict[str, int] = defaultdict(int)
        agents = set()
        chains: Dict[str, int] = defaultdict(int)
        block_reasons: Dict[str, int] = defaultdict(int)

        for r in records:
            decisions[r.decision] += 1
            agents.add(r.agent_id)
            if r.chain_pattern:
                chains[r.chain_pattern] += 1
            if r.decision == "block" and r.explanation:
                # Extract first meaningful phrase as reason
                reason = r.explanation[:80].split(".")[0].strip()
                if reason:
                    block_reasons[reason] += 1

        block_rate = decisions.get("block", 0) / total * 100
        avg_risk = sum(scores) / total
        risk_dist = _compute_risk_distribution(scores)

        risk_level = _classify_risk_level(block_rate, avg_risk, sum(chains.values()), 0, total)

        top_reasons = sorted(block_reasons.items(), key=lambda x: -x[1])[:5]

        recs = []
        if block_rate > 20:
            recs.append(
                f"Tool '{tool}' has a {block_rate:.0f}% block rate. "
                f"Consider whether this tool should remain in agent scope."
            )
        if len(agents) == 1:
            recs.append(f"Only one agent uses this tool. Low blast radius if compromised.")
        elif len(agents) > 5:
            recs.append(
                f"{len(agents)} agents use this tool. High blast radius — "
                f"ensure policies are tight."
            )
        if not recs:
            recs.append("No specific concerns for this tool.")

        return ToolRiskProfile(
            tool=tool,
            total_evaluations=total,
            risk_level=risk_level,
            risk_distribution=risk_dist.to_dict(),
            decision_breakdown=dict(decisions),
            block_rate_pct=block_rate,
            agents_using=len(agents),
            chain_patterns_involving=dict(chains),
            common_block_reasons=top_reasons,
            recommendations=recs,
        )

    # ─── QUERY ───

    @property
    def total_records(self) -> int:
        return len(self._records)

    def list_agents(self, period: AssessmentPeriod = AssessmentPeriod.ALL_TIME) -> List[str]:
        records = self._filter_by_period(period)
        return sorted(set(r.agent_id for r in records))

    def list_tools(self, period: AssessmentPeriod = AssessmentPeriod.ALL_TIME) -> List[str]:
        records = self._filter_by_period(period)
        return sorted(set(r.tool for r in records))
