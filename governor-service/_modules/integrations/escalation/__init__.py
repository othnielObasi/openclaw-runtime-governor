"""
NOVTIA Governor — Escalation Connectors
=========================================
Routes review/block decisions to external workflow systems
so the right human actually sees them.

Supported targets:
  - Slack (via webhook URL)
  - Microsoft Teams (via webhook URL)
  - Jira (create issue via REST API)
  - ServiceNow (create incident via REST API)
  - PagerDuty (trigger incident via Events API v2)
  - Generic webhook (any HTTP endpoint)

Integration:
    from escalation import EscalationRouter, EscalationTarget, EscalationEvent

    router = EscalationRouter()
    router.add_target(EscalationTarget(
        name="security_slack",
        target_type="slack",
        url="https://hooks.slack.com/services/T.../B.../xxx",
        trigger_on={"block", "review"},
        min_risk_score=50,
    ))

    # After evaluation:
    router.escalate(event)
"""
from __future__ import annotations

import json
import time
import threading
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger("novtia.escalation")


# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

@dataclass
class EscalationTarget:
    """Configuration for an escalation target."""
    name: str
    target_type: str                         # slack | teams | jira | servicenow | pagerduty | generic
    url: str = ""                            # Webhook or API endpoint
    auth_token: str = ""                     # API token / key
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer"

    # Trigger rules
    trigger_on: Set[str] = field(default_factory=lambda: {"block", "review"})
    min_risk_score: int = 0                  # Only escalate if risk >= this
    trigger_on_chain_pattern: bool = True    # Escalate if chain pattern detected
    trigger_on_deviations: bool = True       # Escalate if fingerprint deviations found
    trigger_on_kill_switch: bool = True

    # Jira-specific
    jira_project_key: str = ""
    jira_issue_type: str = "Task"
    jira_priority: str = "High"
    jira_assignee: str = ""

    # ServiceNow-specific
    servicenow_instance: str = ""            # e.g., "company.service-now.com"
    servicenow_category: str = "AI Security"
    servicenow_urgency: str = "2"            # 1=High, 2=Medium, 3=Low
    servicenow_impact: str = "2"

    # PagerDuty-specific
    pagerduty_routing_key: str = ""
    pagerduty_severity: str = "warning"      # critical | error | warning | info

    enabled: bool = True
    max_retries: int = 2
    retry_delay_seconds: float = 1.0

    extra_headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class EscalationEvent:
    """An event to be escalated to external systems."""
    event_id: str
    timestamp: str
    tool: str
    decision: str
    risk_score: int
    explanation: str
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    policy_ids: List[str] = field(default_factory=list)
    chain_pattern: Optional[str] = None
    chain_description: Optional[str] = None
    deviations: List[Dict[str, Any]] = field(default_factory=list)
    surge_receipt_id: Optional[str] = None
    deployment_id: str = ""
    severity: str = "medium"
    is_kill_switch: bool = False
    dashboard_url: str = ""                  # Deep link back to Governor dashboard

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "tool": self.tool,
            "decision": self.decision,
            "risk_score": self.risk_score,
            "explanation": self.explanation,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "policy_ids": self.policy_ids,
            "chain_pattern": self.chain_pattern,
            "chain_description": self.chain_description,
            "deviations": self.deviations,
            "surge_receipt_id": self.surge_receipt_id,
            "deployment_id": self.deployment_id,
            "severity": self.severity,
            "is_kill_switch": self.is_kill_switch,
            "dashboard_url": self.dashboard_url,
        }


# ═══════════════════════════════════════════════════════════
# MESSAGE FORMATTERS
# ═══════════════════════════════════════════════════════════

SEVERITY_EMOJI = {
    "low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴",
}
DECISION_EMOJI = {
    "block": "🚫", "review": "👁️", "allow": "✅",
}


