# Integration & Gap Closure — Implementation Plan

> Phased plan to integrate the 5 new modules into governor-service and close identified market-readiness gaps.
> Each phase is self-contained, testable, and deployable independently.

---

## Architecture After Integration

```
governor-service/app/
├── __init__.py
├── main.py                          ← Mount new routers here
├── config.py                        ← Add new settings
├── database.py                      ← Unchanged
├── models.py                        ← Add new DB models
├── schemas.py                       ← Extend ActionDecision
├── state.py                         ← Unchanged
├── event_bus.py                     ← Unchanged
├── session_store.py                 ← Unchanged
├── chain_analysis.py                ← Unchanged
├── rate_limit.py                    ← Unchanged
├── encryption.py                    ← Unchanged
│
├── api/
│   ├── routes_actions.py            ← PRIMARY EDIT: pre/post hooks
│   ├── routes_policies.py
│   ├── routes_summary.py
│   ├── routes_admin.py
│   ├── routes_surge.py              ← REPLACE with v2 adapter
│   ├── routes_stream.py
│   ├── routes_traces.py
│   ├── routes_notifications.py
│   ├── routes_verify.py
│   └── routes_conversations.py
│
├── auth/                            ← Unchanged
├── escalation/                      ← Keep; enhanced by integrations/
├── neuro/                           ← Unchanged
├── policies/
│   ├── engine.py                    ← EDIT: replace injection firewall
│   └── loader.py                    ← Unchanged
├── telemetry/                       ← Unchanged
├── verification/                    ← Unchanged
│
├── modules/                         ← NEW: unified module registry
│   ├── __init__.py                  ← GovernorModules singleton
│   ├── fingerprinting.py            ← Wraps agent-fingerprinting/
│   ├── surge_v2.py                  ← Wraps surge-v2/
│   ├── compliance.py                ← Wraps compliance-modules/
│   ├── impact.py                    ← Wraps impact-assessment/
│   ├── siem.py                      ← Wraps integrations/siem_webhook/
│   └── escalation_connectors.py     ← Wraps integrations/escalation/
│
└── models_v2.py                     ← NEW: DB models for persistent state
```

---

## Phase 1 — Module Registry & Compliance Modules (Pre-Eval)

**Goal:** Wire PII scanner, injection detector, and budget enforcer into the evaluation pipeline. These provide immediate security value with minimal risk.

### Step 1.1 — Create the module registry

Create `governor-service/app/modules/__init__.py`:

```python
"""
GovernorModules — singleton registry for all optional modules.
Each module is lazy-loaded and can be enabled/disabled via config.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("governor.modules")

@dataclass
class GovernorModules:
    """Central registry. Instantiated once at app startup."""
    # compliance-modules
    pii_scanner: Optional[object] = None
    injection_detector: Optional[object] = None
    budget_enforcer: Optional[object] = None
    metrics: Optional[object] = None
    compliance_exporter: Optional[object] = None

    # agent-fingerprinting
    fingerprint_engine: Optional[object] = None

    # surge-v2
    surge_engine: Optional[object] = None

    # impact-assessment
    impact_engine: Optional[object] = None

    # integrations
    siem_dispatcher: Optional[object] = None
    escalation_router: Optional[object] = None

# Singleton — populated by main.py at startup
modules = GovernorModules()
```

### Step 1.2 — Add config settings

Add to `governor-service/app/config.py`:

```python
# ── Module toggles ──
fingerprinting_enabled: bool = True
surge_v2_enabled: bool = True
pii_scanner_enabled: bool = True
injection_detector_enabled: bool = True
budget_enforcer_enabled: bool = True
metrics_enabled: bool = True
impact_assessment_enabled: bool = True
siem_enabled: bool = False            # Off by default — needs target config
escalation_connectors_enabled: bool = False  # Off by default — needs target config

# ── Budget defaults ──
budget_max_per_session: int = 200
budget_max_per_hour: int = 500
budget_max_per_day: int = 5000
budget_circuit_breaker_threshold: int = 5

# ── Fingerprinting ──
fingerprint_confidence_multiplier: float = 1.0

# ── SURGE v2 ──
surge_v2_checkpoint_interval: int = 100
surge_v2_jurisdiction: str = ""
surge_v2_operator: str = ""
surge_v2_deployment_id: str = ""

# ── SIEM ──
siem_targets_json: str = "[]"        # JSON array of SiemTarget configs

# ── Escalation connectors ──
escalation_targets_json: str = "[]"  # JSON array of EscalationTarget configs
```

