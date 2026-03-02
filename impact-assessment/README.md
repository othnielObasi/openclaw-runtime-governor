# NOVTIA Governor — Impact Assessment Engine

> Turns governance data into structured risk reports. Compliance teams get production evidence, not guesswork.

**45 tests passing** · Zero external dependencies · Python 3.9+

---

## What It Does

The Governor already records every evaluation — risk score, decision, tool, agent, policies, chain patterns, fingerprint deviations. The impact assessment engine aggregates that data into three report types:

**Full assessment** — system-wide risk overview with distributions, trends, top-risk agents/tools, policy effectiveness, and actionable recommendations. This is what compliance teams hand to auditors for ISO 42001 Clause 6 and NIST MAP-5.

**Agent assessment** — per-agent risk profile showing block rate, chain patterns detected, fingerprint deviation history, tools used, and agent-specific recommendations.

**Tool assessment** — per-tool risk profile showing which agents use it, block rate, common block reasons, and whether the tool's blast radius warrants tighter policies.

---

## Compliance Coverage

| Requirement | Framework | How This Addresses It |
|---|---|---|
| AI risk assessment | ISO 42001 Clause 6 | Risk distributions, risk level classification, per-agent/tool profiles |
| Impact assessment | NIST AI RMF MAP-5 | Agent and tool impact data, trend analysis, recommendations |
| Continuous risk management | EU AI Act Art.9 | Daily trends, policy effectiveness tracking, automated risk classification |

---

## API Endpoints

Mount: `app.include_router(router, prefix="/impact")`

| Method | Path | Description |
|---|---|---|
| `GET` | `/impact/assess?period=30d` | Full system assessment |
| `GET` | `/impact/assess/agent/{id}?period=30d` | Agent risk profile |
| `GET` | `/impact/assess/tool/{name}?period=30d` | Tool risk profile |
| `GET` | `/impact/agents` | List all assessed agents |
| `GET` | `/impact/tools` | List all assessed tools |

Periods: `24h`, `7d`, `30d`, `90d`, `all`

---

## Quick Start

```python
from impact_assessment import ImpactAssessmentEngine, AssessmentPeriod

engine = ImpactAssessmentEngine()

# Feed from evaluation pipeline (or connect to DB)
engine.record(
    tool="shell", decision="block", risk_score=85,
    agent_id="agent_001", policy_ids=["pol_sec_1"],
    chain_pattern="credential_then_exfil",
    deviation_types=["novel_tool"],
    explanation="Injection detected",
)

# Generate reports
report = engine.assess(AssessmentPeriod.LAST_30D)
agent_profile = engine.assess_agent("agent_001")
tool_profile = engine.assess_tool("shell")
```

---

## Report Contents

The full assessment includes: risk distribution with percentiles (p50/p90/p95/p99) and score buckets, overall risk classification (minimal/low/moderate/high/critical), decision breakdown, chain pattern frequency, fingerprint deviation frequency, top 10 riskiest agents and tools ranked by average risk score, daily trend data, policy hit counts with never-triggered policy detection, compliance framework references, and generated recommendations.

Recommendations are data-driven: high block rates, recurring chain patterns, frequent deviations, and top blocked tools each produce specific actionable guidance. Smooth operations with low risk produce a recommendation to run a red team exercise to validate policy coverage.

---

## Running Tests

```bash
pip install pytest
PYTHONPATH=. pytest tests/ -v
```

**Expected: 45 passed**

---

**Built by Othniel Obasi · NOVTIA · March 2026**