def _format_slack(event: EscalationEvent, target: EscalationTarget) -> Dict[str, Any]:
    """Format as Slack Block Kit message."""
    sev_emoji = SEVERITY_EMOJI.get(event.severity, "⚪")
    dec_emoji = DECISION_EMOJI.get(event.decision, "❓")

    header = f"{dec_emoji} *Agent Action {event.decision.upper()}* {sev_emoji}"
    if event.is_kill_switch:
        header = "🛑 *KILL SWITCH ENGAGED*"

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Governor Alert: {event.decision.upper()}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": header}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Tool:*\n`{event.tool}`"},
            {"type": "mrkdwn", "text": f"*Risk Score:*\n{event.risk_score}/100"},
            {"type": "mrkdwn", "text": f"*Agent:*\n`{event.agent_id or 'unknown'}`"},
            {"type": "mrkdwn", "text": f"*Severity:*\n{event.severity.upper()}"},
        ]},
        {"type": "section", "text": {
            "type": "mrkdwn",
            "text": f"*Explanation:*\n{event.explanation[:500]}",
        }},
    ]

    if event.chain_pattern:
        blocks.append({"type": "section", "text": {
            "type": "mrkdwn",
            "text": f"⚠️ *Chain Pattern:* `{event.chain_pattern}`\n{event.chain_description or ''}",
        }})

    if event.deviations:
        dev_text = "\n".join(
            f"• `{d.get('deviation_type', '?')}` — severity +{d.get('severity', 0):.0f}, "
            f"confidence {d.get('confidence', 0)*100:.0f}%"
            for d in event.deviations[:5]
        )
        blocks.append({"type": "section", "text": {
            "type": "mrkdwn",
            "text": f"🧬 *Fingerprint Deviations:*\n{dev_text}",
        }})

    if event.surge_receipt_id:
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"SURGE Receipt: `{event.surge_receipt_id}`"},
        ]})

    if event.dashboard_url:
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "View in Governor"},
             "url": event.dashboard_url, "style": "primary"},
        ]})

    return {"blocks": blocks}


def _format_teams(event: EscalationEvent, target: EscalationTarget) -> Dict[str, Any]:
    """Format as Microsoft Teams Adaptive Card."""
    color = {"block": "FF0000", "review": "FFA500", "allow": "00FF00"}.get(event.decision, "808080")

    facts = [
        {"name": "Tool", "value": f"`{event.tool}`"},
        {"name": "Decision", "value": event.decision.upper()},
        {"name": "Risk Score", "value": f"{event.risk_score}/100"},
        {"name": "Agent", "value": event.agent_id or "unknown"},
        {"name": "Severity", "value": event.severity.upper()},
    ]

    if event.chain_pattern:
        facts.append({"name": "Chain Pattern", "value": event.chain_pattern})

    if event.surge_receipt_id:
        facts.append({"name": "SURGE Receipt", "value": event.surge_receipt_id})

    sections = [{"facts": facts, "text": event.explanation[:500]}]

    if event.deviations:
        dev_text = "\n\n".join(
            f"**{d.get('deviation_type', '?')}** — severity +{d.get('severity', 0):.0f}"
            for d in event.deviations[:5]
        )
        sections.append({"text": f"**Fingerprint Deviations:**\n\n{dev_text}"})

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": f"Governor: {event.decision.upper()} - {event.tool}",
        "title": f"🛡️ Governor Alert: {event.decision.upper()}",
        "sections": sections,
    }

    if event.dashboard_url:
        card["potentialAction"] = [{
            "@type": "OpenUri",
            "name": "View in Governor",
            "targets": [{"os": "default", "uri": event.dashboard_url}],
        }]

    return card


def _format_jira(event: EscalationEvent, target: EscalationTarget) -> Dict[str, Any]:
    """Format as Jira issue creation payload."""
    description_parts = [
        f"*Decision:* {event.decision.upper()}",
        f"*Risk Score:* {event.risk_score}/100",
        f"*Tool:* {event.tool}",
        f"*Agent:* {event.agent_id or 'unknown'}",
        f"*Session:* {event.session_id or 'unknown'}",
        f"*Severity:* {event.severity}",
        "",
        f"*Explanation:*",
        event.explanation,
    ]

    if event.chain_pattern:
        description_parts.extend(["", f"*Chain Pattern:* {event.chain_pattern}", event.chain_description or ""])

    if event.deviations:
        description_parts.append("\n*Fingerprint Deviations:*")
        for d in event.deviations[:5]:
            description_parts.append(
                f"- {d.get('deviation_type')}: severity +{d.get('severity', 0):.0f}, "
                f"confidence {d.get('confidence', 0)*100:.0f}%"
            )

    if event.surge_receipt_id:
        description_parts.extend(["", f"*SURGE Receipt:* {event.surge_receipt_id}"])

    if event.dashboard_url:
        description_parts.extend(["", f"*Dashboard:* {event.dashboard_url}"])

    payload = {
        "fields": {
            "project": {"key": target.jira_project_key},
            "summary": f"[Governor] {event.decision.upper()}: {event.tool} — risk {event.risk_score}",
            "description": "\n".join(description_parts),
            "issuetype": {"name": target.jira_issue_type},
            "priority": {"name": target.jira_priority},
            "labels": ["novtia-governor", f"severity-{event.severity}", event.decision],
        }
    }

    if target.jira_assignee:
        payload["fields"]["assignee"] = {"name": target.jira_assignee}

    return payload