### Step 1.3 — Initialize modules in main.py

Add after `seed_admin()` in `main.py`:

```python
from .modules import modules as gov_modules

def _init_modules() -> None:
    """Initialize optional governance modules based on config."""
    import sys, importlib

    # Add workspace root to path for external module imports
    sys.path.insert(0, "/workspaces/openclaw-runtime-governor")

    if settings.pii_scanner_enabled:
        from pii_scanner import PIIScanner
        gov_modules.pii_scanner = PIIScanner()
        log.info("Module loaded: pii_scanner")

    if settings.injection_detector_enabled:
        from injection_detector import SemanticInjectionDetector
        gov_modules.injection_detector = SemanticInjectionDetector()
        log.info("Module loaded: injection_detector")

    if settings.budget_enforcer_enabled:
        from budget_enforcer import BudgetEnforcer, BudgetConfig
        gov_modules.budget_enforcer = BudgetEnforcer(BudgetConfig(
            max_per_session=settings.budget_max_per_session,
            max_per_hour=settings.budget_max_per_hour,
            max_per_day=settings.budget_max_per_day,
            circuit_breaker_threshold=settings.budget_circuit_breaker_threshold,
        ))
        log.info("Module loaded: budget_enforcer")

    if settings.metrics_enabled:
        from metrics import metrics as prom_metrics
        gov_modules.metrics = prom_metrics
        log.info("Module loaded: metrics")

    # ... (other modules initialized in later phases)

_init_modules()
```

### Step 1.4 — Replace the injection firewall in policies/engine.py

Edit `governor-service/app/policies/engine.py`, Layer 2:

```python
# ── Layer 2: Injection detection ──────────────────────────────────
t = time.perf_counter()
from ..modules import modules as gov_modules

if gov_modules.injection_detector:
    analysis = gov_modules.injection_detector.analyze_tool_call(action.tool, action.args)
    if analysis.detected:
        top = analysis.matches[0]
        trace.append(_step(2, "Injection Detector", "firewall", "block",
                           min(95, top.risk_boost),
                           [m.pattern_name for m in analysis.matches],
                           f"Injection detected: {top.category} — {top.description} "
                           f"(confidence: {top.confidence:.0%}, method: {top.method})", t))
        return ActionDecision(
            decision="block", risk_score=min(95, top.risk_boost),
            explanation=f"Injection detected: {top.description}",
            policy_ids=["injection-detector"], execution_trace=trace,
        )
    trace.append(_step(2, "Injection Detector", "firewall", "pass", 0, [],
                       f"Scanned {len(gov_modules.injection_detector._patterns)} patterns "
                       f"+ semantic similarity — clean.", t))
else:
    # Fallback to legacy 20-pattern firewall
    triggered, reason, inj_matched = _run_injection_firewall(action)
    # ... existing logic unchanged ...
```

### Step 1.5 — Add PII + budget pre-eval hooks in routes_actions.py

Edit the `evaluate_action_route()` function, insert **before** `evaluate_action(action)`:

```python
from ..modules import modules as gov_modules

# ── Pre-eval: Budget gate ──
if gov_modules.budget_enforcer:
    agent_id = ctx.get("agent_id", "unknown")
    budget_status = gov_modules.budget_enforcer.check_budget(agent_id)
    if not budget_status.allowed:
        raise HTTPException(status_code=429, detail=f"Budget exceeded: {budget_status.reason}")

# ── Pre-eval: PII scan on input ──
pii_risk_boost = 0
pii_findings = []
if gov_modules.pii_scanner:
    pii_result = gov_modules.pii_scanner.scan_input(action.tool, action.args)
    pii_findings = pii_result.findings
    pii_risk_boost = pii_result.risk_boost

# ── Pre-eval: Injection detection (inline boost — full block in engine.py) ──
injection_risk_boost = 0
if gov_modules.injection_detector:
    inj_analysis = gov_modules.injection_detector.analyze(str(action.args))
    injection_risk_boost = inj_analysis.risk_boost
```

