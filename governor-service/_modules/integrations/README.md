# NOVTIA Governor — Enterprise Integrations

> SIEM webhook for your SOC team. Escalation connectors for your incident responders. The two integrations that unblock enterprise sales.

**42 tests passing** · Zero external dependencies · Python 3.9+ · Thread-safe

---

## Why These Two

Every enterprise security team asks two questions in the first demo:

1. "Does this integrate with our SIEM?"
2. "Where do review decisions go?"

If the answer to either is no, the conversation stalls regardless of how good the governance engine is. These two modules ensure the answer is yes.

---

## Module 1: SIEM Webhook

Pushes governance events to external security systems in real-time with batching, retry, filtering, and dead-letter queue.

### Supported Targets

| Target | Format | Auth | Notes |
|--------|--------|------|-------|
| **Splunk HEC** | Splunk JSON with `time`, `source`, `sourcetype`, `index` | `Splunk {token}` header | Newline-delimited JSON for batch events |
| **Elastic** | Elastic Common Schema (ECS) with `event.kind`, `event.category`, `event.outcome` | Bearer token | Renders in Kibana without custom parsing |
| **Microsoft Sentinel** | Log Analytics format with `TimeGenerated`, `Severity` | Bearer token | Direct to Log Analytics workspace |
| **Syslog** | CEF (Common Event Format) over TCP/UDP | N/A | RFC 5424 compliant, works with any legacy SIEM |
| **Generic Webhook** | Raw JSON | Configurable header + prefix | Any HTTP endpoint accepting JSON POST |

### Quick Start

```python
from siem_webhook import SiemDispatcher, SiemTarget, event_from_evaluation

# 1. Create dispatcher
dispatcher = SiemDispatcher()

# 2. Add targets
dispatcher.add_target(SiemTarget(
    name="splunk_prod",
    target_type="splunk_hec",
    url="https://splunk.corp.com:8088/services/collector",
    auth_token="your-hec-token",
    splunk_index="ai_governance",
    splunk_sourcetype="novtia:governance",
    batch_size=10,              # Flush every 10 events
    flush_interval_seconds=5.0, # Or every 5 seconds
    min_severity="medium",      # Only medium+ severity
))

dispatcher.add_target(SiemTarget(
    name="elastic_prod",
    target_type="elastic",
    url="https://elastic.corp.com:9200/novtia-governance/_doc",
    auth_token="your-api-key",
    decision_filter={"block", "review"},  # Only blocks and reviews
))

# 3. After every evaluation, dispatch
event = event_from_evaluation(
    tool="shell",
    decision="block",
    risk_score=85,
    explanation="Injection detected",
    policy_ids=["pol_sec_1"],
    agent_id="agent_001",
    session_id="sess_abc",
    chain_pattern="credential_then_exfil",
    surge_receipt_id="surge-abc123",
    surge_digest="deadbeef...",
    deviations=[{"deviation_type": "novel_tool", "severity": 25.0}],
    deployment_id="novtia-uk-001",
    jurisdiction="GB",
)
results = dispatcher.dispatch(event)

# 4. On shutdown
dispatcher.flush()
```

### Features

**Batching** — Events queue per target and flush when batch size is reached or flush interval expires. Configurable per target. Default: 10 events or 5 seconds.

**Severity filtering** — Set `min_severity` per target. Options: `low`, `medium`, `high`, `critical`. A Splunk target set to `high` only receives blocks with risk ≥80, chain patterns, or multi-deviation events.

**Decision filtering** — Set `decision_filter` per target. Example: `{"block", "review"}` skips all `allow` events. Reduces noise in high-volume deployments.

**Retry with backoff** — Failed deliveries retry up to `max_retries` times (default 3) with increasing delay. After exhaustion, events go to the dead-letter queue.

**Dead-letter queue** — Failed events are stored with target name, error message, timestamp, and retry count. Query via `dispatcher.get_dead_letter()`. Clear via `dispatcher.clear_dead_letter()`.

**Stats** — `dispatcher.stats` returns total dispatched, delivered, failed, filtered, retries, dead letter count, and active target count.

### Event Severity Computation

Severity is computed automatically from the governance decision:

| Condition | Severity |
|-----------|----------|
| Block + risk ≥ 80 | `critical` |
| Block, or chain pattern detected, or 2+ fingerprint deviations | `high` |
| Review, or risk ≥ 50, or any fingerprint deviation | `medium` |
| Everything else | `low` |

### Splunk HEC Event Format