def _format_servicenow(event: EscalationEvent, target: EscalationTarget) -> Dict[str, Any]:
    """Format as ServiceNow incident creation payload."""
    return {
        "short_description": f"[AI Governor] {event.decision.upper()}: {event.tool} — risk {event.risk_score}",
        "description": (
            f"NOVTIA Governor Escalation\n\n"
            f"Decision: {event.decision.upper()}\n"
            f"Tool: {event.tool}\n"
            f"Risk Score: {event.risk_score}/100\n"
            f"Agent: {event.agent_id or 'unknown'}\n"
            f"Severity: {event.severity}\n\n"
            f"Explanation:\n{event.explanation}\n\n"
            f"{'Chain Pattern: ' + event.chain_pattern + chr(10) if event.chain_pattern else ''}"
            f"{'SURGE Receipt: ' + event.surge_receipt_id + chr(10) if event.surge_receipt_id else ''}"
            f"{'Dashboard: ' + event.dashboard_url if event.dashboard_url else ''}"
        ),
        "category": target.servicenow_category,
        "urgency": target.servicenow_urgency,
        "impact": target.servicenow_impact,
        "caller_id": "novtia_governor",
    }


def _format_pagerduty(event: EscalationEvent, target: EscalationTarget) -> Dict[str, Any]:
    """Format as PagerDuty Events API v2 trigger."""
    severity_map = {"low": "info", "medium": "warning", "high": "error", "critical": "critical"}
    pd_severity = severity_map.get(event.severity, target.pagerduty_severity)

    payload = {
        "routing_key": target.pagerduty_routing_key,
        "event_action": "trigger",
        "dedup_key": f"novtia-{event.agent_id}-{event.tool}-{event.event_id[:8]}",
        "payload": {
            "summary": f"AI Agent {event.decision.upper()}: {event.tool} (risk {event.risk_score})",
            "source": event.deployment_id or "novtia-governor",
            "severity": pd_severity,
            "component": event.tool,
            "group": event.agent_id or "unknown",
            "class": event.chain_pattern or event.decision,
            "custom_details": event.to_dict(),
        },
    }

    if event.dashboard_url:
        payload["links"] = [{"href": event.dashboard_url, "text": "View in Governor Dashboard"}]

    return payload


def _format_generic(event: EscalationEvent, target: EscalationTarget) -> Dict[str, Any]:
    """Generic JSON payload."""
    return event.to_dict()


FORMATTERS = {
    "slack": _format_slack,
    "teams": _format_teams,
    "jira": _format_jira,
    "servicenow": _format_servicenow,
    "pagerduty": _format_pagerduty,
    "generic": _format_generic,
}


# ═══════════════════════════════════════════════════════════
# HTTP TRANSPORT
# ═══════════════════════════════════════════════════════════

@dataclass
class HttpResponse:
    status: int
    body: str = ""
    error: bool = False

    @property
    def success(self) -> bool:
        return 200 <= self.status < 300


