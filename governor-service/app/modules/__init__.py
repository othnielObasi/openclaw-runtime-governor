"""
GovernorModules — Central registry for all optional/compliance modules.

Lazily initializes each module on first access and exposes them as
properties.  The registry gracefully degrades: if a module directory is
missing or an import fails the property returns ``None`` so the core
evaluation pipeline never crashes.

On first access of persistence-backed modules (budget_enforcer,
fingerprint_engine, surge_engine, impact_engine) the registry:
  1. Instantiates the module
  2. Hydrates it from the DB (replaying state)
  3. Wires persistence callbacks so future state changes are saved

Usage
-----
    from app.modules import modules          # singleton

    if modules.injection_detector:
        result = modules.injection_detector.analyze(text)

    if modules.budget_enforcer:
        status = modules.budget_enforcer.check_budget(agent_id, session_id)
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    pass  # type stubs only

log = logging.getLogger("governor.modules")

# ---------------------------------------------------------------------------
# Ensure sibling module directories are importable
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[3]          # openclaw-runtime-governor/
_CONTAINER_MODULES = Path("/modules")                         # Docker container fallback
_MODULE_DIRS = [
    _PROJECT_ROOT / "compliance-modules",
    _PROJECT_ROOT / "agent-fingerprinting",
    _PROJECT_ROOT / "surge-v2",
    _PROJECT_ROOT / "integrations",
    _PROJECT_ROOT / "impact-assessment",
    # Container deployment paths (Dockerfile copies modules here)
    _CONTAINER_MODULES / "compliance-modules",
    _CONTAINER_MODULES / "agent-fingerprinting",
    _CONTAINER_MODULES / "surge-v2",
    _CONTAINER_MODULES / "integrations",
    _CONTAINER_MODULES / "impact-assessment",
]

for _d in _MODULE_DIRS:
    _str = str(_d)
    if _str not in sys.path and _d.is_dir():
        sys.path.insert(0, _str)
        log.debug("Added %s to sys.path", _str)


# ---------------------------------------------------------------------------
# Registry singleton
# ---------------------------------------------------------------------------

# ── DB-backed persistence helpers ──────────────────────────────────────────
# These functions connect module persistence hooks to SQLAlchemy models.
# They are called lazily when the module is first accessed.

def _hydrate_budget_enforcer(enforcer) -> None:
    """Wire budget enforcer to DB-backed circuit breaker persistence.

    - Circuit breaker state is persisted into GovernorState KV table.
    - On load, recent ActionLog rows are replayed to rebuild budget counters.
    """
    from ..database import db_session
    from ..models import GovernorState, ActionLog

    # 1. Provide circuit-breaker save/load callbacks
    def cb_save(agent_id: str, until: float, blocks: int):
        try:
            with db_session() as sess:
                key = f"cb:{agent_id}"
                row = sess.query(GovernorState).filter_by(key=key).first()
                payload = json.dumps({"until": until, "blocks": blocks})
                if row:
                    row.value = payload
                else:
                    sess.add(GovernorState(key=key, value=payload))
        except Exception as exc:
            log.warning("Budget CB save error (%s): %s", agent_id, exc)

    def cb_load(agent_id: str):
        try:
            with db_session() as sess:
                key = f"cb:{agent_id}"
                row = sess.query(GovernorState).filter_by(key=key).first()
                if row and row.value:
                    data = json.loads(row.value)
                    return (data["until"], data["blocks"])
        except Exception as exc:
            log.warning("Budget CB load error (%s): %s", agent_id, exc)
        return None

    enforcer.set_persistence(save_cb=cb_save, load_cb=cb_load)

    # 2. Replay recent ActionLog entries (last 24h) to rebuild evaluation counts
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        with db_session() as sess:
            rows = (
                sess.query(ActionLog)
                .filter(ActionLog.created_at >= cutoff)
                .order_by(ActionLog.created_at.asc())
                .all()
            )
            for row in rows:
                agent_id = row.agent_id or "anonymous"
                session_id = row.session_id or "default"
                enforcer.record_evaluation(
                    agent_id=agent_id,
                    session_id=session_id,
                    decision=row.decision,
                    cost=0.0,
                )
            enforcer.mark_hydrated()
            log.info("Budget enforcer hydrated — replayed %d recent evaluations", len(rows))
    except Exception as exc:
        log.warning("Budget enforcer hydration failed: %s", exc)
        enforcer.mark_hydrated()  # Mark anyway so it doesn't block


def _hydrate_fingerprint_engine(engine) -> None:
    """Wire fingerprint engine to DB persistence.

    - Loads all FingerprintState rows and imports them.
    - Sets a save callback that upserts into FingerprintState.
    """
    from ..database import db_session
    from ..models import FingerprintState

    # 1. Load existing states from DB
    try:
        with db_session() as sess:
            rows = sess.query(FingerprintState).all()
            if rows:
                states = {row.agent_id: row.state_json for row in rows}
                engine.import_states(states)
                log.info("Fingerprint engine hydrated — loaded %d agent profiles", len(rows))
    except Exception as exc:
        log.warning("Fingerprint hydration failed: %s", exc)

    # 2. Save callback: upsert FingerprintState on flush
    def fp_save(agent_id: str, state_json_str: str):
        try:
            with db_session() as sess:
                row = sess.query(FingerprintState).filter_by(agent_id=agent_id).first()
                # Extract metadata from JSON for indexed columns
                try:
                    data = json.loads(state_json_str)
                    total = data.get("total_evaluations", 0)
                    maturity = data.get("maturity", "learning")
                except Exception:
                    total, maturity = 0, "learning"

                if row:
                    row.state_json = state_json_str
                    row.total_evaluations = total
                    row.maturity = maturity
                    row.updated_at = datetime.now(timezone.utc)
                else:
                    sess.add(FingerprintState(
                        agent_id=agent_id,
                        state_json=state_json_str,
                        total_evaluations=total,
                        maturity=maturity,
                    ))
        except Exception as exc:
            log.warning("Fingerprint save error (%s): %s", agent_id, exc)

    engine.set_persistence(save_fn=fp_save, interval=10)


def _hydrate_surge_engine(engine) -> None:
    """Wire SURGE v2 engine to DB persistence.

    - Loads all SurgeV2Receipt and SurgeV2Checkpoint rows.
    - Calls load_chain() to rebuild hash chain state.
    - Sets callbacks for receipt/checkpoint insertion.
    """
    from ..database import db_session
    from ..models import SurgeV2Receipt, SurgeV2Checkpoint

    # 1. Load existing chain from DB
    try:
        with db_session() as sess:
            receipt_rows = (
                sess.query(SurgeV2Receipt)
                .order_by(SurgeV2Receipt.sequence.asc())
                .all()
            )
            checkpoint_rows = (
                sess.query(SurgeV2Checkpoint)
                .order_by(SurgeV2Checkpoint.sequence_start.asc())
                .all()
            )

            receipts = []
            for r in receipt_rows:
                receipts.append({
                    "receipt_id": r.receipt_id,
                    "sequence": r.sequence,
                    "timestamp": r.timestamp,
                    "tool": r.tool,
                    "decision": r.decision,
                    "risk_score": r.risk_score,
                    "explanation": r.explanation or "",
                    "policy_ids": json.loads(r.policy_ids_json) if r.policy_ids_json else [],
                    "chain_pattern": r.chain_pattern,
                    "agent_id": r.agent_id,
                    "session_id": r.session_id,
                    "sovereign": json.loads(r.sovereign_json) if r.sovereign_json else {},
                    "compliance": json.loads(r.compliance_json) if r.compliance_json else {},
                    "digest": r.digest,
                    "previous_digest": r.previous_digest,
                    "merkle_root": r.merkle_root,
                })

            checkpoints = []
            for c in checkpoint_rows:
                checkpoints.append({
                    "checkpoint_id": c.checkpoint_id,
                    "timestamp": c.timestamp,
                    "sequence_start": c.sequence_start,
                    "sequence_end": c.sequence_end,
                    "receipt_count": c.receipt_count,
                    "merkle_root": c.merkle_root,
                    "leaf_digests": json.loads(c.leaf_digests_json) if c.leaf_digests_json else [],
                })

            if receipts or checkpoints:
                engine.load_chain(receipts, checkpoints)
                log.info(
                    "SURGE v2 hydrated — loaded %d receipts, %d checkpoints",
                    len(receipts), len(checkpoints),
                )
    except Exception as exc:
        log.warning("SURGE v2 hydration failed: %s", exc)

    # 2. Persistence callbacks
    def on_receipt(receipt):
        try:
            with db_session() as sess:
                sess.add(SurgeV2Receipt(
                    receipt_id=receipt.receipt_id,
                    sequence=receipt.sequence,
                    timestamp=receipt.timestamp,
                    tool=receipt.tool,
                    decision=receipt.decision,
                    risk_score=receipt.risk_score,
                    explanation=receipt.explanation or "",
                    policy_ids_json=json.dumps(receipt.policy_ids or []),
                    chain_pattern=receipt.chain_pattern,
                    agent_id=receipt.agent_id,
                    session_id=receipt.session_id,
                    sovereign_json=json.dumps(receipt.sovereign or {}),
                    compliance_json=json.dumps(receipt.compliance or {}),
                    digest=receipt.digest,
                    previous_digest=receipt.previous_digest,
                    merkle_root=receipt.merkle_root,
                ))
        except Exception as exc:
            log.warning("SURGE receipt persist error: %s", exc)

    def on_checkpoint(cp):
        try:
            with db_session() as sess:
                sess.add(SurgeV2Checkpoint(
                    checkpoint_id=cp.checkpoint_id,
                    timestamp=cp.timestamp,
                    sequence_start=cp.sequence_start,
                    sequence_end=cp.sequence_end,
                    receipt_count=cp.receipt_count,
                    merkle_root=cp.merkle_root,
                    leaf_digests_json=json.dumps(cp.leaf_digests or []),
                ))
        except Exception as exc:
            log.warning("SURGE checkpoint persist error: %s", exc)

    engine.set_persistence(on_receipt=on_receipt, on_checkpoint=on_checkpoint)


def _hydrate_impact_engine(engine) -> None:
    """Wire impact engine to DB-backed query backend.

    Provides a function that queries ActionLog for a given assessment period,
    converting rows into EvaluationRecord objects.
    """
    from ..database import db_session
    from ..models import ActionLog

    def query_backend(period):
        """Query ActionLog for the given AssessmentPeriod, return EvaluationRecords."""
        # Import here to avoid circular dependency
        from impact_assessment import AssessmentPeriod, EvaluationRecord, PERIOD_SECONDS

        try:
            with db_session() as sess:
                q = sess.query(ActionLog)
                period_secs = PERIOD_SECONDS.get(period)
                if period_secs is not None:
                    cutoff = datetime.now(timezone.utc) - timedelta(seconds=period_secs)
                    q = q.filter(ActionLog.created_at >= cutoff)
                rows = q.order_by(ActionLog.created_at.asc()).all()

                records = []
                for r in rows:
                    records.append(EvaluationRecord(
                        timestamp=r.created_at.timestamp() if r.created_at else time.time(),
                        tool=r.tool or "unknown",
                        decision=r.decision or "allow",
                        risk_score=r.risk_score or 0,
                        agent_id=r.agent_id or "anonymous",
                        session_id=r.session_id or "default",
                        policy_ids=r.policy_ids.split(",") if r.policy_ids else [],
                        chain_pattern=r.chain_pattern,
                        explanation=r.explanation or "",
                    ))
                return records
        except Exception as exc:
            log.warning("Impact query backend error: %s", exc)
            return []

    engine.set_query_backend(query_backend)
    log.info("Impact assessment wired to DB query backend")


# ---------------------------------------------------------------------------
# Registry singleton
# ---------------------------------------------------------------------------

class GovernorModules:
    """Lazy-loading registry for every optional module."""

    def __init__(self) -> None:
        self._injection_detector: Any = _SENTINEL
        self._pii_scanner: Any = _SENTINEL
        self._budget_enforcer: Any = _SENTINEL
        self._metrics: Any = _SENTINEL
        self._metrics_router: Any = _SENTINEL
        self._compliance_exporter: Any = _SENTINEL
        self._compliance_router: Any = _SENTINEL
        self._fingerprint_engine: Any = _SENTINEL
        self._fingerprint_router: Any = _SENTINEL
        self._surge_engine: Any = _SENTINEL
        self._impact_engine: Any = _SENTINEL
        self._siem_dispatcher: Any = _SENTINEL
        self._escalation_connector: Any = _SENTINEL
        self._pii_router: Any = _SENTINEL

    # ── Compliance: Injection Detector ──────────────────────────────
    @property
    def injection_detector(self) -> Optional[Any]:
        if self._injection_detector is _SENTINEL:
            self._injection_detector = _load(
                "injection_detector",
                "SemanticInjectionDetector",
                "Semantic injection detector",
            )
        return self._injection_detector

    # ── Compliance: PII Scanner ─────────────────────────────────────
    @property
    def pii_scanner(self) -> Optional[Any]:
        if self._pii_scanner is _SENTINEL:
            self._pii_scanner = _load(
                "pii_scanner",
                "PIIScanner",
                "PII scanner",
            )
        return self._pii_scanner

    @property
    def pii_router(self) -> Optional[Any]:
        if self._pii_router is _SENTINEL:
            self._pii_router = _load_attr(
                "pii_scanner.router",
                "router",
                "PII scanner router",
            )
        return self._pii_router

    # ── Compliance: Budget Enforcer ─────────────────────────────────
    @property
    def budget_enforcer(self) -> Optional[Any]:
        if self._budget_enforcer is _SENTINEL:
            self._budget_enforcer = _load(
                "budget_enforcer",
                "BudgetEnforcer",
                "Budget enforcer",
            )
            if self._budget_enforcer is not None:
                try:
                    _hydrate_budget_enforcer(self._budget_enforcer)
                except Exception as exc:
                    log.warning("Budget enforcer hydration error: %s", exc)
        return self._budget_enforcer

    # ── Compliance: Metrics ─────────────────────────────────────────
    @property
    def metrics(self) -> Optional[Any]:
        if self._metrics is _SENTINEL:
            self._metrics = _load_attr(
                "metrics",
                "metrics",
                "Metrics singleton",
            )
        return self._metrics

    @property
    def metrics_router(self) -> Optional[Any]:
        if self._metrics_router is _SENTINEL:
            self._metrics_router = _load_attr(
                "metrics",
                "metrics_router",
                "Metrics router",
            )
        return self._metrics_router

    # ── Compliance: Compliance Exporter ─────────────────────────────
    @property
    def compliance_exporter(self) -> Optional[Any]:
        if self._compliance_exporter is _SENTINEL:
            self._compliance_exporter = _load(
                "compliance_exporter",
                "ComplianceExporter",
                "Compliance exporter",
            )
        return self._compliance_exporter

    @property
    def compliance_router(self) -> Optional[Any]:
        if self._compliance_router is _SENTINEL:
            self._compliance_router = _load_attr(
                "compliance_exporter",
                "router",
                "Compliance exporter router",
            )
        return self._compliance_router

    # ── Agent Fingerprinting ────────────────────────────────────────
    @property
    def fingerprint_engine(self) -> Optional[Any]:
        if self._fingerprint_engine is _SENTINEL:
            self._fingerprint_engine = _load(
                "fingerprinting",
                "FingerprintEngine",
                "Fingerprint engine",
            )
            if self._fingerprint_engine is not None:
                try:
                    _hydrate_fingerprint_engine(self._fingerprint_engine)
                except Exception as exc:
                    log.warning("Fingerprint hydration error: %s", exc)
        return self._fingerprint_engine

    @property
    def fingerprint_router(self) -> Optional[Any]:
        if self._fingerprint_router is _SENTINEL:
            self._fingerprint_router = _load_attr(
                "fingerprinting.router",
                "router",
                "Fingerprinting router",
            )
        return self._fingerprint_router

    # ── SURGE v2 ────────────────────────────────────────────────────
    @property
    def surge_engine(self) -> Optional[Any]:
        if self._surge_engine is _SENTINEL:
            try:
                from surge import SurgeEngine, SovereignConfig
                from ..config import settings as _s
                cfg = SovereignConfig(
                    deployment_id=_s.surge_v2_org,
                    jurisdiction="GB",
                    operator=_s.surge_v2_org,
                )
                self._surge_engine = SurgeEngine(
                    config=cfg,
                    checkpoint_interval=_s.surge_v2_checkpoint_interval,
                )
                log.info("✓ Loaded SURGE v2 engine (org=%s)", _s.surge_v2_org)
                try:
                    _hydrate_surge_engine(self._surge_engine)
                except Exception as exc:
                    log.warning("SURGE v2 hydration error: %s", exc)
            except Exception as exc:
                log.warning("✗ Could not load SURGE v2 engine: %s", exc)
                self._surge_engine = None
        return self._surge_engine

    @property
    def surge_router(self) -> Optional[Any]:
        if not hasattr(self, "_surge_router"):
            self._surge_router = _SENTINEL
        if self._surge_router is _SENTINEL:
            self._surge_router = _load_attr(
                "surge.router",
                "router",
                "SURGE v2 router",
            )
            # Inject the shared engine into the router module
            # Use self.surge_engine (property) instead of self._surge_engine
            # to ensure the engine is lazily initialised before we inject it.
            _engine = self.surge_engine
            if self._surge_router is not None and _engine is not None:
                try:
                    import surge.router as _sr
                    _sr.set_engine(_engine)
                    log.info("Injected shared SURGE engine into router")
                except Exception as exc:
                    log.warning("Could not inject SURGE engine into router: %s", exc)
        return self._surge_router

    # ── Impact Assessment ───────────────────────────────────────────
    @property
    def impact_engine(self) -> Optional[Any]:
        if self._impact_engine is _SENTINEL:
            self._impact_engine = _load(
                "impact_assessment",
                "ImpactAssessmentEngine",
                "Impact assessment engine",
            )
            if self._impact_engine is not None:
                try:
                    _hydrate_impact_engine(self._impact_engine)
                except Exception as exc:
                    log.warning("Impact engine hydration error: %s", exc)
        return self._impact_engine

    @property
    def impact_router(self) -> Optional[Any]:
        if not hasattr(self, "_impact_router"):
            self._impact_router = _SENTINEL
        if self._impact_router is _SENTINEL:
            self._impact_router = _load_attr(
                "impact_assessment.router",
                "router",
                "Impact assessment router",
            )
            # Inject the shared engine into the router module
            if self._impact_router is not None and self._impact_engine is not _SENTINEL and self._impact_engine is not None:
                try:
                    import impact_assessment.router as _ir
                    _ir.engine = self._impact_engine
                    log.info("Injected shared impact engine into router")
                except Exception as exc:
                    log.warning("Could not inject impact engine into router: %s", exc)
        return self._impact_router

    # ── Integrations: SIEM ──────────────────────────────────────────
    @property
    def siem_dispatcher(self) -> Optional[Any]:
        if self._siem_dispatcher is _SENTINEL:
            self._siem_dispatcher = _load(
                "siem_webhook",
                "SiemDispatcher",
                "SIEM dispatcher",
            )
        return self._siem_dispatcher

    # ── Integrations: Escalation ────────────────────────────────────
    @property
    def escalation_connector(self) -> Optional[Any]:
        if self._escalation_connector is _SENTINEL:
            self._escalation_connector = _load(
                "escalation",
                "EscalationRouter",
                "Escalation connector",
            )
        return self._escalation_connector

    # ── Convenience ─────────────────────────────────────────────────
    def status(self) -> dict:
        """Return a dict of module name → loaded boolean for diagnostics."""
        return {
            "injection_detector": self.injection_detector is not None,
            "pii_scanner": self.pii_scanner is not None,
            "budget_enforcer": self.budget_enforcer is not None,
            "metrics": self.metrics is not None,
            "compliance_exporter": self.compliance_exporter is not None,
            "fingerprint_engine": self.fingerprint_engine is not None,
            "surge_engine": self.surge_engine is not None,
            "impact_engine": self.impact_engine is not None,
            "siem_dispatcher": self.siem_dispatcher is not None,
            "escalation_connector": self.escalation_connector is not None,
            "surge_router": self.surge_router is not None,
            "impact_router": self.impact_router is not None,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SENTINEL = object()


def _load(module_name: str, class_name: str, label: str) -> Optional[Any]:
    """Import *module_name* and instantiate *class_name* with defaults."""
    try:
        mod = __import__(module_name, fromlist=[class_name])
        cls = getattr(mod, class_name)
        instance = cls()
        log.info("✓ Loaded %s (%s.%s)", label, module_name, class_name)
        return instance
    except Exception as exc:
        log.warning("✗ Could not load %s: %s", label, exc)
        return None


def _load_attr(module_name: str, attr_name: str, label: str) -> Optional[Any]:
    """Import *module_name* and return a module-level attribute (no instantiation)."""
    try:
        mod = __import__(module_name, fromlist=[attr_name])
        obj = getattr(mod, attr_name)
        log.info("✓ Loaded %s (%s.%s)", label, module_name, attr_name)
        return obj
    except Exception as exc:
        log.warning("✗ Could not load %s: %s", label, exc)
        return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
modules = GovernorModules()
