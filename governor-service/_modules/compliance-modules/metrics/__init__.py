"""
NOVTIA Governor — Prometheus Metrics
======================================
Standard /metrics endpoint for Prometheus scraping.
Zero dependency — generates Prometheus text format directly.

Integration:
    from metrics import GovernorMetrics, metrics_router
    app.include_router(metrics_router)

    # In your evaluation pipeline:
    metrics.record_evaluation("allow", latency_ms=12.5, tool="shell")
    metrics.record_chain_detection("credential-then-http")
    metrics.record_pii_finding("email", "input")
"""
from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List, Optional
from fastapi import APIRouter


class GovernorMetrics:
    """
    Collects and exposes Prometheus-compatible metrics.
    No external dependency — generates text format directly.
    """

    def __init__(self):
        self._lock = Lock()

        # Counters
        self._evaluations_total: Dict[str, int] = defaultdict(int)      # by decision
        self._evaluations_by_tool: Dict[str, int] = defaultdict(int)    # by tool
        self._policy_violations: Dict[str, int] = defaultdict(int)      # by policy_id
        self._chain_detections: Dict[str, int] = defaultdict(int)       # by pattern
        self._pii_findings: Dict[str, int] = defaultdict(int)           # by entity_type
        self._injection_detections: Dict[str, int] = defaultdict(int)   # by category
        self._budget_exceeded: Dict[str, int] = defaultdict(int)        # by reason_type
        self._verification_verdicts: Dict[str, int] = defaultdict(int)  # by verdict
        self._errors_total: Dict[str, int] = defaultdict(int)           # by error_type
        self._kill_switch_activations: int = 0

        # Histogram buckets for latency
        self._latency_buckets = [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
        self._latency_counts: Dict[str, int] = {str(b): 0 for b in self._latency_buckets}
        self._latency_counts["+Inf"] = 0
        self._latency_sum: float = 0.0
        self._latency_count: int = 0

        # Gauges
        self._active_agents: int = 0
        self._kill_switch_engaged: int = 0
        self._active_policies: int = 0
        self._active_sessions: int = 0

        # Startup time
        self._start_time = time.time()

    # ─── Recording Methods ───

    def record_evaluation(self, decision: str, latency_ms: float = 0.0,
                          tool: str = "unknown", policy_ids: Optional[List[str]] = None):
        """Record an evaluation result."""
        with self._lock:
            self._evaluations_total[decision] += 1
            self._evaluations_by_tool[tool] += 1

            # Latency histogram
            self._latency_sum += latency_ms
            self._latency_count += 1
            for bucket in self._latency_buckets:
                if latency_ms <= bucket:
                    self._latency_counts[str(bucket)] += 1
            self._latency_counts["+Inf"] += 1

            # Policy violations
            if policy_ids and decision == "block":
                for pid in policy_ids:
                    self._policy_violations[pid] += 1

    def record_chain_detection(self, pattern: str):
        with self._lock:
            self._chain_detections[pattern] += 1

    def record_pii_finding(self, entity_type: str, direction: str):
        with self._lock:
            self._pii_findings[f"{entity_type}_{direction}"] += 1

    def record_injection_detection(self, category: str):
        with self._lock:
            self._injection_detections[category] += 1

    def record_budget_exceeded(self, reason_type: str):
        with self._lock:
            self._budget_exceeded[reason_type] += 1

    def record_verification(self, verdict: str):
        with self._lock:
            self._verification_verdicts[verdict] += 1

    def record_error(self, error_type: str):
        with self._lock:
            self._errors_total[error_type] += 1

    def record_kill_switch(self, engaged: bool):
        with self._lock:
            self._kill_switch_engaged = 1 if engaged else 0
            if engaged:
                self._kill_switch_activations += 1

    def set_active_agents(self, count: int):
        with self._lock:
            self._active_agents = count

    def set_active_policies(self, count: int):
        with self._lock:
            self._active_policies = count

    def set_active_sessions(self, count: int):
        with self._lock:
            self._active_sessions = count

    # ─── Prometheus Export ───

    def export(self) -> str:
        """Generate Prometheus text exposition format."""
        with self._lock:
            lines = []

            def _sanitize_label(v: str) -> str:
                """Escape Prometheus label value: backslash, double-quote, newline."""
                return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

            def counter(name: str, help_text: str, labels_values: Dict[str, int], label_name: str = "type"):
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} counter")
                for label, value in sorted(labels_values.items()):
                    lines.append(f'{name}{{{label_name}="{_sanitize_label(label)}"}} {value}')

            def gauge(name: str, help_text: str, value):
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {value}")

            # Counters
            counter("governor_evaluations_total",
                    "Total evaluations by decision", self._evaluations_total, "decision")

            counter("governor_evaluations_by_tool_total",
                    "Total evaluations by tool name", self._evaluations_by_tool, "tool")

            counter("governor_policy_violations_total",
                    "Policy violations by policy ID", self._policy_violations, "policy_id")

            counter("governor_chain_detections_total",
                    "Chain analysis detections by pattern", self._chain_detections, "pattern")

            counter("governor_pii_findings_total",
                    "PII findings by entity type and direction", self._pii_findings, "entity")

            counter("governor_injection_detections_total",
                    "Injection detections by category", self._injection_detections, "category")

            counter("governor_budget_exceeded_total",
                    "Budget exceeded events by reason", self._budget_exceeded, "reason")

            counter("governor_verification_verdicts_total",
                    "Verification verdicts", self._verification_verdicts, "verdict")

            counter("governor_errors_total",
                    "Errors by type", self._errors_total, "error_type")

            # Kill switch activations
            lines.append("# HELP governor_kill_switch_activations_total Total kill switch activations")
            lines.append("# TYPE governor_kill_switch_activations_total counter")
            lines.append(f"governor_kill_switch_activations_total {self._kill_switch_activations}")

            # Latency histogram
            # NOTE: record_evaluation() stores cumulative counts — each bucket
            # holds the number of observations <= that bucket threshold.
            # We output them directly (no running sum needed).
            lines.append("# HELP governor_evaluation_latency_ms Evaluation latency in milliseconds")
            lines.append("# TYPE governor_evaluation_latency_ms histogram")
            for bucket in self._latency_buckets:
                lines.append(f'governor_evaluation_latency_ms_bucket{{le="{bucket}"}} {self._latency_counts.get(str(bucket), 0)}')
            lines.append(f'governor_evaluation_latency_ms_bucket{{le="+Inf"}} {self._latency_count}')
            lines.append(f"governor_evaluation_latency_ms_sum {self._latency_sum:.2f}")
            lines.append(f"governor_evaluation_latency_ms_count {self._latency_count}")

            # Gauges
            gauge("governor_active_agents", "Number of active agents", self._active_agents)
            gauge("governor_kill_switch_engaged", "Kill switch status (1=engaged)", self._kill_switch_engaged)
            gauge("governor_active_policies", "Number of active policies", self._active_policies)
            gauge("governor_active_sessions", "Number of active sessions", self._active_sessions)
            gauge("governor_uptime_seconds", "Time since startup", f"{time.time() - self._start_time:.0f}")

            return "\n".join(lines) + "\n"

    def summary(self) -> Dict:
        """Get metrics summary as dict (for JSON endpoints)."""
        with self._lock:
            total_evals = sum(self._evaluations_total.values())
            return {
                "evaluations_total": total_evals,
                "evaluations_by_decision": dict(self._evaluations_total),
                "evaluations_by_tool": dict(self._evaluations_by_tool),
                "avg_latency_ms": round(self._latency_sum / self._latency_count, 2) if self._latency_count > 0 else 0,
                "chain_detections": dict(self._chain_detections),
                "pii_findings": dict(self._pii_findings),
                "injection_detections": dict(self._injection_detections),
                "kill_switch_engaged": bool(self._kill_switch_engaged),
                "uptime_seconds": int(time.time() - self._start_time),
            }


# ─── Singleton + Router ───

metrics = GovernorMetrics()
metrics_router = APIRouter(tags=["Metrics"])


@metrics_router.get("/metrics", response_class=None)
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint."""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=metrics.export(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@metrics_router.get("/metrics/summary")
async def metrics_summary():
    """JSON metrics summary."""
    return metrics.summary()
