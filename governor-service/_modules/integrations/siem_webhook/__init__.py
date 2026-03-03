"""
NOVTIA Governor — SIEM Webhook Integration
============================================
Pushes governance events to external security systems in real-time.

Supported targets:
  - Splunk HTTP Event Collector (HEC)
  - Elastic Common Schema (ECS) via webhook
  - Microsoft Sentinel via Log Analytics Data Collector API
  - Generic webhook (any HTTP endpoint accepting JSON POST)
  - Syslog (RFC 5424 over TCP/UDP)

Architecture:
  Evaluation completes → event queued → background worker batches
  and delivers → retry on failure → dead letter after max retries.

Integration:
    from siem_webhook import SiemDispatcher, SiemTarget, SiemConfig

    dispatcher = SiemDispatcher()
    dispatcher.add_target(SiemTarget(
        name="splunk_prod",
        target_type="splunk_hec",
        url="https://splunk.corp.com:8088/services/collector",
        auth_token="your-hec-token",
    ))

    # After every evaluation:
    dispatcher.dispatch(event)

    # Graceful shutdown:
    dispatcher.flush()
"""
from __future__ import annotations

import json
import hashlib
import logging
import queue
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger("novtia.siem")


# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

class TargetType(str, Enum):
    SPLUNK_HEC = "splunk_hec"
    ELASTIC = "elastic"
    SENTINEL = "sentinel"
    GENERIC_WEBHOOK = "generic_webhook"
    SYSLOG = "syslog"


class EventSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SiemTarget:
    """Configuration for a single SIEM target."""
    name: str
    target_type: str                         # splunk_hec | elastic | sentinel | generic_webhook | syslog
    url: str = ""                            # HTTP endpoint URL
    auth_token: str = ""                     # Bearer token / HEC token / API key
    auth_header: str = "Authorization"       # Header name for auth
    auth_prefix: str = "Bearer"              # Prefix (e.g., "Splunk" for HEC, "Bearer" for generic)

    # Syslog-specific
    syslog_host: str = ""
    syslog_port: int = 514
    syslog_protocol: str = "tcp"             # tcp | udp
    syslog_facility: int = 1                 # user-level

    # Filtering
    min_severity: str = "low"                # Only send events at or above this severity
    decision_filter: Optional[Set[str]] = None  # None = all, or {"block", "review"}
    enabled: bool = True

    # Batching
    batch_size: int = 10                     # Flush after N events
    flush_interval_seconds: float = 5.0      # Flush at least every N seconds

    # Retry
    max_retries: int = 3
    retry_delay_seconds: float = 2.0

    # Custom headers
    extra_headers: Dict[str, str] = field(default_factory=dict)

    # Splunk-specific
    splunk_index: str = "main"
    splunk_source: str = "novtia_governor"
    splunk_sourcetype: str = "novtia:governance"

    # Elastic-specific
    elastic_index: str = "novtia-governance"

    # Sentinel-specific
    sentinel_workspace_id: str = ""
    sentinel_log_type: str = "NovtiaGovernance"


@dataclass
class GovernanceEvent:
    """A governance event to be dispatched to SIEM targets."""
    event_id: str
    timestamp: str                           # ISO-8601
    event_type: str                          # evaluation | kill_switch | policy_change | escalation
    tool: str
    decision: str                            # allow | block | review
    risk_score: int
    explanation: str
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    policy_ids: List[str] = field(default_factory=list)
    chain_pattern: Optional[str] = None
    execution_trace: List[Dict[str, Any]] = field(default_factory=list)

    # SURGE receipt reference
    surge_receipt_id: Optional[str] = None
    surge_digest: Optional[str] = None

    # Fingerprint deviations
    deviations: List[Dict[str, Any]] = field(default_factory=list)

    # Sovereign context
    deployment_id: str = ""
    jurisdiction: str = ""

    # Computed
    severity: str = "low"                    # low | medium | high | critical

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "tool": self.tool,
            "decision": self.decision,
            "risk_score": self.risk_score,
            "explanation": self.explanation,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "policy_ids": self.policy_ids,
            "chain_pattern": self.chain_pattern,
            "execution_trace": self.execution_trace,
            "surge_receipt_id": self.surge_receipt_id,
            "surge_digest": self.surge_digest,
            "deviations": self.deviations,
            "deployment_id": self.deployment_id,
            "jurisdiction": self.jurisdiction,
            "severity": self.severity,
        }