### Step 1.6 — Mount compliance routers in main.py

```python
if settings.pii_scanner_enabled:
    from pii_scanner.router import router as pii_router
    app.include_router(pii_router, prefix="/compliance/pii", tags=["compliance"])

if settings.metrics_enabled:
    from metrics import router as metrics_router
    app.include_router(metrics_router, tags=["observability"])
```

### Step 1.7 — Tests

- Verify existing 20-pattern tests still pass (fallback mode)
- New tests: injection detector catches paraphrased attacks
- New tests: PII scanner blocks SSNs/credit cards in tool args
- New tests: budget enforcer returns 429 when limits exceeded
- Run: `pytest governor-service/tests/ -v`
- Run: `pytest compliance-modules/tests/ -v`

**Deliverable:** Pre-eval security hardening live. All existing tests green. New `/compliance/pii/scan` and `/metrics` endpoints active.

---

## Phase 2 — Agent Fingerprinting

**Goal:** Wire behavioural fingerprinting into the eval pipeline (pre-eval check, post-eval record) and persist fingerprint data.

### Step 2.1 — Initialize fingerprint engine

In the `_init_modules()` function:

```python
if settings.fingerprinting_enabled:
    from fingerprinting import FingerprintEngine
    gov_modules.fingerprint_engine = FingerprintEngine()
    log.info("Module loaded: fingerprint_engine")
```

### Step 2.2 — Add fingerprinting to evaluate pipeline

**In `policies/engine.py`** — add as Layer 2.5 (after injection, before scope):

```python
# ── Layer 2.5: Behavioural fingerprinting ─────────────────────────
t = time.perf_counter()
deviations = []
if gov_modules.fingerprint_engine and agent_id:
    deviations = gov_modules.fingerprint_engine.check(
        agent_id=agent_id, tool=action.tool,
        args=action.args, session_id=session_id,
    )
    if deviations:
        dev_boost = sum(d.severity for d in deviations)
        risk_score = min(100, risk_score + dev_boost)
        dev_names = [d.deviation_type for d in deviations]
        trace.append(_step(2.5, "Fingerprint Check", "fingerprint",
                           "flag", dev_boost, dev_names,
                           f"{len(deviations)} deviations: {', '.join(dev_names)}. "
                           f"+{dev_boost} risk.", t))
    else:
        trace.append(_step(2.5, "Fingerprint Check", "fingerprint",
                           "pass", 0, [], "No deviations from baseline.", t))
```

**In `routes_actions.py`** — post-eval recording (after `log_action()`):

```python
# ── Post-eval: Record fingerprint baseline ──
if gov_modules.fingerprint_engine:
    agent_id = ctx.get("agent_id")
    if agent_id:
        gov_modules.fingerprint_engine.record(
            agent_id=agent_id, tool=action.tool,
            args=action.args, decision=decision.decision,
            risk_score=decision.risk_score,
            session_id=ctx.get("session_id"),
        )
```

### Step 2.3 — Extend ActionDecision schema

Add to `schemas.py` `ActionDecision`:

```python
deviation_types: list[str] = Field(default_factory=list, description="Fingerprint deviations detected")
deviation_count: int = Field(0, description="Number of fingerprint deviations")
```

### Step 2.4 — DB persistence for fingerprints

Add to `models.py` (or `models_v2.py`):

```python
class AgentFingerprintSnapshot(Base):
    """Periodic snapshot of agent behavioural fingerprint for persistence."""
    __tablename__ = "agent_fingerprint_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    snapshot_json: Mapped[str] = mapped_column(Text)       # Serialized AgentFingerprint
    total_evaluations: Mapped[int] = mapped_column(Integer)
    maturity_level: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
```

