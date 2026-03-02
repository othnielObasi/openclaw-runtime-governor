# New Modules — Summary, Enhancements & Integration Plan

> Analysis of the five new directories added to openclaw-runtime-governor.
> Covers what each module does, how it enhances the existing Governor, and which existing components it replaces.

---

## Module Overview

| Directory | Purpose | Tests | External Deps |
|---|---|---|---|
| `agent-fingerprinting/` | Behavioural baseline engine — learns per-agent tool-call patterns, flags statistical deviations | 27 | None (stdlib) |
| `surge-v2/` | Cryptographic governance receipt chain with hash chaining, Merkle checkpoints, compliance tagging | 47 | None (stdlib) |
| `integrations/` | Enterprise SIEM webhooks (Splunk/Elastic/Sentinel/Syslog) + escalation connectors (Slack/Teams/Jira/ServiceNow/PagerDuty) | 42 | None (stdlib) |
| `impact-assessment/` | Risk reporting engine — aggregates evaluations into structured assessment reports for auditors | 45 | None (stdlib) |
| `compliance-modules/` | Five pre/post-evaluation security modules: PII scanner, injection detector, budget enforcer, Prometheus metrics, compliance exporter | 54 | None (stdlib) |

**Total: 215 new tests, zero external dependencies across all five modules.**

---

## 1. `agent-fingerprinting/` — Behavioural Baseline Engine

### What It Does

Learns each AI agent's "normal" tool-call patterns over time and flags statistical deviations that static policy rules miss. Runs **6 deviation checks** on every tool call:

| Check | Score Boost | What It Catches |
|---|---|---|
| Novel Tool | +25 | Agent suddenly using a tool it has never used before |
| Frequency Spike | +15 | Abnormally long sessions (many calls beyond the norm) |
| Sequence Anomaly | +20 | Unusual tool-to-tool transition (bigrams) |
| Argument Anomaly | +10 | New argument keys appearing in tool calls |
| Velocity Spike | +15 | Rapid-fire calls within a session |
| Novel Target | +30 | Unknown domains/paths in HTTP arguments |

Has a **maturity model** so new agents aren't over-flagged: learning (0–9 evals, 0× confidence) → developing (10–49, 0.5×) → established (50–199, 0.8×) → mature (200+, 1.0×).

### Does It Enhance the System?

**Yes — significantly.** The existing Governor relies on **static rules** (YAML policies, injection regex patterns, keyword-based neuro risk). It cannot detect:

- An agent that normally uses `read_file` and `summarize` suddenly calling `shell` and `http_request`
- An agent gradually escalating privilege over many sessions
- Abnormal velocity patterns suggesting automated retry attacks

Fingerprinting adds a **dynamic, learned security layer** that improves with usage. The accumulated behavioural baselines become a defensible moat — competitors can copy static policies but not months of learned agent behaviour.

### Does It Replace Anything Existing?

**No.** There is no behavioural analysis in the current codebase. This is a **net-new capability** that layers alongside the existing policy engine.

### Integration Point

- **Pre-eval:** `engine.check(agent_id, tool, args)` → returns deviations that boost the risk score
- **Post-eval:** `engine.record(agent_id, tool, args, decision, risk_score)` → updates the baseline
- **Router:** Mount at `/fingerprint` on the FastAPI app

---

## 2. `surge-v2/` — Cryptographic Governance Receipt Chain

### What It Does

Issues **hash-chained governance receipts** with SHA-256 digests. Each receipt includes the digest of the previous receipt — altering any record breaks the chain. Key features:

- **Hash chain:** `genesis → receipt₀ → receipt₁ → ...` with SHA-256 linking
- **Merkle checkpoints:** Every N receipts (default 100), a Merkle tree root is computed for efficient auditing
- **Compliance auto-tagging:** Each receipt is tagged against EU AI Act (Art. 9/12/13/14/15/17/26), NIST AI RMF, and OWASP Top 10 for LLM 2025
- **Sovereign attestation:** Receipts embed deployment_id, jurisdiction, operator, data_residency, classification
- **Chain verification:** `verify_chain()` walks all receipts checking links, digests, and Merkle roots
- **Audit export:** `export()` generates a self-contained JSON bundle with verification instructions

### Does It Enhance the System?