def compute_severity(decision: str, risk_score: int, chain_pattern: Optional[str],
                     deviations: List) -> str:
    """Compute event severity from governance decision attributes."""
    if decision == "block" and risk_score >= 80:
        return "critical"
    if decision == "block" or chain_pattern or len(deviations) >= 2:
        return "high"
    if decision == "review" or risk_score >= 50 or deviations:
        return "medium"
    return "low"


SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


# ═══════════════════════════════════════════════════════════
# EVENT FORMATTERS
# ═══════════════════════════════════════════════════════════

def _format_splunk_hec(event: GovernanceEvent, target: SiemTarget) -> Dict[str, Any]:
    """Format event for Splunk HTTP Event Collector."""
    return {
        "time": _iso_to_epoch(event.timestamp),
        "host": event.deployment_id or "novtia-governor",
        "source": target.splunk_source,
        "sourcetype": target.splunk_sourcetype,
        "index": target.splunk_index,
        "event": event.to_dict(),
    }


def _format_elastic_ecs(event: GovernanceEvent, target: SiemTarget) -> Dict[str, Any]:
    """Format event as Elastic Common Schema (ECS)."""
    return {
        "@timestamp": event.timestamp,
        "event": {
            "kind": "alert" if event.decision == "block" else "event",
            "category": ["intrusion_detection"],
            "type": ["info"] if event.decision == "allow" else ["denied"],
            "severity": SEVERITY_ORDER.get(event.severity, 0) * 25,
            "module": "novtia_governor",
            "dataset": "novtia.governance",
            "id": event.event_id,
            "outcome": "failure" if event.decision == "block" else "success",
        },
        "rule": {
            "id": ",".join(event.policy_ids) if event.policy_ids else None,
            "description": event.explanation,
        },
        "threat": {
            "technique": {"name": event.chain_pattern} if event.chain_pattern else None,
        },
        "agent": {"id": event.agent_id, "type": "ai_agent"},
        "novtia": event.to_dict(),
    }


def _format_sentinel(event: GovernanceEvent, target: SiemTarget) -> Dict[str, Any]:
    """Format for Microsoft Sentinel Log Analytics."""
    d = event.to_dict()
    d["TimeGenerated"] = event.timestamp
    d["Severity"] = event.severity.upper()
    return d


def _format_generic(event: GovernanceEvent, target: SiemTarget) -> Dict[str, Any]:
    """Generic JSON format."""
    return event.to_dict()


def _format_syslog_cef(event: GovernanceEvent, target: SiemTarget) -> str:
    """Format as CEF (Common Event Format) for syslog."""
    severity_map = {"low": 2, "medium": 5, "high": 7, "critical": 10}
    sev = severity_map.get(event.severity, 3)

    extension = (
        f"act={event.decision} "
        f"risk={event.risk_score} "
        f"msg={_cef_escape(event.explanation[:200])} "
        f"cs1={event.tool} cs1Label=Tool "
        f"cs2={event.agent_id or 'unknown'} cs2Label=AgentID "
        f"cs3={event.surge_receipt_id or ''} cs3Label=SurgeReceiptID"
    )

    if event.chain_pattern:
        extension += f" cs4={event.chain_pattern} cs4Label=ChainPattern"

    return (
        f"CEF:0|NOVTIA|Governor|1.0|{event.event_type}|"
        f"{event.decision.upper()} {event.tool}|{sev}|{extension}"
    )


def _cef_escape(s: str) -> str:
    """Escape special characters for CEF format."""
    return s.replace("\\", "\\\\").replace("=", "\\=").replace("|", "\\|").replace("\n", " ")