Add a background task or post-eval hook that periodically snapshots:

```python
# Every 50 evaluations, persist the fingerprint
if fp.total_evaluations % 50 == 0:
    _persist_fingerprint_snapshot(agent_id, fp)
```

On startup, restore from latest snapshot:

```python
def _restore_fingerprints():
    """Load latest fingerprint snapshots from DB into the in-memory engine."""
    # Query latest snapshot per agent_id, deserialize, load into engine
```

### Step 2.5 — Mount fingerprint router

```python
if settings.fingerprinting_enabled:
    from fingerprinting.router import router as fp_router
    app.include_router(fp_router, prefix="/fingerprint", tags=["fingerprinting"])
```

### Step 2.6 — Tests

- Run: `pytest agent-fingerprinting/tests/ -v` (27 tests)
- New integration tests: fingerprint deviations boost risk_score in full eval flow
- Snapshot persistence: save + restart + verify restoration

**Deliverable:** Behavioural fingerprinting live in eval pipeline. Deviations visible in execution_trace. Fingerprints persisted to DB.

---

## Phase 3 — SURGE v2 (Cryptographic Audit Trail)

**Goal:** Replace SURGE v1 token economy with v2 hash-chained receipts. Preserve v1 tables for migration.

### Step 3.1 — Initialize SURGE v2

```python
if settings.surge_v2_enabled:
    from surge import SurgeEngine, SovereignConfig
    gov_modules.surge_engine = SurgeEngine(
        config=SovereignConfig(
            deployment_id=settings.surge_v2_deployment_id or "default",
            jurisdiction=settings.surge_v2_jurisdiction,
            operator=settings.surge_v2_operator,
        ),
        checkpoint_interval=settings.surge_v2_checkpoint_interval,
    )
    log.info("Module loaded: surge_v2")
```

### Step 3.2 — Replace receipt creation in routes_actions.py

Replace the `create_governance_receipt()` call:

```python
# ── SURGE receipt ──
surge_receipt_id = None
if gov_modules.surge_engine:
    receipt = gov_modules.surge_engine.issue(
        tool=action.tool,
        decision=decision.decision,
        risk_score=decision.risk_score,
        explanation=decision.explanation,
        policy_ids=decision.policy_ids,
        chain_pattern=decision.chain_pattern,
        agent_id=ctx.get("agent_id"),
        session_id=ctx.get("session_id"),
        extra_context={
            "deviation_types": decision.deviation_types,
            "pii_findings": len(pii_findings),
        },
    )
    surge_receipt_id = receipt.receipt_id
    _persist_surge_receipt(receipt)  # Write to DB
else:
    # Fallback to v1 receipt
    create_governance_receipt(...)
```

### Step 3.3 — DB model for v2 receipts

```python
class SurgeReceiptV2(Base):
    """SURGE v2 hash-chained governance receipt."""
    __tablename__ = "surge_receipts_v2"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    receipt_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    sequence: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    tool: Mapped[str] = mapped_column(String(128), index=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    risk_score: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    policy_ids_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chain_pattern: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Cryptographic chain
    digest: Mapped[str] = mapped_column(String(64), index=True)
    previous_digest: Mapped[str] = mapped_column(String(64))
    merkle_root: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Compliance
    compliance_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Sovereign attestation
    sovereign_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SurgeMerkleCheckpoint(Base):
    """Merkle checkpoint for SURGE v2 chain."""
    __tablename__ = "surge_merkle_checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    checkpoint_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    sequence_start: Mapped[int] = mapped_column(Integer)
    sequence_end: Mapped[int] = mapped_column(Integer)
    merkle_root: Mapped[str] = mapped_column(String(64))
    leaf_digests_json: Mapped[str] = mapped_column(Text)
```

### Step 3.4 — Restore chain on startup

