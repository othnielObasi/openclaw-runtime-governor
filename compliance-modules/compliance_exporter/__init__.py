"""
NOVTIA Governor — Compliance Evidence Exporter
================================================
Exports audit trails with OWASP LLM 2025 and NIST AI RMF risk tags.
Generates compliance reports in JSON/CSV format.

Integration:
    from compliance_exporter import ComplianceExporter, ComplianceFramework
    exporter = ComplianceExporter()
    report = exporter.generate_report(actions, framework=ComplianceFramework.OWASP_LLM_2025)
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse


class ComplianceFramework(str, Enum):
    OWASP_LLM_2025 = "owasp_llm_2025"
    NIST_AI_RMF = "nist_ai_rmf"
    NIST_AI_600_1 = "nist_ai_600_1"
    EU_AI_ACT = "eu_ai_act"
    ALL = "all"


# ═══ RISK CATEGORY MAPPINGS ═══

OWASP_LLM_2025_TAGS = {
    "LLM01": {"name": "Prompt Injection", "indicators": ["injection", "jailbreak", "role_play", "delimiter_escape"]},
    "LLM02": {"name": "Sensitive Information Disclosure", "indicators": ["pii", "credential_leak", "api_key", "private_key"]},
    "LLM05": {"name": "Improper Output Handling", "indicators": ["verification_fail", "output_injection", "format_violation"]},
    "LLM06": {"name": "Excessive Agency", "indicators": ["scope_violation", "privilege_escalation", "kill_switch", "blocked"]},
    "LLM10": {"name": "Unbounded Consumption", "indicators": ["budget_exceeded", "rate_limited", "velocity_check"]},
}

NIST_AI_RMF_TAGS = {
    "GOVERN-1": {"name": "Policies & Procedures", "indicators": ["policy_created", "policy_updated", "policy_toggled"]},
    "GOVERN-2": {"name": "Roles & Responsibilities", "indicators": ["rbac", "auth", "permission"]},
    "MAP-1": {"name": "Risk Identification", "indicators": ["risk_score", "chain_analysis", "injection"]},
    "MEASURE-1": {"name": "Quantitative Metrics", "indicators": ["risk_score", "evaluation", "latency"]},
    "MEASURE-2": {"name": "Monitoring", "indicators": ["stream", "dashboard", "alert"]},
    "MANAGE-1": {"name": "Risk Treatment", "indicators": ["block", "allow", "review", "kill_switch"]},
    "MANAGE-2": {"name": "Incident Response", "indicators": ["kill_switch", "escalation", "notification"]},
}

NIST_600_1_TAGS = {
    "GAI-3": {"name": "Data Privacy", "indicators": ["pii", "encryption", "credential_leak"]},
    "GAI-6": {"name": "Human-AI Configuration", "indicators": ["kill_switch", "escalation", "review"]},
    "GAI-7": {"name": "Information Integrity", "indicators": ["surge_receipt", "audit", "hash"]},
    "GAI-8": {"name": "Information Security", "indicators": ["auth", "rbac", "injection", "blocked"]},
    "GAI-12": {"name": "Harmful Use / Dual Use", "indicators": ["chain_analysis", "privilege_escalation", "exfiltration"]},
}


def _tag_action(action: Dict[str, Any], framework: ComplianceFramework) -> List[Dict[str, str]]:
    """Tag an action with compliance framework risk categories."""
    tags = []
    decision = action.get("decision", "")
    explanation = (action.get("explanation", "") or "").lower()
    policy_ids = action.get("policy_ids", [])
    risk_score = action.get("risk_score", 0)

    # Build indicator set from action data
    indicators = set()
    if decision == "block":
        indicators.add("blocked")
    if decision == "review":
        indicators.add("review")
    indicators.add(decision)

    if risk_score > 0:
        indicators.add("risk_score")
        indicators.add("evaluation")

    # Check explanation for keywords
    keyword_map = {
        "injection": "injection", "jailbreak": "jailbreak", "pii": "pii",
        "credential": "credential_leak", "scope": "scope_violation",
        "privilege": "privilege_escalation", "kill": "kill_switch",
        "budget": "budget_exceeded", "rate": "rate_limited",
        "chain": "chain_analysis", "verification": "verification_fail",
        "policy": "policy_created", "escalat": "escalation",
        "surge": "surge_receipt", "auth": "auth", "rbac": "rbac",
        "exfil": "exfiltration", "encrypt": "encryption",
    }
    for keyword, indicator in keyword_map.items():
        if keyword in explanation:
            indicators.add(indicator)

    # Match indicators to framework tags
    tag_maps = {}
    if framework in (ComplianceFramework.OWASP_LLM_2025, ComplianceFramework.ALL):
        tag_maps.update({"owasp:" + k: v for k, v in OWASP_LLM_2025_TAGS.items()})
    if framework in (ComplianceFramework.NIST_AI_RMF, ComplianceFramework.ALL):
        tag_maps.update({"nist_rmf:" + k: v for k, v in NIST_AI_RMF_TAGS.items()})
    if framework in (ComplianceFramework.NIST_AI_600_1, ComplianceFramework.ALL):
        tag_maps.update({"nist_600:" + k: v for k, v in NIST_600_1_TAGS.items()})

    for tag_id, tag_def in tag_maps.items():
        if indicators & set(tag_def["indicators"]):
            tags.append({"id": tag_id, "name": tag_def["name"]})

    return tags


@dataclass
class ComplianceReport:
    """Generated compliance report."""
    framework: str
    generated_at: str
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    total_actions: int = 0
    total_blocks: int = 0
    total_reviews: int = 0
    total_allows: int = 0
    risk_categories_hit: Dict[str, int] = field(default_factory=dict)
    tagged_actions: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "framework": self.framework,
            "generated_at": self.generated_at,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_actions": self.total_actions,
            "total_blocks": self.total_blocks,
            "total_reviews": self.total_reviews,
            "total_allows": self.total_allows,
            "risk_categories_hit": self.risk_categories_hit,
            "summary": self.summary,
            "actions": self.tagged_actions,
        }


class ComplianceExporter:
    """
    Generates compliance reports from governance audit trails.

    Usage:
        exporter = ComplianceExporter()
        actions = [...]  # List of action dicts from /actions endpoint
        report = exporter.generate_report(actions, ComplianceFramework.OWASP_LLM_2025)
    """

    def generate_report(
        self,
        actions: List[Dict[str, Any]],
        framework: ComplianceFramework = ComplianceFramework.ALL,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> ComplianceReport:
        """Generate a compliance report from action logs."""
        now = datetime.now(timezone.utc).isoformat()

        report = ComplianceReport(
            framework=framework.value,
            generated_at=now,
            period_start=period_start,
            period_end=period_end,
            total_actions=len(actions),
        )

        category_counts: Dict[str, int] = {}

        for action in actions:
            decision = action.get("decision", "allow")
            if decision == "block":
                report.total_blocks += 1
            elif decision == "review":
                report.total_reviews += 1
            else:
                report.total_allows += 1

            tags = _tag_action(action, framework)

            tagged = {
                "id": action.get("id", action.get("action_id")),
                "timestamp": action.get("created_at", action.get("timestamp")),
                "tool": action.get("tool"),
                "decision": decision,
                "risk_score": action.get("risk_score", 0),
                "compliance_tags": tags,
            }
            report.tagged_actions.append(tagged)

            for tag in tags:
                tid = tag["id"]
                category_counts[tid] = category_counts.get(tid, 0) + 1

        report.risk_categories_hit = dict(sorted(category_counts.items(), key=lambda x: -x[1]))

        # Summary statistics
        risk_scores = [a.get("risk_score", 0) for a in actions if a.get("risk_score")]
        report.summary = {
            "block_rate": round(report.total_blocks / max(len(actions), 1) * 100, 2),
            "review_rate": round(report.total_reviews / max(len(actions), 1) * 100, 2),
            "avg_risk_score": round(sum(risk_scores) / max(len(risk_scores), 1), 2),
            "max_risk_score": max(risk_scores) if risk_scores else 0,
            "unique_tools": len(set(a.get("tool", "") for a in actions)),
            "categories_triggered": len(category_counts),
        }

        return report

    def to_csv(self, report: ComplianceReport) -> str:
        """Export tagged actions as CSV."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "timestamp", "tool", "decision", "risk_score", "compliance_tags"])

        for action in report.tagged_actions:
            tags_str = "; ".join(f"{t['id']}: {t['name']}" for t in action["compliance_tags"])
            writer.writerow([
                action.get("id", ""),
                action.get("timestamp", ""),
                action.get("tool", ""),
                action.get("decision", ""),
                action.get("risk_score", 0),
                tags_str,
            ])

        return output.getvalue()


# ─── FastAPI Router ───

compliance_router = APIRouter(tags=["Compliance"])
_exporter = ComplianceExporter()


@compliance_router.post("/compliance/report")
async def generate_compliance_report(
    actions: List[Dict[str, Any]],
    framework: ComplianceFramework = Query(ComplianceFramework.ALL),
    period_start: Optional[str] = Query(None),
    period_end: Optional[str] = Query(None),
):
    """Generate compliance report from action logs."""
    report = _exporter.generate_report(actions, framework, period_start, period_end)
    return report.to_dict()


@compliance_router.post("/compliance/export/csv")
async def export_compliance_csv(
    actions: List[Dict[str, Any]],
    framework: ComplianceFramework = Query(ComplianceFramework.ALL),
):
    """Export compliance-tagged actions as CSV."""
    report = _exporter.generate_report(actions, framework)
    csv_content = _exporter.to_csv(report)
    return StreamingResponse(
        io.BytesIO(csv_content.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=compliance_report.csv"},
    )