def _iso_to_epoch(ts: str) -> float:
    """Convert ISO-8601 timestamp to epoch seconds."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, AttributeError):
        return time.time()


FORMATTERS = {
    "splunk_hec": _format_splunk_hec,
    "elastic": _format_elastic_ecs,
    "sentinel": _format_sentinel,
    "generic_webhook": _format_generic,
    "syslog": _format_syslog_cef,
}


# ═══════════════════════════════════════════════════════════
# HTTP TRANSPORT (pluggable)
# ═══════════════════════════════════════════════════════════

class HttpTransport:
    """
    Pluggable HTTP transport. Default uses urllib (stdlib).
    Replace with httpx/aiohttp in production for async.
    """

    def post(self, url: str, headers: Dict[str, str],
             body: str, timeout: float = 10.0) -> 'HttpResponse':
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


@dataclass
class HttpResponse:
    status: int
    body: str = ""
    error: bool = False

    @property
    def success(self) -> bool:
        return 200 <= self.status < 300


class MockTransport:
    """For testing — records all dispatched events."""

    def __init__(self):
        self.sent: List[Dict[str, Any]] = []
        self.fail_next: int = 0  # Fail the next N requests

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
# SYSLOG TRANSPORT
# ═══════════════════════════════════════════════════════════

class SyslogTransport:
    """Send CEF-formatted events over TCP or UDP syslog."""

    def send(self, message: str, host: str, port: int,
             protocol: str = "tcp", facility: int = 1) -> bool:
        try:
            # RFC 5424 priority = facility * 8 + severity (6 = informational)
            pri = facility * 8 + 6
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            syslog_msg = f"<{pri}>1 {timestamp} novtia-governor - - - {message}"

            if protocol == "udp":
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.sendto(syslog_msg.encode("utf-8"), (host, port))
            else:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(5.0)
                    sock.connect((host, port))
                    sock.sendall((syslog_msg + "\n").encode("utf-8"))
            return True
        except Exception as e:
            logger.error(f"Syslog send failed: {e}")
            return False


# ═══════════════════════════════════════════════════════════
# DISPATCHER
# ═══════════════════════════════════════════════════════════

@dataclass
class DeliveryResult:
    target_name: str
    success: bool
    status_code: int = 0
    events_sent: int = 0
    error: str = ""
    retries_used: int = 0


@dataclass
class DispatcherStats:
    total_dispatched: int = 0
    total_delivered: int = 0
    total_failed: int = 0
    total_filtered: int = 0
    total_retries: int = 0
    dead_letter_count: int = 0
    targets_active: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_dispatched": self.total_dispatched,
            "total_delivered": self.total_delivered,
            "total_failed": self.total_failed,
            "total_filtered": self.total_filtered,
            "total_retries": self.total_retries,
            "dead_letter_count": self.dead_letter_count,
            "targets_active": self.targets_active,
        }


class SiemDispatcher:
    """
    Dispatches governance events to one or more SIEM targets.

    Supports batching, retry with backoff, filtering by severity
    and decision type, and dead-letter queue for failed deliveries.

    Usage:
        dispatcher = SiemDispatcher()
        dispatcher.add_target(SiemTarget(name="splunk", ...))
        dispatcher.dispatch(event)
        dispatcher.flush()  # on shutdown
    """

    def __init__(
        self,
        transport: Optional[HttpTransport] = None,
        syslog_transport: Optional[SyslogTransport] = None,
        max_queue_size: int = 10000,
    ):
        self._targets: Dict[str, SiemTarget] = {}
        self._transport = transport or HttpTransport()
        self._syslog = syslog_transport or SyslogTransport()
        self._stats = DispatcherStats()
        self._dead_letter: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

        # Per-target batching queues
        self._queues: Dict[str, List[GovernanceEvent]] = {}
        self._last_flush: Dict[str, float] = {}

    def add_target(self, target: SiemTarget):
        """Register a SIEM target."""
        with self._lock:
            self._targets[target.name] = target
            self._queues[target.name] = []
            self._last_flush[target.name] = time.time()
            self._stats.targets_active = len([t for t in self._targets.values() if t.enabled])

    def remove_target(self, name: str):
        """Remove a SIEM target."""
        with self._lock:
            if name in self._targets:
                # Flush remaining events
                self._flush_target(name)
                del self._targets[name]
                del self._queues[name]
                del self._last_flush[name]
                self._stats.targets_active = len([t for t in self._targets.values() if t.enabled])

    def dispatch(self, event: GovernanceEvent) -> List[DeliveryResult]:
        """
        Dispatch an event to all registered targets.
        Events are queued and batched per target configuration.
        Returns delivery results for any targets that flushed.

        The lock is released before network I/O to avoid blocking
        other dispatches during slow deliveries.
        """
        self._stats.total_dispatched += 1
        results = []
        flush_jobs = []  # (target_copy, events_copy, formatter)

        with self._lock:
            for name, target in self._targets.items():
                if not target.enabled:
                    continue

                # Filter by severity
                if SEVERITY_ORDER.get(event.severity, 0) < SEVERITY_ORDER.get(target.min_severity, 0):
                    self._stats.total_filtered += 1
                    continue

                # Filter by decision
                if target.decision_filter and event.decision not in target.decision_filter:
                    self._stats.total_filtered += 1
                    continue

                # Queue the event
                self._queues[name].append(event)

                # Check if we should flush
                should_flush = (
                    len(self._queues[name]) >= target.batch_size or
                    (time.time() - self._last_flush[name]) >= target.flush_interval_seconds
                )

                if should_flush:
                    # Snapshot and drain queue while holding lock
                    events = self._queues[name][:]
                    self._queues[name] = []
                    self._last_flush[name] = time.time()
                    formatter = FORMATTERS.get(target.target_type, _format_generic)
                    flush_jobs.append((target, events, formatter))

        # Deliver OUTSIDE the lock so other dispatches aren't blocked
        for target, events, formatter in flush_jobs:
            try:
                if target.target_type == "syslog":
                    result = self._deliver_syslog(target, events, formatter)
                else:
                    result = self._deliver_http(target, events, formatter)
                if result:
                    results.append(result)
            except Exception:
                pass  # already handled inside deliver methods

        return results

    def _flush_target(self, name: str) -> Optional[DeliveryResult]:
        """Flush queued events for a specific target. Caller holds lock."""
        target = self._targets.get(name)
        if not target or not self._queues.get(name):
            return None

        events = self._queues[name][:]
        self._queues[name] = []
        self._last_flush[name] = time.time()

        # Format events
        formatter = FORMATTERS.get(target.target_type, _format_generic)

        if target.target_type == "syslog":
            return self._deliver_syslog(target, events, formatter)
        else:
            return self._deliver_http(target, events, formatter)

    def _deliver_http(self, target: SiemTarget, events: List[GovernanceEvent],
                      formatter) -> DeliveryResult:
        """Deliver events via HTTP with retry."""
        # Format all events
        formatted = [formatter(e, target) for e in events]

        # Build request body
        if target.target_type == "splunk_hec":
            # Splunk HEC accepts newline-delimited JSON
            body = "\n".join(json.dumps(f) for f in formatted)
        else:
            body = json.dumps(formatted if len(formatted) > 1 else formatted[0])

        # Build headers
        headers = {
            "Content-Type": "application/json",
            **target.extra_headers,
        }

        if target.auth_token:
            if target.target_type == "splunk_hec":
                headers["Authorization"] = f"Splunk {target.auth_token}"
            else:
                headers[target.auth_header] = f"{target.auth_prefix} {target.auth_token}"

        # Deliver with retry
        retries = 0
        last_error = ""

        for attempt in range(target.max_retries + 1):
            resp = self._transport.post(target.url, headers, body)

            if resp.success:
                self._stats.total_delivered += len(events)
                return DeliveryResult(
                    target_name=target.name, success=True,
                    status_code=resp.status, events_sent=len(events),
                    retries_used=retries,
                )

            last_error = f"HTTP {resp.status}: {resp.body[:200]}"
            retries += 1
            self._stats.total_retries += 1

            if attempt < target.max_retries:
                time.sleep(target.retry_delay_seconds * (attempt + 1))

        # All retries exhausted — dead letter
        self._stats.total_failed += len(events)
        for event in events:
            self._dead_letter.append({
                "event": event.to_dict(),
                "target": target.name,
                "error": last_error,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "retries": retries,
            })
        self._stats.dead_letter_count = len(self._dead_letter)

        return DeliveryResult(
            target_name=target.name, success=False,
            events_sent=0, error=last_error,
            retries_used=retries,
        )

    def _deliver_syslog(self, target: SiemTarget, events: List[GovernanceEvent],
                        formatter) -> DeliveryResult:
        """Deliver events via syslog."""
        sent = 0
        last_error = ""

        for event in events:
            cef_msg = formatter(event, target)
            success = self._syslog.send(
                cef_msg, target.syslog_host, target.syslog_port,
                target.syslog_protocol, target.syslog_facility,
            )
            if success:
                sent += 1
            else:
                last_error = f"Syslog send failed to {target.syslog_host}:{target.syslog_port}"

        if sent == len(events):
            self._stats.total_delivered += sent
            return DeliveryResult(target_name=target.name, success=True, events_sent=sent)
        else:
            self._stats.total_failed += (len(events) - sent)
            self._stats.total_delivered += sent
            return DeliveryResult(
                target_name=target.name, success=False,
                events_sent=sent, error=last_error,
            )

    def flush(self) -> List[DeliveryResult]:
        """Flush all targets. Call on shutdown."""
        results = []
        with self._lock:
            for name in list(self._targets.keys()):
                result = self._flush_target(name)
                if result:
                    results.append(result)
        return results

    # ─── Query ───

    @property
    def stats(self) -> DispatcherStats:
        return self._stats

    def get_dead_letter(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get failed events from dead letter queue."""
        return self._dead_letter[-limit:]

    def clear_dead_letter(self):
        """Clear the dead letter queue."""
        self._dead_letter.clear()
        self._stats.dead_letter_count = 0

    def list_targets(self) -> List[Dict[str, Any]]:
        """List all registered targets."""
        return [
            {
                "name": t.name,
                "type": t.target_type,
                "enabled": t.enabled,
                "url": t.url[:50] + "..." if len(t.url) > 50 else t.url,
                "min_severity": t.min_severity,
                "decision_filter": list(t.decision_filter) if t.decision_filter else "all",
                "batch_size": t.batch_size,
                "queue_depth": len(self._queues.get(t.name, [])),
            }
            for t in self._targets.values()
        ]