```python
def _restore_surge_chain():
    """Load all SURGE v2 receipts from DB → rebuild in-memory hash chain."""
    with db_session() as session:
        rows = session.query(SurgeReceiptV2).order_by(SurgeReceiptV2.sequence).all()
        for row in rows:
            gov_modules.surge_engine._chain.append(_row_to_receipt(row))
        # Restore last_digest
        if rows:
            gov_modules.surge_engine._last_digest = rows[-1].digest
```

### Step 3.5 — Mount v2 router, deprecate v1

```python
if settings.surge_v2_enabled:
    from surge.router import router as surge_v2_router
    app.include_router(surge_v2_router, prefix="/surge/v2", tags=["surge-v2"])
    # Keep /surge (v1) for backward compat during migration

    # Remove SURGE wallet gating from evaluate route
```

Remove the `check_wallet_balance()` call from `evaluate_action_route()` when v2 is active.

### Step 3.6 — Add receipt_id to ActionDecision

```python
# In schemas.py ActionDecision:
surge_receipt_id: Optional[str] = Field(None, description="SURGE v2 receipt ID")
surge_digest: Optional[str] = Field(None, description="SHA-256 digest of governance receipt")
```

### Step 3.7 — Tests

- Run: `pytest surge-v2/tests/ -v` (47 tests)
- Integration: issue receipt → verify chain → export bundle
- Migration: v1 receipts remain queryable during transition
- Tamper detection: modify a DB row → verify_chain() catches it

**Deliverable:** Cryptographic audit trail live. Every evaluation produces a hash-chained, compliance-tagged receipt. Export endpoint for auditors.

---

## Phase 4 — Impact Assessment

**Goal:** Wire impact engine into post-eval flow. Mount reporting endpoints.

### Step 4.1 — Initialize

```python
if settings.impact_assessment_enabled:
    from impact_assessment import ImpactAssessmentEngine
    gov_modules.impact_engine = ImpactAssessmentEngine()
    log.info("Module loaded: impact_assessment")
```

### Step 4.2 — Post-eval recording in routes_actions.py

After `log_action()`:

```python
# ── Post-eval: Impact assessment recording ──
if gov_modules.impact_engine:
    gov_modules.impact_engine.record(
        tool=action.tool,
        decision=decision.decision,
        risk_score=decision.risk_score,
        agent_id=ctx.get("agent_id", "unknown"),
        session_id=ctx.get("session_id", ""),
        policy_ids=decision.policy_ids,
        chain_pattern=decision.chain_pattern,
        deviation_types=decision.deviation_types,
        explanation=decision.explanation,
    )
```

### Step 4.3 — Mount router

```python
if settings.impact_assessment_enabled:
    from impact_assessment.router import router as impact_router
    app.include_router(impact_router, prefix="/impact", tags=["impact-assessment"])
```

### Step 4.4 — DB persistence for impact data

Impact engine currently stores `EvaluationRecord` objects in memory. For persistence:

Option A (simple): Impact engine reads from the existing `action_logs` table — the data is already there. Modify `assess()` to accept records directly from DB queries instead of only in-memory.

Option B (fast): Keep in-memory for real-time, add startup restoration from `action_logs`:

```python
def _restore_impact_data():
    """Backfill impact engine from action_logs on startup."""
    with db_session() as session:
        recent = session.query(ActionLog).order_by(ActionLog.created_at.desc()).limit(10000).all()
        for row in reversed(recent):
            gov_modules.impact_engine.record(
                tool=row.tool, decision=row.decision,
                risk_score=row.risk_score, agent_id=row.agent_id or "unknown",
                session_id=row.session_id or "",
                policy_ids=row.policy_ids.split(",") if row.policy_ids else [],
                chain_pattern=row.chain_pattern,
            )
```

**Recommended: Option B** — uses existing DB data, no new tables needed. Impact engine gets instant history on restart.

### Step 4.5 — Tests

- Run: `pytest impact-assessment/tests/ -v` (45 tests)
- Integration: 100 evaluations → GET /impact/assess → verify report structure
- Restart: verify data survives via action_logs backfill

**Deliverable:** `/impact/assess`, `/impact/assess/agent/{id}`, `/impact/assess/tool/{name}` live. Compliance teams can pull structured risk reports.