```json
{
  "time": 1709294400.0,
  "host": "novtia-uk-001",
  "source": "novtia_governor",
  "sourcetype": "novtia:governance",
  "index": "ai_governance",
  "event": {
    "event_id": "evt-abc123",
    "tool": "shell",
    "decision": "block",
    "risk_score": 85,
    "explanation": "Injection detected",
    "agent_id": "agent_001",
    "chain_pattern": "credential_then_exfil",
    "surge_receipt_id": "surge-abc123",
    "deviations": [{"deviation_type": "novel_tool", "severity": 25.0}],
    "severity": "critical"
  }
}
```

### Elastic Common Schema Mapping

```json
{
  "@timestamp": "2026-03-01T12:00:00+00:00",
  "event": {
    "kind": "alert",
    "category": ["intrusion_detection"],
    "type": ["denied"],
    "severity": 75,
    "module": "novtia_governor",
    "id": "evt-abc123",
    "outcome": "failure"
  },
  "rule": { "id": "pol_sec_1", "description": "Injection detected" },
  "agent": { "id": "agent_001", "type": "ai_agent" },
  "novtia": { ... }
}
```

### CEF Syslog Format

```
CEF:0|NOVTIA|Governor|1.0|evaluation|BLOCK shell|10|act=block risk=85 msg=Injection detected cs1=shell cs1Label=Tool cs2=agent_001 cs2Label=AgentID cs3=surge-abc123 cs3Label=SurgeReceiptID cs4=credential_then_exfil cs4Label=ChainPattern
```

---

## Module 2: Escalation Connectors

Routes review/block decisions to external workflow systems so the right human sees them immediately.

### Supported Targets

| Target | Format | Use Case |
|--------|--------|----------|
| **Slack** | Block Kit with rich formatting, severity emoji, action buttons | Security team channel |
| **Microsoft Teams** | Adaptive Card with facts, sections, action buttons | SOC team channel |
| **Jira** | Issue creation with project, type, priority, labels, assignee | Incident tracking |
| **ServiceNow** | Incident creation with category, urgency, impact | ITSM workflow |
| **PagerDuty** | Events API v2 trigger with dedup keys, severity, routing | On-call escalation |
| **Generic Webhook** | Raw JSON | Any HTTP endpoint |

### Quick Start

```python
from escalation import EscalationRouter, EscalationTarget, EscalationEvent

# 1. Create router
router = EscalationRouter()

# 2. Add targets with trigger rules
router.add_target(EscalationTarget(
    name="security_slack",
    target_type="slack",
    url="https://hooks.slack.com/services/T.../B.../xxx",
    trigger_on={"block", "review"},
    min_risk_score=50,
    trigger_on_chain_pattern=True,     # Escalate chain patterns even below threshold
    trigger_on_deviations=True,        # Escalate fingerprint deviations even below threshold
    trigger_on_kill_switch=True,       # Always escalate kill switch
))

router.add_target(EscalationTarget(
    name="incident_jira",
    target_type="jira",
    url="https://company.atlassian.net/rest/api/2/issue",
    auth_token="base64_encoded_email:api_token",
    jira_project_key="SEC",
    jira_issue_type="Bug",
    jira_priority="High",
    trigger_on={"block"},             # Only blocks create Jira tickets
    min_risk_score=70,
))

router.add_target(EscalationTarget(
    name="oncall_pagerduty",
    target_type="pagerduty",
    pagerduty_routing_key="your-routing-key",
    trigger_on={"block"},
    min_risk_score=90,                # Only critical blocks page on-call
))

# 3. After evaluation
event = EscalationEvent(
    event_id="esc-001",
    timestamp="2026-03-01T12:00:00+00:00",
    tool="http_post",
    decision="block",
    risk_score=92,
    explanation="Credential exfiltration attempt",
    agent_id="agent_ops_001",
    chain_pattern="credential_then_exfil",
    chain_description="Agent read AWS keys then attempted external POST",
    deviations=[
        {"deviation_type": "novel_tool", "severity": 25.0, "confidence": 0.9},
        {"deviation_type": "novel_target_domain", "severity": 30.0, "confidence": 0.87},
    ],
    surge_receipt_id="surge-xyz789",
    severity="critical",
    dashboard_url="https://governor.novtia.io/dashboard?event=esc-001",
)
results = router.escalate(event)
```

### Trigger Rules

Each target has independent trigger configuration:

| Rule | Description | Default |
|------|-------------|---------|
| `trigger_on` | Which decisions trigger escalation | `{"block", "review"}` |
| `min_risk_score` | Minimum risk score to escalate | `0` |
| `trigger_on_chain_pattern` | Escalate if chain pattern detected, even below risk threshold | `True` |
| `trigger_on_deviations` | Escalate if fingerprint deviations found, even below risk threshold | `True` |
| `trigger_on_kill_switch` | Always escalate kill switch events regardless of other filters | `True` |

This means you can configure a layered escalation strategy:

- **Slack**: All blocks and reviews above risk 50 → security team awareness
- **Jira**: All blocks above risk 70 → incident ticket for tracking
- **PagerDuty**: Only blocks above risk 90 → page the on-call engineer

Chain patterns and fingerprint deviations bypass the risk threshold because they represent behavioural anomalies that are significant regardless of the individual risk score.

### Slack Message Format

Slack messages use Block Kit for rich formatting:

- Header with decision and severity emoji (🚫 🔴 for critical block)
- Fields grid: tool, risk score, agent ID, severity
- Explanation text
- Chain pattern section (if detected)
- Fingerprint deviations list (if present)
- SURGE receipt reference
- "View in Governor" action button linking to dashboard

Kill switch events override the header to: 🛑 **KILL SWITCH ENGAGED**

### Jira Issue Format

```
Summary: [Governor] BLOCK: http_post — risk 92
Labels: novtia-governor, severity-critical, block
Priority: High
Project: SEC

Description:
  Decision: BLOCK
  Risk Score: 92/100
  Tool: http_post
  Agent: agent_ops_001
  Chain Pattern: credential_then_exfil
  SURGE Receipt: surge-xyz789
  Dashboard: https://governor.novtia.io/dashboard?event=esc-001
```

### PagerDuty Event Format

```json
{
  "routing_key": "your-routing-key",
  "event_action": "trigger",
  "dedup_key": "novtia-agent_ops_001-http_post-esc-001",
  "payload": {
    "summary": "AI Agent BLOCK: http_post (risk 92)",
    "source": "novtia-uk-001",
    "severity": "critical",
    "component": "http_post",
    "group": "agent_ops_001",
    "class": "credential_then_exfil"
  }
}
```

---

## Pipeline Integration

Both modules hook into the evaluation pipeline after the decision is made:

```python
from siem_webhook import SiemDispatcher, event_from_evaluation
from escalation import EscalationRouter, EscalationEvent

# Initialise once at startup
siem = SiemDispatcher()
siem.add_target(SiemTarget(...))

esc = EscalationRouter()
esc.add_target(EscalationTarget(...))

# After every evaluation:
async def post_evaluation(tool, result, receipt, deviations):
    # SIEM — every event, batched
    siem_event = event_from_evaluation(
        tool=tool,
        decision=result.decision,
        risk_score=result.risk_score,
        explanation=result.explanation,
        policy_ids=result.policy_ids,
        chain_pattern=result.chain_pattern,
        surge_receipt_id=receipt.receipt_id if receipt else None,
        surge_digest=receipt.digest if receipt else None,
        deviations=[d.to_dict() for d in deviations],
    )
    siem.dispatch(siem_event)

    # Escalation — only matching events, immediate
    if result.decision in ("block", "review"):
        esc_event = EscalationEvent(
            event_id=siem_event.event_id,
            timestamp=siem_event.timestamp,
            tool=tool,
            decision=result.decision,
            risk_score=result.risk_score,
            explanation=result.explanation,
            agent_id=result.agent_id,
            chain_pattern=result.chain_pattern,
            deviations=[d.to_dict() for d in deviations],
            surge_receipt_id=receipt.receipt_id if receipt else None,
            severity=siem_event.severity,
            dashboard_url=f"https://governor.novtia.io/event/{siem_event.event_id}",
        )
        esc.escalate(esc_event)
```

---

## Running Tests

```bash
cd integrations
pip install pytest
PYTHONPATH=. pytest tests/ -v
```

**Expected: 42 passed**

Test coverage:

SIEM Webhook (24 tests):
- Severity computation (6 tests)
- Event creation from evaluation (2 tests)
- Formatters: Splunk HEC, Elastic ECS, Sentinel, CEF syslog, generic (6 tests)
- Dispatcher: add/list targets, dispatch and deliver, batch flushing, severity filtering, decision filtering, retry, dead letter, flush on shutdown, auth headers, remove target, stats (12 tests)

Escalation Connectors (18 tests):
- Formatters: Slack, Slack kill switch, Teams, Jira, ServiceNow, PagerDuty (6 tests)
- Router: basic escalation, trigger filters, risk threshold, chain pattern bypass, deviation bypass, kill switch override, multiple targets, retry, stats, disabled target, list targets (12 tests)

---

## Requirements

```
# Zero external dependencies for core modules
# stdlib only: json, urllib, socket, threading, time, uuid, hashlib, logging
```

For production deployments with high-volume async delivery, replace `HttpTransport` with `httpx` or `aiohttp`:

```python
import httpx

class AsyncTransport:
    async def post(self, url, headers, body, timeout=10.0):
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, content=body, timeout=timeout)
            return HttpResponse(status=resp.status_code, body=resp.text)
```

---

**Built by Othniel Obasi · NOVTIA · March 2026**
