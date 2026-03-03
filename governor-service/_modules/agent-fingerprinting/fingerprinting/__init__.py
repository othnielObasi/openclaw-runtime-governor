"""
NOVTIA Governor — Agent Behavioural Fingerprinting
====================================================
Learns per-agent tool-call baselines from production data.
Detects statistical deviations that no static rule can catch.
Compounds over time — the more data, the smarter the detection.

This is the moat. Competitors can copy policies. They can't copy
months of accumulated behavioural data.

Integration:
    from fingerprinting import FingerprintEngine, Deviation
    engine = FingerprintEngine()

    # Record every evaluation (background, non-blocking)
    engine.record("agent_001", tool="shell", args={"command": "ls"},
                  decision="allow", risk_score=10, latency_ms=12)

    # Check before evaluation — does this look normal for this agent?
    deviations = engine.check("agent_001", tool="http_post",
                              args={"url": "https://evil.com"})
    if deviations:
        risk_boost = sum(d.severity for d in deviations)
"""
from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ═══════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════

@dataclass
class Deviation:
    """A single behavioural deviation from an agent's fingerprint."""
    deviation_type: str       # e.g., "novel_tool", "frequency_spike", "arg_anomaly"
    description: str          # Human-readable explanation
    severity: float           # 0-50 risk boost
    confidence: float         # 0.0-1.0 — how confident we are this is anomalous
    expected: Any = None      # What we expected
    observed: Any = None      # What we got
    fingerprint_data_points: int = 0  # How much data the baseline is built from

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deviation_type": self.deviation_type,
            "description": self.description,
            "severity": round(self.severity, 2),
            "confidence": round(self.confidence, 3),
            "expected": self.expected,
            "observed": self.observed,
            "data_points": self.fingerprint_data_points,
        }