---

## Phase 5 — Enterprise Integrations (SIEM + Escalation Connectors)

**Goal:** Wire SIEM dispatching and rich escalation formatting into the post-eval flow.

### Step 5.1 — Initialize SIEM

```python
if settings.siem_enabled:
    import json
    from siem_webhook import SiemDispatcher, SiemTarget
    gov_modules.siem_dispatcher = SiemDispatcher()
    targets = json.loads(settings.siem_targets_json)
    for t in targets:
        gov_modules.siem_dispatcher.add_target(SiemTarget(**t))
    log.info("Module loaded: siem_dispatcher (%d targets)", len(targets))
```

### Step 5.2 — Initialize escalation connectors

```python
if settings.escalation_connectors_enabled:
    import json
    from escalation import EscalationRouter as ConnectorRouter, EscalationTarget
    gov_modules.escalation_router = ConnectorRouter()
    targets = json.loads(settings.escalation_targets_json)
    for t in targets:
        gov_modules.escalation_router.add_target(EscalationTarget(**t))
    log.info("Module loaded: escalation_connectors (%d targets)", len(targets))
```

### Step 5.3 — Post-eval hooks in routes_actions.py

After the existing `handle_post_evaluation()`:

```python
# ── Post-eval: SIEM dispatch ──
if gov_modules.siem_dispatcher:
    from siem_webhook import event_from_evaluation
    siem_event = event_from_evaluation(
        tool=action.tool,
        decision=decision.decision,
        risk_score=decision.risk_score,
        explanation=decision.explanation,
        policy_ids=decision.policy_ids,
        chain_pattern=decision.chain_pattern,
        agent_id=ctx.get("agent_id"),
        session_id=ctx.get("session_id"),
        surge_receipt_id=surge_receipt_id,
        deviations=[d.to_dict() for d in deviations] if deviations else [],
    )
    gov_modules.siem_dispatcher.dispatch(siem_event)

# ── Post-eval: Rich escalation ──
if gov_modules.escalation_router and decision.decision in ("block", "review"):
    from escalation import EscalationEvent as ConnectorEvent
    esc_event = ConnectorEvent(
        tool=action.tool,
        decision=decision.decision,
        risk_score=decision.risk_score,
        explanation=decision.explanation,
        chain_pattern=decision.chain_pattern,
        deviations=decision.deviation_types,
        surge_receipt_id=surge_receipt_id,
        agent_id=ctx.get("agent_id"),
    )
    gov_modules.escalation_router.escalate(esc_event)
```

### Step 5.4 — Tests

- Run: `pytest integrations/tests/ -v` (42 tests)
- Integration: evaluate with block → verify SIEM mock received event
- Integration: evaluate with block, risk > threshold → verify Slack/Teams mock triggered

**Deliverable:** Governance events flowing to Splunk/Elastic/Sentinel. Block decisions triggering Slack/Teams/Jira/PagerDuty with rich formatting.

---

## Phase 6 — Post-Eval Metrics & Compliance Export

**Goal:** Wire Prometheus metrics recording and compliance exporter.

### Step 6.1 — Post-eval metrics recording

In `routes_actions.py`, after all other post-eval hooks:

```python
# ── Post-eval: Prometheus metrics ──
if gov_modules.metrics:
    import time
    eval_duration_ms = (datetime.now(timezone.utc) - eval_start).total_seconds() * 1000
    gov_modules.metrics.record_evaluation(
        decision=decision.decision,
        risk_score=decision.risk_score,
        latency_ms=eval_duration_ms,
        tool=action.tool,
        agent_id=ctx.get("agent_id"),
    )
    if decision.chain_pattern:
        gov_modules.metrics.record_chain_detection(decision.chain_pattern)
    if pii_findings:
        gov_modules.metrics.record_pii_findings(len(pii_findings))
```

### Step 6.2 — Mount compliance exporter

```python
from compliance_exporter import router as export_router
app.include_router(export_router, prefix="/compliance", tags=["compliance"])
```

