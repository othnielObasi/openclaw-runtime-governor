"""
GovernorModules — Central registry for all optional/compliance modules.

Lazily initializes each module on first access and exposes them as
properties.  The registry gracefully degrades: if a module directory is
missing or an import fails the property returns ``None`` so the core
evaluation pipeline never crashes.

Usage
-----
    from app.modules import modules          # singleton

    if modules.injection_detector:
        result = modules.injection_detector.analyze(text)

    if modules.budget_enforcer:
        status = modules.budget_enforcer.check_budget(agent_id, session_id)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

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
            if self._surge_router is not None and self._surge_engine is not _SENTINEL and self._surge_engine is not None:
                try:
                    import surge.router as _sr
                    _sr.set_engine(self._surge_engine)
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