class HttpTransport:
    """Pluggable HTTP transport using stdlib."""

    def post(self, url: str, headers: Dict[str, str],
             body: str, timeout: float = 10.0) -> HttpResponse:
        import urllib.request
        import urllib.error

        req = urllib.request.Request(
            url, data=body.encode("utf-8"),
            headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return HttpResponse(status=resp.status, body=resp.read().decode())
        except urllib.error.HTTPError as e:
            return HttpResponse(status=e.code, body=str(e.reason))
        except Exception as e:
            return HttpResponse(status=0, body=str(e), error=True)


class MockTransport:
    """For testing — records all sent messages."""

    def __init__(self):
        self.sent: List[Dict[str, Any]] = []
        self.fail_next: int = 0

    def post(self, url: str, headers: Dict[str, str],
             body: str, timeout: float = 10.0) -> HttpResponse:
        if self.fail_next > 0:
            self.fail_next -= 1
            return HttpResponse(status=500, body="Mock failure", error=True)

        self.sent.append({
            "url": url, "headers": headers,
            "body": json.loads(body) if body.startswith(("{", "[")) else body,
            "timestamp": time.time(),
        })
        return HttpResponse(status=200, body="OK")


# ═══════════════════════════════════════════════════════════
# ESCALATION ROUTER
# ═══════════════════════════════════════════════════════════

@dataclass
class EscalationResult:
    target_name: str
    success: bool
    error: str = ""
    retries_used: int = 0


@dataclass
class EscalationStats:
    total_events: int = 0
    total_escalated: int = 0
    total_filtered: int = 0
    total_failed: int = 0
    total_retries: int = 0
    per_target: Dict[str, int] = field(default_factory=lambda: {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_events": self.total_events,
            "total_escalated": self.total_escalated,
            "total_filtered": self.total_filtered,
            "total_failed": self.total_failed,
            "total_retries": self.total_retries,
            "per_target": self.per_target,
        }


class EscalationRouter:
    """
    Routes governance events to external workflow systems.

    The router evaluates each event against target trigger rules
    and delivers to matching targets. Unlike the SIEM dispatcher,
    escalation is immediate (no batching) because a human needs
    to see and act on these events promptly.

    Usage:
        router = EscalationRouter()
        router.add_target(EscalationTarget(
            name="sec_team_slack",
            target_type="slack",
            url="https://hooks.slack.com/services/...",
            trigger_on={"block", "review"},
            min_risk_score=50,
        ))
        results = router.escalate(event)
    """

    def __init__(self, transport: Optional[HttpTransport] = None):
        self._targets: Dict[str, EscalationTarget] = {}
        self._transport = transport or HttpTransport()
        self._stats = EscalationStats()
        self._lock = threading.Lock()

    def add_target(self, target: EscalationTarget):
        with self._lock:
            self._targets[target.name] = target
            self._stats.per_target[target.name] = 0

    def remove_target(self, name: str):
        with self._lock:
            self._targets.pop(name, None)
            self._stats.per_target.pop(name, None)

    def escalate(self, event: EscalationEvent) -> List[EscalationResult]:
        """
        Evaluate event against all targets and deliver to matching ones.
        Returns results for each target that was attempted.
        """
        self._stats.total_events += 1
        results = []

        with self._lock:
            targets = list(self._targets.values())

        for target in targets:
            if not target.enabled:
                continue

            if not self._should_trigger(event, target):
                self._stats.total_filtered += 1
                continue

            result = self._deliver(event, target)
            results.append(result)

            if result.success:
                self._stats.total_escalated += 1
                self._stats.per_target[target.name] = self._stats.per_target.get(target.name, 0) + 1
            else:
                self._stats.total_failed += 1

        return results

    def _should_trigger(self, event: EscalationEvent, target: EscalationTarget) -> bool:
        """Check if event matches target's trigger rules."""
        # Kill switch overrides everything
        if event.is_kill_switch and target.trigger_on_kill_switch:
            return True

        # Decision filter
        if event.decision not in target.trigger_on:
            return False

        # Risk score threshold
        if event.risk_score < target.min_risk_score:
            # But still trigger if chain pattern or deviations, if configured
            if event.chain_pattern and target.trigger_on_chain_pattern:
                return True
            if event.deviations and target.trigger_on_deviations:
                return True
            return False

        return True

    def _deliver(self, event: EscalationEvent, target: EscalationTarget) -> EscalationResult:
        """Deliver escalation to a single target with retry."""
        formatter = FORMATTERS.get(target.target_type, _format_generic)
        payload = formatter(event, target)
        body = json.dumps(payload)

        headers = {"Content-Type": "application/json", **target.extra_headers}

        if target.auth_token:
            if target.target_type == "jira":
                # Jira uses Basic auth with email:api_token
                headers[target.auth_header] = f"Basic {target.auth_token}"
            elif target.target_type == "servicenow":
                headers[target.auth_header] = f"Basic {target.auth_token}"
            elif target.target_type in ("slack", "teams"):
                pass  # Webhook URL contains auth
            else:
                headers[target.auth_header] = f"{target.auth_prefix} {target.auth_token}"

        # Determine URL
        url = target.url
        if target.target_type == "pagerduty":
            url = url or "https://events.pagerduty.com/v2/enqueue"
        elif target.target_type == "servicenow" and target.servicenow_instance:
            url = url or f"https://{target.servicenow_instance}/api/now/table/incident"

        retries = 0
        last_error = ""

        for attempt in range(target.max_retries + 1):
            resp = self._transport.post(url, headers, body)

            if resp.success:
                return EscalationResult(
                    target_name=target.name, success=True,
                    retries_used=retries,
                )

            last_error = f"HTTP {resp.status}: {resp.body[:200]}"
            retries += 1
            self._stats.total_retries += 1

            if attempt < target.max_retries:
                time.sleep(target.retry_delay_seconds * (attempt + 1))

        return EscalationResult(
            target_name=target.name, success=False,
            error=last_error, retries_used=retries,
        )

    # ─── Query ───

    @property
    def stats(self) -> EscalationStats:
        return self._stats

    def list_targets(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t.name,
                "type": t.target_type,
                "enabled": t.enabled,
                "trigger_on": list(t.trigger_on),
                "min_risk_score": t.min_risk_score,
                "escalations_sent": self._stats.per_target.get(t.name, 0),
            }
            for t in self._targets.values()
        ]