**Deliverable:** `/metrics` returns Prometheus text format. `/compliance/report` and `/compliance/export/csv` live.

---

## Phase 7 — Gap Closure: DB Persistence for All Modules

**Goal:** Ensure no governance data is lost on restart.

### 7.1 — Fingerprinting persistence

Already covered in Phase 2 Step 2.4. Snapshot every 50 evals + restore on startup.

### 7.2 — SURGE v2 persistence

Already covered in Phase 3 Steps 3.3–3.4. Every receipt written to `surge_receipts_v2`. Chain restored on startup.

### 7.3 — Impact assessment persistence

Already covered in Phase 4 Step 4.4. Backfill from `action_logs` on startup — no new table needed.

### 7.4 — Budget enforcer persistence

Add to `governor_state` table (existing key-value store):

```python
# On budget change:
set_state(f"budget:{agent_id}:session_count", str(count))
set_state(f"budget:{agent_id}:hourly_count", str(count))

# On startup:
_restore_budget_state_from_db()
```

### 7.5 — SIEM dead-letter persistence

```python
class SiemDeadLetter(Base):
    """Failed SIEM dispatches for retry."""
    __tablename__ = "siem_dead_letters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_name: Mapped[str] = mapped_column(String(128), index=True)
    event_json: Mapped[str] = mapped_column(Text)
    error: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
```

**Deliverable:** Full persistence. No governance data lost on deploy/restart.

---

## Phase 8 — Gap Closure: Multi-Tenancy

**Goal:** Isolate data per tenant (organization). This is the biggest architectural change.

### 8.1 — Tenant model

```python
class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    plan: Mapped[str] = mapped_column(String(32), default="free")  # free | pro | enterprise
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    settings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

### 8.2 — Add tenant_id to all data tables

Add `tenant_id: Mapped[str]` column + index to:
- `action_logs`
- `policies`
- `surge_receipts_v2`
- `agent_fingerprint_snapshots`
- `escalation_events` / `escalation_configs`
- `trace_spans`
- `conversation_turns`
- `verification_logs`
- `users` (users belong to a tenant)

### 8.3 — Tenant middleware

```python
class TenantMiddleware:
    """Extract tenant_id from JWT claims or API key lookup.
    Sets request.state.tenant_id for all downstream handlers."""

    async def __call__(self, request, call_next):
        tenant_id = extract_tenant(request)  # from JWT 'org' claim or API key → tenant lookup
        request.state.tenant_id = tenant_id
        response = await call_next(request)
        return response
```

### 8.4 — Scoped queries

All DB queries filter by `tenant_id`:

```python
def db_session_scoped(tenant_id: str):
    """Returns a session with automatic tenant filtering."""
    # Use SQLAlchemy event listeners or a custom Session subclass
    # that appends WHERE tenant_id = :tid to every query
```

### 8.5 — Per-tenant module instances

Each tenant gets isolated module state:

```python
class TenantModules:
    """Per-tenant module instances — isolated fingerprints, budgets, SURGE chains."""
    _tenants: Dict[str, GovernorModules] = {}

    def get(self, tenant_id: str) -> GovernorModules:
        if tenant_id not in self._tenants:
            self._tenants[tenant_id] = _create_modules_for_tenant(tenant_id)
        return self._tenants[tenant_id]
```

**Deliverable:** Full tenant isolation. Each org sees only their data, policies, fingerprints, and SURGE chain.

---

## Phase 9 — Gap Closure: SDK / Agent Framework Integrations

**Goal:** Make it trivial for developers to add governance to their agents.

### 9.1 — Python SDK

Create `openclaw-sdk/` package:

```python
# Usage:
from openclaw import Governor

gov = Governor(api_url="https://your-governor.fly.dev", api_key="...")

# Wrap any tool call
result = gov.evaluate_and_run(
    tool="shell",
    args={"command": "ls -la"},
    agent_id="agent_001",
    session_id="sess_abc",
    run_fn=lambda: subprocess.run(["ls", "-la"]),
)
```

### 9.2 — LangChain integration

```python
from openclaw.langchain import GovernorCallbackHandler