# ═══════════════════════════════════════════════════════════
# HELPER: Create event from ActionDecision
# ═══════════════════════════════════════════════════════════

def event_from_evaluation(
    tool: str,
    decision: str,
    risk_score: int,
    explanation: str,
    policy_ids: List[str],
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    chain_pattern: Optional[str] = None,
    execution_trace: Optional[List[Dict]] = None,
    surge_receipt_id: Optional[str] = None,
    surge_digest: Optional[str] = None,
    deviations: Optional[List[Dict]] = None,
    deployment_id: str = "",
    jurisdiction: str = "",
) -> GovernanceEvent:
    """Create a GovernanceEvent from evaluation result fields."""
    devs = deviations or []
    severity = compute_severity(decision, risk_score, chain_pattern, devs)

    return GovernanceEvent(
        event_id=f"evt-{uuid4().hex[:16]}",
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type="evaluation",
        tool=tool,
        decision=decision,
        risk_score=risk_score,
        explanation=explanation,
        agent_id=agent_id,
        session_id=session_id,
        policy_ids=policy_ids,
        chain_pattern=chain_pattern,
        execution_trace=execution_trace or [],
        surge_receipt_id=surge_receipt_id,
        surge_digest=surge_digest,
        deviations=devs,
        deployment_id=deployment_id,
        jurisdiction=jurisdiction,
        severity=severity,
    )
