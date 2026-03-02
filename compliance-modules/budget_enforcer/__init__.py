"""
NOVTIA Governor — Evaluation Budget Enforcer
==============================================
Per-agent, per-session evaluation budgets with circuit breaker.
Supports DB-backed hydration: on startup the governor-service replays
recent ActionLog rows into the enforcer so counters survive restarts.

Circuit breaker state is persisted via save/load callbacks so that a
mid-cooldown restart doesn't reset the breaker prematurely.

Integration:
    from budget_enforcer import BudgetEnforcer, BudgetConfig
    enforcer = BudgetEnforcer()
    result = enforcer.check_budget("agent_001", session_id="sess_123")
    if result.exceeded:
        # Block the evaluation
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict
from threading import Lock


@dataclass
class BudgetConfig:
    """Budget configuration for an agent or global default."""
    max_evaluations_per_session: int = 500
    max_evaluations_per_hour: int = 1000
    max_evaluations_per_day: int = 10000
    max_blocked_consecutive: int = 10        # Circuit breaker threshold
    circuit_breaker_cooldown_sec: float = 300.0  # 5 min cooldown
    cost_limit_per_session: Optional[float] = None  # Optional cost cap

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_evaluations_per_session": self.max_evaluations_per_session,
            "max_evaluations_per_hour": self.max_evaluations_per_hour,
            "max_evaluations_per_day": self.max_evaluations_per_day,
            "max_blocked_consecutive": self.max_blocked_consecutive,
            "circuit_breaker_cooldown_sec": self.circuit_breaker_cooldown_sec,
            "cost_limit_per_session": self.cost_limit_per_session,
        }


@dataclass
class BudgetStatus:
    """Current budget status for an agent/session."""
    exceeded: bool = False
    reason: Optional[str] = None
    session_count: int = 0
    hourly_count: int = 0
    daily_count: int = 0
    consecutive_blocks: int = 0
    circuit_breaker_engaged: bool = False
    circuit_breaker_until: Optional[float] = None
    remaining_session: int = 0
    remaining_hourly: int = 0
    remaining_daily: int = 0
    session_cost: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "exceeded": self.exceeded,
            "reason": self.reason,
            "session_count": self.session_count,
            "hourly_count": self.hourly_count,
            "daily_count": self.daily_count,
            "consecutive_blocks": self.consecutive_blocks,
            "circuit_breaker_engaged": self.circuit_breaker_engaged,
            "remaining_session": self.remaining_session,
            "remaining_hourly": self.remaining_hourly,
            "remaining_daily": self.remaining_daily,
            "session_cost": round(self.session_cost, 4),
        }
        if self.circuit_breaker_until:
            d["circuit_breaker_until"] = self.circuit_breaker_until
        return d


@dataclass
class _AgentBucket:
    """Internal tracking state for an agent."""
    session_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    hourly_timestamps: List[float] = field(default_factory=list)
    daily_timestamps: List[float] = field(default_factory=list)
    consecutive_blocks: int = 0
    circuit_breaker_until: float = 0.0
    session_costs: Dict[str, float] = field(default_factory=lambda: defaultdict(float))


class BudgetEnforcer:
    """
    Enforces per-agent, per-session evaluation budgets.

    Features:
    - Per-session evaluation count limits
    - Per-hour and per-day rate limits
    - Consecutive block circuit breaker (auto-halt after N blocks)
    - Optional per-session cost tracking
    - Thread-safe in-memory store

    Usage:
        enforcer = BudgetEnforcer()

        # Set custom budget for an agent
        enforcer.set_agent_config("agent_001", BudgetConfig(
            max_evaluations_per_session=100,
            max_evaluations_per_hour=500,
        ))

        # Check before evaluation
        status = enforcer.check_budget("agent_001", session_id="sess_abc")
        if status.exceeded:
            return {"decision": "block", "reason": status.reason}

        # Record after evaluation
        enforcer.record_evaluation("agent_001", session_id="sess_abc",
                                   decision="allow", cost=0.001)
    """

    def __init__(self, default_config: Optional[BudgetConfig] = None):
        self.default_config = default_config or BudgetConfig()
        self._agent_configs: Dict[str, BudgetConfig] = {}
        self._buckets: Dict[str, _AgentBucket] = defaultdict(_AgentBucket)
        self._lock = Lock()
        self._hydrated = False

        # Persistence callbacks (set by governor-service for DB-backed state)
        self._cb_save: Optional[Callable] = None      # fn(agent_id, until, blocks)
        self._cb_load: Optional[Callable] = None      # fn(agent_id) -> (until, blocks) | None

    def set_persistence(
        self,
        save_cb: Optional[Callable] = None,
        load_cb: Optional[Callable] = None,
    ):
        """Set callbacks for circuit-breaker state persistence.

        save_cb(agent_id: str, until: float, blocks: int)
        load_cb(agent_id: str) -> Optional[Tuple[float, int]]
        """
        self._cb_save = save_cb
        self._cb_load = load_cb

    def mark_hydrated(self):
        """Mark that the enforcer has been hydrated from DB."""
        self._hydrated = True

    def set_agent_config(self, agent_id: str, config: BudgetConfig):
        """Set custom budget config for a specific agent."""
        with self._lock:
            self._agent_configs[agent_id] = config

    def get_config(self, agent_id: str) -> BudgetConfig:
        """Get the effective config for an agent."""
        return self._agent_configs.get(agent_id, self.default_config)

    def _prune_timestamps(self, bucket: _AgentBucket, now: float):
        """Remove timestamps older than 24 hours."""
        hour_ago = now - 3600
        day_ago = now - 86400
        bucket.hourly_timestamps = [t for t in bucket.hourly_timestamps if t > hour_ago]
        bucket.daily_timestamps = [t for t in bucket.daily_timestamps if t > day_ago]

    def check_budget(self, agent_id: str, session_id: str = "default") -> BudgetStatus:
        """
        Check if an evaluation is within budget.
        Does NOT record — call record_evaluation() after.
        """
        with self._lock:
            config = self.get_config(agent_id)
            bucket = self._buckets[agent_id]
            now = time.time()
            self._prune_timestamps(bucket, now)

            session_count = bucket.session_counts[session_id]
            hourly_count = len(bucket.hourly_timestamps)
            daily_count = len(bucket.daily_timestamps)
            session_cost = bucket.session_costs[session_id]

            status = BudgetStatus(
                session_count=session_count,
                hourly_count=hourly_count,
                daily_count=daily_count,
                consecutive_blocks=bucket.consecutive_blocks,
                remaining_session=max(0, config.max_evaluations_per_session - session_count),
                remaining_hourly=max(0, config.max_evaluations_per_hour - hourly_count),
                remaining_daily=max(0, config.max_evaluations_per_day - daily_count),
                session_cost=session_cost,
            )

            # Check circuit breaker (load persisted state if available)
            if bucket.circuit_breaker_until == 0.0 and self._cb_load:
                try:
                    persisted = self._cb_load(agent_id)
                    if persisted:
                        bucket.circuit_breaker_until, bucket.consecutive_blocks = persisted
                except Exception:
                    pass

            if bucket.circuit_breaker_until > now:
                status.exceeded = True
                status.reason = f"Circuit breaker engaged until {bucket.circuit_breaker_until:.0f} ({bucket.consecutive_blocks} consecutive blocks)"
                status.circuit_breaker_engaged = True
                status.circuit_breaker_until = bucket.circuit_breaker_until
                return status

            # Reset circuit breaker if cooldown passed
            if bucket.circuit_breaker_until > 0 and bucket.circuit_breaker_until <= now:
                bucket.circuit_breaker_until = 0.0
                bucket.consecutive_blocks = 0

            # Check session limit
            if session_count >= config.max_evaluations_per_session:
                status.exceeded = True
                status.reason = f"Session budget exceeded: {session_count}/{config.max_evaluations_per_session}"
                return status

            # Check hourly limit
            if hourly_count >= config.max_evaluations_per_hour:
                status.exceeded = True
                status.reason = f"Hourly budget exceeded: {hourly_count}/{config.max_evaluations_per_hour}"
                return status

            # Check daily limit
            if daily_count >= config.max_evaluations_per_day:
                status.exceeded = True
                status.reason = f"Daily budget exceeded: {daily_count}/{config.max_evaluations_per_day}"
                return status

            # Check cost limit
            if config.cost_limit_per_session and session_cost >= config.cost_limit_per_session:
                status.exceeded = True
                status.reason = f"Cost budget exceeded: {session_cost:.4f}/{config.cost_limit_per_session}"
                return status

            return status

    def record_evaluation(
        self,
        agent_id: str,
        session_id: str = "default",
        decision: str = "allow",
        cost: float = 0.0,
    ):
        """Record a completed evaluation against the budget."""
        with self._lock:
            config = self.get_config(agent_id)
            bucket = self._buckets[agent_id]
            now = time.time()

            bucket.session_counts[session_id] += 1
            bucket.hourly_timestamps.append(now)
            bucket.daily_timestamps.append(now)
            bucket.session_costs[session_id] += cost

            # Track consecutive blocks for circuit breaker
            if decision == "block":
                bucket.consecutive_blocks += 1
                if bucket.consecutive_blocks >= config.max_blocked_consecutive:
                    bucket.circuit_breaker_until = now + config.circuit_breaker_cooldown_sec
                    # Persist circuit breaker state
                    if self._cb_save:
                        try:
                            self._cb_save(agent_id, bucket.circuit_breaker_until,
                                          bucket.consecutive_blocks)
                        except Exception:
                            pass  # best-effort persistence
            else:
                bucket.consecutive_blocks = 0

    def reset_session(self, agent_id: str, session_id: str):
        """Reset a session's budget counters."""
        with self._lock:
            bucket = self._buckets[agent_id]
            bucket.session_counts[session_id] = 0
            bucket.session_costs[session_id] = 0.0

    def reset_agent(self, agent_id: str):
        """Reset all budget counters for an agent."""
        with self._lock:
            self._buckets[agent_id] = _AgentBucket()

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get budget status for all tracked agents."""
        with self._lock:
            result = {}
            now = time.time()
            for agent_id, bucket in self._buckets.items():
                self._prune_timestamps(bucket, now)
                config = self.get_config(agent_id)
                result[agent_id] = {
                    "sessions": dict(bucket.session_counts),
                    "hourly_count": len(bucket.hourly_timestamps),
                    "daily_count": len(bucket.daily_timestamps),
                    "consecutive_blocks": bucket.consecutive_blocks,
                    "circuit_breaker_engaged": bucket.circuit_breaker_until > now,
                    "config": config.to_dict(),
                }
            return result