@dataclass
class AgentFingerprint:
    """Statistical profile of an agent's tool-call behaviour."""
    agent_id: str
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    total_evaluations: int = 0

    # ─── Tool Usage Profile ───
    tool_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tool_first_seen: Dict[str, float] = field(default_factory=dict)
    tool_last_seen: Dict[str, float] = field(default_factory=dict)

    # ─── Session Profile ───
    session_lengths: List[int] = field(default_factory=list)    # Tool calls per session
    _current_session_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # ─── Timing Profile ───
    eval_timestamps: List[float] = field(default_factory=list)  # Last N timestamps
    avg_latency_ms: float = 0.0
    _latency_sum: float = 0.0
    _latency_count: int = 0

    # ─── Risk Profile ───
    risk_scores: List[float] = field(default_factory=list)      # Last N risk scores
    block_count: int = 0
    review_count: int = 0
    allow_count: int = 0

    # ─── Argument Patterns ───
    # For each tool, track the set of argument keys seen
    tool_arg_keys: Dict[str, Dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )
    # For each tool, track common argument values (for categorical args)
    tool_arg_values: Dict[str, Dict[str, Dict[str, int]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    )

    # ─── Sequence Profile ───
    # Track tool-to-tool transitions (bigrams)
    tool_transitions: Dict[str, Dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )
    _last_tool: Optional[str] = None

    # ─── Target Profile ───
    # Track domains/paths/resources accessed
    target_domains: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    target_paths: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Config
    _max_history: int = 1000  # Max items in rolling lists

    def to_summary(self) -> Dict[str, Any]:
        """Export fingerprint summary for API/dashboard."""
        total = max(self.total_evaluations, 1)
        tool_dist = {t: round(c / total * 100, 1) for t, c in self.tool_counts.items()}

        return {
            "agent_id": self.agent_id,
            "total_evaluations": self.total_evaluations,
            "age_hours": round((time.time() - self.created_at) / 3600, 1),
            "unique_tools": len(self.tool_counts),
            "tool_distribution_pct": tool_dist,
            "top_tools": sorted(self.tool_counts.items(), key=lambda x: -x[1])[:10],
            "avg_risk_score": round(sum(self.risk_scores[-100:]) / max(len(self.risk_scores[-100:]), 1), 2),
            "block_rate_pct": round(self.block_count / total * 100, 2),
            "avg_session_length": round(sum(self.session_lengths[-50:]) / max(len(self.session_lengths[-50:]), 1), 1) if self.session_lengths else 0,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "known_transitions": sum(sum(v.values()) for v in self.tool_transitions.values()),
            "maturity": self._maturity_level(),
        }

    def _maturity_level(self) -> str:
        """How reliable is this fingerprint?"""
        n = self.total_evaluations
        if n < 10:
            return "learning"       # Not enough data — don't flag deviations
        elif n < 50:
            return "developing"     # Some patterns, low confidence
        elif n < 200:
            return "established"    # Reliable patterns
        else:
            return "mature"         # High confidence baselines

    # ─── Serialization ───

    def to_json(self) -> Dict[str, Any]:
        """Serialize full fingerprint state to a JSON-safe dict."""
        return {
            "agent_id": self.agent_id,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "total_evaluations": self.total_evaluations,
            "tool_counts": dict(self.tool_counts),
            "tool_first_seen": dict(self.tool_first_seen),
            "tool_last_seen": dict(self.tool_last_seen),
            "session_lengths": self.session_lengths[-500:],
            "eval_timestamps": self.eval_timestamps[-500:],
            "avg_latency_ms": self.avg_latency_ms,
            "_latency_sum": self._latency_sum,
            "_latency_count": self._latency_count,
            "risk_scores": self.risk_scores[-500:],
            "block_count": self.block_count,
            "review_count": self.review_count,
            "allow_count": self.allow_count,
            "tool_arg_keys": {t: dict(v) for t, v in self.tool_arg_keys.items()},
            "tool_arg_values": {
                t: {k: dict(vv) for k, vv in v.items()}
                for t, v in self.tool_arg_values.items()
            },
            "tool_transitions": {t: dict(v) for t, v in self.tool_transitions.items()},
            "_last_tool": self._last_tool,
            "target_domains": dict(self.target_domains),
            "target_paths": dict(self.target_paths),
        }

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "AgentFingerprint":
        """Reconstruct an AgentFingerprint from a serialized dict."""
        fp = cls(agent_id=data["agent_id"])
        fp.created_at = data.get("created_at", time.time())
        fp.last_updated = data.get("last_updated", time.time())
        fp.total_evaluations = data.get("total_evaluations", 0)

        fp.tool_counts = defaultdict(int, data.get("tool_counts", {}))
        fp.tool_first_seen = data.get("tool_first_seen", {})
        fp.tool_last_seen = data.get("tool_last_seen", {})
        fp.session_lengths = data.get("session_lengths", [])
        fp.eval_timestamps = data.get("eval_timestamps", [])
        fp.avg_latency_ms = data.get("avg_latency_ms", 0.0)
        fp._latency_sum = data.get("_latency_sum", 0.0)
        fp._latency_count = data.get("_latency_count", 0)
        fp.risk_scores = data.get("risk_scores", [])
        fp.block_count = data.get("block_count", 0)
        fp.review_count = data.get("review_count", 0)
        fp.allow_count = data.get("allow_count", 0)

        fp.tool_arg_keys = defaultdict(
            lambda: defaultdict(int),
            {t: defaultdict(int, v) for t, v in data.get("tool_arg_keys", {}).items()},
        )
        raw_av = data.get("tool_arg_values", {})
        fp.tool_arg_values = defaultdict(
            lambda: defaultdict(lambda: defaultdict(int)),
            {
                t: defaultdict(
                    lambda: defaultdict(int),
                    {k: defaultdict(int, vv) for k, vv in v.items()},
                )
                for t, v in raw_av.items()
            },
        )
        fp.tool_transitions = defaultdict(
            lambda: defaultdict(int),
            {t: defaultdict(int, v) for t, v in data.get("tool_transitions", {}).items()},
        )
        fp._last_tool = data.get("_last_tool")
        fp.target_domains = defaultdict(int, data.get("target_domains", {}))
        fp.target_paths = defaultdict(int, data.get("target_paths", {}))
        return fp


# ═══════════════════════════════════════════════════════════
# FINGERPRINT ENGINE
# ═══════════════════════════════════════════════════════════

class FingerprintEngine:
    """
    Builds and maintains behavioural fingerprints for AI agents.

    The engine learns what's "normal" for each agent by observing their
    tool-call patterns over time. When an agent deviates from its
    established baseline, the engine returns Deviation objects that
    boost the risk score.

    The key insight: this gets more accurate with more data.
    After 200+ evaluations, the fingerprint is "mature" and
    deviations are high-confidence signals. A new competitor
    would need months of production data to match this.

    Usage:
        engine = FingerprintEngine()

        # In your evaluation pipeline:
        deviations = engine.check("agent_id", tool, args, session_id)
        risk_boost = sum(d.severity for d in deviations)

        # After evaluation completes:
        engine.record("agent_id", tool, args, decision, risk_score,
                      latency_ms, session_id)
    """

    def __init__(
        self,
        min_data_points: int = 10,
        novel_tool_severity: float = 25.0,
        frequency_spike_severity: float = 15.0,
        sequence_anomaly_severity: float = 20.0,
        arg_anomaly_severity: float = 10.0,
        velocity_spike_severity: float = 15.0,
        target_anomaly_severity: float = 30.0,
    ):
        self._fingerprints: Dict[str, AgentFingerprint] = {}
        self._lock = Lock()
        self.min_data_points = min_data_points

        # Severity configs
        self.novel_tool_severity = novel_tool_severity
        self.frequency_spike_severity = frequency_spike_severity
        self.sequence_anomaly_severity = sequence_anomaly_severity
        self.arg_anomaly_severity = arg_anomaly_severity
        self.velocity_spike_severity = velocity_spike_severity
        self.target_anomaly_severity = target_anomaly_severity

        # Persistence callbacks
        self._persist_save: Optional[Callable] = None   # fn(agent_id, state_json_str)
        self._persist_dirty: Dict[str, int] = {}        # agent_id -> evals since last save
        self._persist_interval: int = 10                 # Save every N evals

    def set_persistence(
        self,
        save_fn: Optional[Callable] = None,
        interval: int = 10,
    ):
        """Set persistence save callback.

        save_fn(agent_id: str, state_json: str, total_evals: int, maturity: str)
        """
        self._persist_save = save_fn
        self._persist_interval = interval

    def import_states(self, states: Dict[str, str]):
        """Bulk-load fingerprint states from persistence.

        Args:
            states: {agent_id: json_string} from DB
        """
        with self._lock:
            loaded = 0
            for agent_id, json_str in states.items():
                try:
                    data = json.loads(json_str)
                    fp = AgentFingerprint.from_json(data)
                    self._fingerprints[agent_id] = fp
                    loaded += 1
                except Exception:
                    pass  # skip corrupt entries
            return loaded

    def export_states(self) -> Dict[str, str]:
        """Export all fingerprint states as {agent_id: json_string}."""
        with self._lock:
            return {
                aid: json.dumps(fp.to_json())
                for aid, fp in self._fingerprints.items()
            }

    def _get_or_create(self, agent_id: str) -> AgentFingerprint:
        if agent_id not in self._fingerprints:
            self._fingerprints[agent_id] = AgentFingerprint(agent_id=agent_id)
        return self._fingerprints[agent_id]

    # ─── RECORD ───

    def record(
        self,
        agent_id: str,
        tool: str,
        args: Dict[str, Any],
        decision: str = "allow",
        risk_score: float = 0.0,
        latency_ms: float = 0.0,
        session_id: str = "default",
    ):
        """
        Record a completed evaluation to build the fingerprint.
        Call this AFTER every evaluation, regardless of decision.
        """
        with self._lock:
            fp = self._get_or_create(agent_id)
            now = time.time()

            fp.total_evaluations += 1
            fp.last_updated = now

            # Tool usage
            fp.tool_counts[tool] += 1
            if tool not in fp.tool_first_seen:
                fp.tool_first_seen[tool] = now
            fp.tool_last_seen[tool] = now

            # Session tracking
            fp._current_session_counts[session_id] += 1

            # Timing
            fp.eval_timestamps.append(now)
            if len(fp.eval_timestamps) > fp._max_history:
                fp.eval_timestamps = fp.eval_timestamps[-fp._max_history:]

            fp._latency_sum += latency_ms
            fp._latency_count += 1
            fp.avg_latency_ms = fp._latency_sum / fp._latency_count

            # Risk
            fp.risk_scores.append(risk_score)
            if len(fp.risk_scores) > fp._max_history:
                fp.risk_scores = fp.risk_scores[-fp._max_history:]

            if decision == "block":
                fp.block_count += 1
            elif decision == "review":
                fp.review_count += 1
            else:
                fp.allow_count += 1

            # Argument patterns
            for key in args.keys():
                fp.tool_arg_keys[tool][key] += 1
            for key, value in args.items():
                if isinstance(value, str) and len(value) < 200:
                    fp.tool_arg_values[tool][key][value] += 1

            # Sequence tracking
            if fp._last_tool is not None:
                fp.tool_transitions[fp._last_tool][tool] += 1
            fp._last_tool = tool

            # Target tracking (extract domains/paths from args)
            self._extract_targets(fp, args)

            # Periodic persistence flush
            if self._persist_save:
                self._persist_dirty[agent_id] = self._persist_dirty.get(agent_id, 0) + 1
                if self._persist_dirty[agent_id] >= self._persist_interval:
                    self._persist_dirty[agent_id] = 0
                    try:
                        self._persist_save(
                            agent_id,
                            json.dumps(fp.to_json()),
                            fp.total_evaluations,
                            fp._maturity_level(),
                        )
                    except Exception:
                        pass  # best-effort

    def _extract_targets(self, fp: AgentFingerprint, args: Dict[str, Any]):
        """Extract domains and paths from tool arguments."""
        for key, value in args.items():
            if not isinstance(value, str):
                continue
            # URL detection
            if value.startswith(("http://", "https://")):
                try:
                    # Simple domain extraction without urllib
                    parts = value.split("/")
                    if len(parts) >= 3:
                        domain = parts[2].split(":")[0]
                        fp.target_domains[domain] += 1
                        path = "/" + "/".join(parts[3:]) if len(parts) > 3 else "/"
                        fp.target_paths[path] += 1
                except (IndexError, ValueError):
                    pass
            # File path detection
            elif value.startswith("/") and not value.startswith("//"):
                fp.target_paths[value] += 1

    def end_session(self, agent_id: str, session_id: str = "default"):
        """Record that a session ended — finalise session length."""
        with self._lock:
            fp = self._fingerprints.get(agent_id)
            if fp and session_id in fp._current_session_counts:
                count = fp._current_session_counts.pop(session_id)
                fp.session_lengths.append(count)
                if len(fp.session_lengths) > fp._max_history:
                    fp.session_lengths = fp.session_lengths[-fp._max_history:]

    # ─── CHECK ───

    def check(
        self,
        agent_id: str,
        tool: str,
        args: Dict[str, Any],
        session_id: str = "default",
    ) -> List[Deviation]:
        """
        Check if a tool call deviates from this agent's fingerprint.
        Returns list of Deviation objects. Empty list = normal behaviour.

        Call this BEFORE evaluation to get risk boost.
        """
        with self._lock:
            fp = self._fingerprints.get(agent_id)

            # No fingerprint yet — can't detect deviations
            if fp is None:
                return []

            # Not enough data — still learning
            if fp.total_evaluations < self.min_data_points:
                return []

            maturity = fp._maturity_level()
            confidence_multiplier = {
                "learning": 0.0,
                "developing": 0.5,
                "established": 0.8,
                "mature": 1.0,
            }[maturity]

            deviations: List[Deviation] = []

            # Check 1: Novel tool (never seen before)
            d = self._check_novel_tool(fp, tool, confidence_multiplier)
            if d:
                deviations.append(d)

            # Check 2: Frequency spike (tool used way more than normal)
            d = self._check_frequency_spike(fp, tool, session_id, confidence_multiplier)
            if d:
                deviations.append(d)

            # Check 3: Sequence anomaly (unusual tool transition)
            d = self._check_sequence_anomaly(fp, tool, confidence_multiplier)
            if d:
                deviations.append(d)

            # Check 4: Argument anomaly (new arg keys or unusual values)
            ds = self._check_arg_anomaly(fp, tool, args, confidence_multiplier)
            deviations.extend(ds)

            # Check 5: Velocity spike (calls coming in faster than normal)
            d = self._check_velocity_spike(fp, confidence_multiplier)
            if d:
                deviations.append(d)

            # Check 6: Novel target (new domain or sensitive path)
            ds = self._check_target_anomaly(fp, args, confidence_multiplier)
            deviations.extend(ds)

            return deviations

    def _check_novel_tool(self, fp: AgentFingerprint, tool: str,
                          conf_mult: float) -> Optional[Deviation]:
        """Agent has never used this tool before."""
        if tool not in fp.tool_counts:
            known = list(fp.tool_counts.keys())
            return Deviation(
                deviation_type="novel_tool",
                description=f"Agent '{fp.agent_id}' has never used tool '{tool}'. "
                            f"Known tools: {known}",
                severity=self.novel_tool_severity * conf_mult,
                confidence=min(0.5 + (fp.total_evaluations / 500), 1.0) * conf_mult,
                expected=known,
                observed=tool,
                fingerprint_data_points=fp.total_evaluations,
            )
        return None

    def _check_frequency_spike(self, fp: AgentFingerprint, tool: str,
                                session_id: str, conf_mult: float) -> Optional[Deviation]:
        """Tool being used far more than its historical proportion."""
        if tool not in fp.tool_counts or fp.total_evaluations < 20:
            return None

        historical_rate = fp.tool_counts[tool] / fp.total_evaluations
        session_count = fp._current_session_counts.get(session_id, 0)

        if session_count < 3:
            return None

        # Compare session usage of this tool vs historical average
        # Need per-tool session count — approximate from total
        avg_session_len = (sum(fp.session_lengths) / max(len(fp.session_lengths), 1)) if fp.session_lengths else 10
        expected_in_session = historical_rate * avg_session_len

        if expected_in_session < 1:
            expected_in_session = 1

        # Flag if this session's usage is 3x+ the expected
        # (We don't track per-tool session count, so use total session count as proxy)
        if session_count > avg_session_len * 2 and avg_session_len > 3:
            return Deviation(
                deviation_type="frequency_spike",
                description=f"Session has {session_count} tool calls, "
                            f"avg session length is {avg_session_len:.0f}",
                severity=self.frequency_spike_severity * conf_mult,
                confidence=min(0.4 + (fp.total_evaluations / 400), 0.9) * conf_mult,
                expected=f"~{avg_session_len:.0f} calls per session",
                observed=f"{session_count} calls so far",
                fingerprint_data_points=len(fp.session_lengths),
            )
        return None

    def _check_sequence_anomaly(self, fp: AgentFingerprint, tool: str,
                                 conf_mult: float) -> Optional[Deviation]:
        """This tool transition has never been seen before."""
        if fp._last_tool is None:
            return None

        prev = fp._last_tool
        transitions = fp.tool_transitions.get(prev, {})

        # If we've seen transitions from prev before, but never to this tool
        if transitions and tool not in transitions:
            known_next = list(transitions.keys())
            total_from_prev = sum(transitions.values())
            if total_from_prev >= 5:  # Only flag if we have enough data
                return Deviation(
                    deviation_type="sequence_anomaly",
                    description=f"Transition '{prev}' → '{tool}' never observed. "
                                f"After '{prev}', agent normally calls: {known_next}",
                    severity=self.sequence_anomaly_severity * conf_mult,
                    confidence=min(0.4 + (total_from_prev / 100), 0.95) * conf_mult,
                    expected=known_next,
                    observed=f"{prev} → {tool}",
                    fingerprint_data_points=total_from_prev,
                )
        return None

    def _check_arg_anomaly(self, fp: AgentFingerprint, tool: str,
                            args: Dict[str, Any], conf_mult: float) -> List[Deviation]:
        """New argument keys or unusual argument values."""
        deviations = []

        if tool not in fp.tool_arg_keys:
            return deviations

        known_keys = fp.tool_arg_keys[tool]
        total_tool_calls = fp.tool_counts.get(tool, 0)

        if total_tool_calls < 10:
            return deviations

        # Check for completely new argument keys
        for key in args.keys():
            if key not in known_keys:
                deviations.append(Deviation(
                    deviation_type="arg_anomaly_new_key",
                    description=f"Tool '{tool}' called with new argument key '{key}'. "
                                f"Known keys: {list(known_keys.keys())}",
                    severity=self.arg_anomaly_severity * conf_mult,
                    confidence=min(0.3 + (total_tool_calls / 200), 0.85) * conf_mult,
                    expected=list(known_keys.keys()),
                    observed=key,
                    fingerprint_data_points=total_tool_calls,
                ))

        # Check for unusual argument values (for string args)
        if tool in fp.tool_arg_values:
            for key, value in args.items():
                if not isinstance(value, str) or len(value) > 200:
                    continue
                known_values = fp.tool_arg_values[tool].get(key, {})
                if known_values and len(known_values) >= 3:
                    # If we've seen many values for this key and this one is new
                    if value not in known_values and len(known_values) >= 10:
                        top_values = sorted(known_values.items(), key=lambda x: -x[1])[:5]
                        deviations.append(Deviation(
                            deviation_type="arg_anomaly_new_value",
                            description=f"Tool '{tool}', key '{key}': value never seen before. "
                                        f"Common values: {[v[0][:30] for v in top_values]}",
                            severity=self.arg_anomaly_severity * 0.5 * conf_mult,
                            confidence=min(0.2 + (len(known_values) / 100), 0.7) * conf_mult,
                            expected=f"{len(known_values)} known values",
                            observed=value[:50],
                            fingerprint_data_points=sum(known_values.values()),
                        ))

        return deviations

    def _check_velocity_spike(self, fp: AgentFingerprint,
                               conf_mult: float) -> Optional[Deviation]:
        """Calls coming in faster than historical average."""
        timestamps = fp.eval_timestamps
        if len(timestamps) < 20:
            return None

        # Calculate recent velocity (last 10 calls)
        recent = timestamps[-10:]
        if len(recent) < 2:
            return None

        recent_interval = (recent[-1] - recent[0]) / (len(recent) - 1)

        # Calculate historical velocity
        historical = timestamps[:-10]
        if len(historical) < 10:
            return None

        hist_sample = historical[-100:]  # Use last 100 for baseline
        hist_interval = (hist_sample[-1] - hist_sample[0]) / max(len(hist_sample) - 1, 1)

        if hist_interval <= 0 or recent_interval <= 0:
            return None

        # Flag if recent calls are 5x faster than historical
        speed_ratio = hist_interval / recent_interval
        if speed_ratio > 5.0:
            return Deviation(
                deviation_type="velocity_spike",
                description=f"Agent calling {speed_ratio:.1f}x faster than normal. "
                            f"Recent: {recent_interval:.1f}s between calls, "
                            f"Historical: {hist_interval:.1f}s",
                severity=self.velocity_spike_severity * conf_mult,
                confidence=min(0.5 + (len(timestamps) / 500), 0.9) * conf_mult,
                expected=f"{hist_interval:.1f}s between calls",
                observed=f"{recent_interval:.1f}s between calls",
                fingerprint_data_points=len(timestamps),
            )
        return None

    def _check_target_anomaly(self, fp: AgentFingerprint, args: Dict[str, Any],
                               conf_mult: float) -> List[Deviation]:
        """Agent accessing a domain or path it's never accessed before."""
        deviations = []

        if not fp.target_domains and not fp.target_paths:
            return deviations

        for key, value in args.items():
            if not isinstance(value, str):
                continue

            # Check URLs
            if value.startswith(("http://", "https://")):
                try:
                    parts = value.split("/")
                    if len(parts) >= 3:
                        domain = parts[2].split(":")[0]
                        if fp.target_domains and domain not in fp.target_domains:
                            known = sorted(fp.target_domains.keys())[:10]
                            deviations.append(Deviation(
                                deviation_type="novel_target_domain",
                                description=f"Agent contacting domain '{domain}' for the first time. "
                                            f"Known domains: {known}",
                                severity=self.target_anomaly_severity * conf_mult,
                                confidence=min(0.5 + (sum(fp.target_domains.values()) / 200), 0.95) * conf_mult,
                                expected=known,
                                observed=domain,
                                fingerprint_data_points=sum(fp.target_domains.values()),
                            ))
                except (IndexError, ValueError):
                    pass

            # Check file paths — flag sensitive paths
            elif value.startswith("/"):
                sensitive_prefixes = ["/etc/", "/root/", "/var/log/", "/proc/",
                                      "/sys/", "/boot/", "/dev/"]
                for prefix in sensitive_prefixes:
                    if value.startswith(prefix) and prefix not in {
                        p for p in fp.target_paths if p.startswith(prefix)
                    }:
                        deviations.append(Deviation(
                            deviation_type="novel_target_path",
                            description=f"Agent accessing sensitive path '{value}' "
                                        f"(prefix '{prefix}') for the first time",
                            severity=self.target_anomaly_severity * conf_mult,
                            confidence=0.8 * conf_mult,
                            expected="No prior access to this sensitive path",
                            observed=value,
                            fingerprint_data_points=len(fp.target_paths),
                        ))
                        break

        return deviations

    # ─── API ───

    def get_fingerprint(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get fingerprint summary for an agent."""
        with self._lock:
            fp = self._fingerprints.get(agent_id)
            return fp.to_summary() if fp else None

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all fingerprinted agents with summary stats."""
        with self._lock:
            return [fp.to_summary() for fp in self._fingerprints.values()]

    def get_maturity(self, agent_id: str) -> str:
        """Get fingerprint maturity level."""
        with self._lock:
            fp = self._fingerprints.get(agent_id)
            return fp._maturity_level() if fp else "unknown"

    def reset(self, agent_id: str):
        """Reset an agent's fingerprint (start learning from scratch)."""
        with self._lock:
            if agent_id in self._fingerprints:
                del self._fingerprints[agent_id]

    @property
    def agent_count(self) -> int:
        return len(self._fingerprints)

    @property
    def total_evaluations(self) -> int:
        return sum(fp.total_evaluations for fp in self._fingerprints.values())