**Yes — this is a major upgrade.** The existing SURGE v1 (`governor-service/app/api/routes_surge.py`) is fundamentally a **token economy system** — virtual wallets, micro-fee gating, tiered pricing, and policy staking with $SURGE tokens. Its receipts use SHA-256 but are standalone (no chain linking, no Merkle trees, no compliance tagging).

SURGE v2 is an entirely different design philosophy:

| Feature | SURGE v1 (Current) | SURGE v2 (New) |
|---|---|---|
| Purpose | Token economy / fee gating | Cryptographic audit trail |
| Hash chaining | No (standalone hashes) | Yes (each receipt links to previous) |
| Merkle checkpoints | No | Yes (configurable interval) |
| Tamper detection | No chain verification | Full chain + Merkle verification |
| Compliance tagging | No | EU AI Act, NIST RMF, OWASP LLM |
| Sovereign attestation | No | Jurisdiction, operator, data residency |
| Audit export | No | Self-contained JSON bundle with verification instructions |
| Token wallets | Yes | Removed |
| Fee gating | Yes | Removed |
| Policy staking | Yes | Removed |

### Does It Replace Anything Existing?

**Yes — it replaces `governor-service/app/api/routes_surge.py` (SURGE v1).**

The token economy features (wallets, fees, staking) are removed in v2. If those are still needed, they could be preserved as a separate module, but the receipt system, chain verification, and `/surge` routes should be replaced entirely by v2.

### Integration Point

- **Post-eval:** `surge.issue(tool, decision, risk_score, explanation, policy_ids, chain_pattern, agent_id)`
- **Router:** Replace existing `/surge` routes with v2 router
- **Database models:** `SurgeReceipt`, `SurgeStakedPolicy`, `SurgeWallet` tables become unused if v1 is fully replaced

---

## 3. `integrations/` — Enterprise SIEM + Escalation Connectors

### What It Does

Two enterprise integration modules:

**SIEM Webhook (`SiemDispatcher`)** — Pushes governance events to external security systems:

| Target | Format |
|---|---|
| Splunk | HEC JSON with auth token |
| Elastic | ECS (Elastic Common Schema) |
| Microsoft Sentinel | Log Analytics API |
| Syslog | CEF (Common Event Format) |
| Generic | JSON POST webhook |

Features per-target batching, severity/decision filtering, retry with exponential backoff, and a dead-letter queue.

**Escalation Connectors (`EscalationRouter`)** — Routes block/review decisions to incident management:

| Target | Format |
|---|---|
| Slack | Block Kit messages |
| Microsoft Teams | Adaptive Cards |
| Jira | Issue creation |
| ServiceNow | Incident creation |
| PagerDuty | Events API v2 |
| Generic | JSON POST webhook |

Features layered trigger rules: decision filter, risk threshold, chain pattern bypass, deviation bypass, kill switch override.

### Does It Enhance the System?

**Yes — substantially.** The existing escalation system (`governor-service/app/escalation/`) has:

- Database-backed escalation configs and review queues
- Basic webhook delivery (CRUD for webhook URLs)
- Auto-kill-switch logic based on block thresholds

The new `integrations/` module adds:

- **SIEM integration** (entirely new — no SIEM support exists today)
- **Rich message formatting** for Slack Block Kit, Teams Adaptive Cards, Jira issues, ServiceNow incidents, PagerDuty with dedup keys
- **SURGE receipt IDs and fingerprint deviations** embedded in every outgoing event
- **Batching and dead-letter** infrastructure for production reliability

### Does It Replace Anything Existing?

**Partially.** The new escalation connectors overlap with `governor-service/app/escalation/` webhook delivery, but the existing module has DB-backed config, review queues, and auto-kill-switch logic that the new module does not replicate. The recommended approach:

- **Keep** the existing `escalation/` for its review queue, config CRUD, and auto-kill-switch logic
- **Add** the new `integrations/escalation/` connectors as the **delivery backend** — when the existing system decides to notify, use the new rich formatters and retry logic
- **Add** the new `integrations/siem_webhook/` as an entirely new capability

---

## 4. `impact-assessment/` — Risk Reporting Engine

### What It Does

Aggregates governance evaluation data into three report types:

| Report | Method | Contents |
|---|---|---|
| **Full assessment** | `assess(period)` | System-wide risk: distributions (p50/p90/p95/p99), score buckets, decision breakdown, chain pattern frequency, deviation frequency, top-10 riskiest agents/tools, daily trends, policy effectiveness, recommendations |
| **Agent assessment** | `assess_agent(id)` | Per-agent: block rate, chain patterns, deviation history, unique tools, active hours, recommendations |
| **Tool assessment** | `assess_tool(name)` | Per-tool: blast radius, agents using it, block rate, common block reasons, recommendations |

Risk classification: minimal → low → moderate → high → critical. Recommendations are data-driven (not static templates).

Compliance coverage: ISO 42001 Clause 6 (risk assessment), NIST AI RMF MAP-5 (impact assessment), EU AI Act Art. 9 (continuous risk management).

### Does It Enhance the System?

**Yes — this is a completely new capability.** The existing Governor collects evaluation data (action logs, traces, summaries) but has **no aggregation or reporting engine**. The dashboard's `SummaryPanel` shows basic counters, but there is no:

- Statistical risk distribution analysis
- Trend detection over time
- Per-agent or per-tool risk profiling
- Automated recommendations
- Compliance-ready export for auditors

This transforms raw governance data into the structured evidence compliance teams need for ISO 42001 and NIST AI RMF audits.

### Does It Replace Anything Existing?

**No.** The existing `/summary` endpoints provide basic metrics (decision counts, risk averages). The impact assessment engine produces a fundamentally different output — deep statistical reports. The summary endpoints can remain as lightweight real-time metrics while `/impact` serves compliance reporting.

### Integration Point

- **Post-eval:** `engine.record(tool, decision, risk_score, agent_id, policy_ids, chain_pattern, deviation_types)`
- **Router:** Mount at `/impact` on the FastAPI app

---

## 5. `compliance-modules/` — Pre/Post-Evaluation Security Modules

### What It Does

Five modules that plug into the evaluation pipeline at different stages:

| Module | Stage | Purpose |
|---|---|---|
| **PII Scanner** | Pre-eval (input) + Post-eval (output) | Detects 12 PII entity types: SSN, credit card (Luhn-validated), email, phone, IBAN, NHS number, passport, IP, API keys (OpenAI/GitHub/Slack), AWS keys, JWT, private keys. Risk boost per finding. |
| **Injection Detector** | Pre-eval | 54+ regex patterns across 10 categories + custom TF-IDF cosine similarity for paraphrased variants. Categories: direct injection, jailbreak, role play, system prompt extraction, encoding bypass, context overflow, delimiter escape, instruction smuggling, exfiltration, privilege escalation, multi-language. |
| **Budget Enforcer** | Pre-eval gate | Per-session/hour/day evaluation count limits + cost caps. Circuit breaker after N consecutive blocks with auto-cooldown. |
| **Metrics** | Post-eval | Zero-dep Prometheus exporter: 12 metric families (counters, histograms, gauges). Text format at `/metrics`. |
| **Compliance Exporter** | On-demand | Generates OWASP/NIST/EU AI Act compliance reports from recorded actions. CSV export. |

### Does It Enhance the System?

**Yes — each module adds significant depth:**

- **PII Scanner:** Entirely new. The existing Governor has no PII detection at all. Catches SSNs, credit cards, API keys, JWTs, and private keys in tool inputs/outputs.

- **Injection Detector:** The existing injection firewall (`policies/engine.py`) has **20 regex patterns** in a single flat list. The new detector has **54+ patterns** across 10 categorized threat types, plus a **TF-IDF semantic similarity engine** that catches paraphrased injection attempts the regex alone would miss. It also supports multi-language detection (Chinese, French, etc.).

- **Budget Enforcer:** Entirely new. No rate limiting per-agent or per-session cost tracking exists in the current Governor (there is a request-level rate limiter via slowapi, but no eval budget enforcement).

- **Metrics:** Entirely new. No Prometheus metrics endpoint exists. The current `/summary` endpoint returns JSON counters but not Prometheus exposition format.

- **Compliance Exporter:** Entirely new. No compliance-specific report generation exists.

### Does It Replace Anything Existing?