# Add to any LangChain agent
agent = initialize_agent(
    tools=tools, llm=llm,
    callbacks=[GovernorCallbackHandler(governor_url=..., api_key=...)]
)
```

### 9.3 — CrewAI integration

```python
from openclaw.crewai import GovernorToolWrapper

# Wrap CrewAI tools
governed_tools = [GovernorToolWrapper(tool, governor=gov) for tool in crew_tools]
```

### 9.4 — TypeScript/JS SDK

```typescript
import { Governor } from '@openclaw/sdk';

const gov = new Governor({ apiUrl: '...', apiKey: '...' });
const decision = await gov.evaluate({ tool: 'shell', args: { command: 'rm -rf /' } });
```

**Deliverable:** `pip install openclaw-sdk`, `npm install @openclaw/sdk`. 3-line integration for LangChain, CrewAI, AutoGen.

---

## Phase 10 — Gap Closure: Pricing, SOC 2, SLAs

These are business/ops tasks, not engineering:

| Item | Owner | Timeline |
|---|---|---|
| **Pricing model** | Business — evaluate per-agent, per-evaluation, per-seat models. Recommend usage-based (per-evaluation) with free tier. | 2-3 weeks |
| **SOC 2 Type II** | Ops — engage audit firm. The SURGE v2 audit trail + RBAC + encryption at rest are strong foundations. | 3-6 months |
| **ISO 27001** | Ops — overlaps significantly with SOC 2. Run concurrently. | 4-8 months |
| **SLA definition** | Ops — define uptime targets (99.9%), response time guarantees (<50ms p99 for /evaluate), support tiers. | 2 weeks |
| **Terms of Service / DPA** | Legal — data processing agreement for GDPR, data residency options (SURGE v2 sovereign config). | 4-6 weeks |

---

## Implementation Timeline

| Phase | Scope | Effort | Dependencies |
|---|---|---|---|
| **Phase 1** | Compliance modules (PII, injection, budget, metrics) | 3-4 days | None |
| **Phase 2** | Agent fingerprinting | 2-3 days | Phase 1 (modules registry) |
| **Phase 3** | SURGE v2 | 3-4 days | Phase 1 (modules registry) |
| **Phase 4** | Impact assessment | 1-2 days | Phase 1 (modules registry) |
| **Phase 5** | Enterprise integrations (SIEM + escalation) | 2-3 days | Phase 3 (receipt IDs), Phase 2 (deviations) |
| **Phase 6** | Metrics wiring + compliance exporter | 1 day | Phases 1-5 |
| **Phase 7** | DB persistence for all modules | 3-4 days | Phases 1-5 |
| **Phase 8** | Multi-tenancy | 5-7 days | Phase 7 |
| **Phase 9** | SDKs (Python, JS, LangChain, CrewAI) | 5-7 days | Phases 1-6 stable |
| **Phase 10** | SOC 2, pricing, SLAs | Ongoing | Business/ops |

**Total engineering: ~25-35 days for Phases 1-9.**

Phases 1-6 can be done in parallel tracks (compliance + fingerprinting vs. SURGE v2 + impact).

---

## Files Modified Per Phase

| Phase | Files Created | Files Modified |
|---|---|---|
| 1 | `app/modules/__init__.py` | `config.py`, `main.py`, `policies/engine.py`, `api/routes_actions.py` |
| 2 | — | `main.py`, `policies/engine.py`, `routes_actions.py`, `schemas.py`, `models.py` |
| 3 | `models_v2.py` (or extend `models.py`) | `main.py`, `routes_actions.py`, `schemas.py` |
| 4 | — | `main.py`, `routes_actions.py` |
| 5 | — | `main.py`, `routes_actions.py` |
| 6 | — | `main.py`, `routes_actions.py` |
| 7 | — | `models.py`, `main.py`, module wrappers |
| 8 | `app/tenancy/` | Nearly all files (add tenant_id scoping) |
| 9 | `openclaw-sdk/` (new package) | None in governor-service |

---

*Ready to execute. Say "go" and specify which phase to start.*