**The injection detector is a superset of the existing injection firewall.** The current firewall in `governor-service/app/policies/engine.py` (20 patterns, no categorization, no semantic matching) should be **replaced** by the new `SemanticInjectionDetector` (54+ patterns, 10 categories, TF-IDF cosine similarity). The other four modules are all net-new.

| Existing Component | Replacement / Enhancement |
|---|---|
| `policies/engine.py` `_run_injection_firewall()` (20 patterns) | `injection_detector.SemanticInjectionDetector` (54+ patterns + TF-IDF semantic) |
| `neuro/risk_estimator.py` keyword scanning | **Enhanced by** PII scanner + injection detector risk boosts (not replaced — neuro estimator covers different heuristics) |
| slowapi request rate limiter | **Complemented by** budget enforcer (different scope: eval count limits, not HTTP rate limits) |

---

## Replacement Summary

| New Module | Replaces Existing? | Details |
|---|---|---|
| `agent-fingerprinting/` | **No** | Net-new behavioural analysis capability |
| `surge-v2/` | **Yes** | Replaces `governor-service/app/api/routes_surge.py` (v1 token economy → v2 cryptographic audit trail) |
| `integrations/siem_webhook/` | **No** | Net-new SIEM integration |
| `integrations/escalation/` | **Partial** | Adds rich formatters and delivery backend; existing `escalation/` review queue and auto-kill-switch remain |
| `impact-assessment/` | **No** | Net-new risk reporting engine |
| `compliance-modules/injection_detector` | **Yes** | Replaces `policies/engine.py` `_run_injection_firewall()` with 54+ patterns + TF-IDF |
| `compliance-modules/pii_scanner` | **No** | Net-new PII detection |
| `compliance-modules/budget_enforcer` | **No** | Net-new eval budget enforcement |
| `compliance-modules/metrics` | **No** | Net-new Prometheus metrics |
| `compliance-modules/compliance_exporter` | **No** | Net-new compliance reporting |

---

## Full Pipeline Integration

Where each module plugs into the evaluation flow:

```
Incoming tool call
  │
  ├─ 1. budget_enforcer.check_budget()          ← compliance-modules (NEW)
  ├─ 2. injection_detector.analyze()             ← compliance-modules (REPLACES injection firewall)
  ├─ 3. pii_scanner.scan_input()                 ← compliance-modules (NEW)
  ├─ 4. fingerprint_engine.check()               ← agent-fingerprinting (NEW)
  │     (deviations boost risk_score)
  │
  ▼
  EXISTING POLICY ENGINE (kill switch → scope → YAML/DB policies → neuro risk)
  │
  ▼
  Post-evaluation:
  ├─ 5. fingerprint_engine.record()              ← agent-fingerprinting (NEW)
  ├─ 6. surge_engine.issue()                     ← surge-v2 (REPLACES v1)
  ├─ 7. pii_scanner.scan_output()                ← compliance-modules (NEW)
  ├─ 8. metrics.record_evaluation()              ← compliance-modules (NEW)
  ├─ 9. impact_engine.record()                   ← impact-assessment (NEW)
  ├─ 10. siem_dispatcher.dispatch()              ← integrations (NEW)
  ├─ 11. escalation_router.escalate()            ← integrations (ENHANCES existing)
  └─ 12. event_bus.publish()                     ← existing SSE stream
```

---

## Key Architectural Notes

1. **All five modules use stdlib only** for core logic — no heavy ML libraries or external service dependencies. FastAPI/Pydantic are needed only for the HTTP routers.

2. **All modules expose FastAPI routers** mountable via `app.include_router()` in `main.py`.

3. **Cross-module data flow is built in:** SIEM events carry `surge_receipt_id` and `deviations`; escalation events carry `surge_receipt_id`; impact reports include `chain_pattern` and `deviation_types`. The modules are designed to enrich each other.

4. **The existing `EventBus` / `ActionEvent`** already carries `chain_pattern`, `agent_id`, `session_id` — the new modules consume and produce these same fields.

5. **Thread safety:** `FingerprintEngine`, `SurgeEngine`, `BudgetEnforcer`, and `SiemDispatcher` all use `threading.Lock` for in-memory state.

6. **In-memory state:** All modules currently store state in memory. For production persistence, the engines would need database-backed storage or periodic snapshots — but this doesn't block initial integration.

---

*Generated March 2026 — NOVTIA Governor*
