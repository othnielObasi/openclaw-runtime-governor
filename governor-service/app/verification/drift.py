"""
verification/drift.py — Cross-session behavioural drift detection
==================================================================
Compares an agent's current behaviour against its historical baseline.
Unlike chain_analysis.py (which detects intra-session attack patterns),
drift detection works ACROSS sessions to catch:

  - Gradual behavioural change over days/weeks
  - Tool usage distribution shifts
  - Risk profile changes
  - Operating hour anomalies
  - Sudden scope expansion (new tools the agent never used before)

The drift score is a float 0.0–1.0 where:
  0.0 = perfectly normal behaviour
  1.0 = completely aberrant

Each signal contributes a weighted component to the final score.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func

from ..database import db_session
from ..models import ActionLog


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DriftSignal:
    """One dimension of drift detection."""
    name: str
    description: str
    weight: float            # 0.0–1.0, relative importance
    triggered: bool = False
    value: float = 0.0       # signal-specific score 0.0–1.0
    detail: str = ""


# How far back to look for baseline (7 days)
BASELINE_WINDOW_DAYS = 7
# Minimum actions needed to establish a baseline
MIN_BASELINE_ACTIONS = 10
# Current session window for comparison
CURRENT_WINDOW_MINUTES = 120


# ---------------------------------------------------------------------------
# Signal computation functions
# ---------------------------------------------------------------------------

def _tool_distribution_shift(
    baseline_tools: Dict[str, int],
    current_tools: Dict[str, int],
) -> Tuple[float, str]:
    """Compute Jensen-Shannon-like divergence between tool distributions.

    Returns (score 0-1, detail string).
    """
    if not baseline_tools or not current_tools:
        return 0.0, "Insufficient data for tool distribution comparison."

    all_tools = set(baseline_tools.keys()) | set(current_tools.keys())
    baseline_total = sum(baseline_tools.values()) or 1
    current_total = sum(current_tools.values()) or 1

    divergence = 0.0
    new_tools = []
    for tool in all_tools:
        baseline_freq = baseline_tools.get(tool, 0) / baseline_total
        current_freq = current_tools.get(tool, 0) / current_total

        # Track completely new tools (not in baseline)
        if tool not in baseline_tools and current_tools.get(tool, 0) > 0:
            new_tools.append(tool)

        divergence += abs(baseline_freq - current_freq)

    # Normalize to 0–1
    score = min(1.0, divergence / 2)

    # Bonus for completely new tools
    if new_tools:
        score = min(1.0, score + 0.2 * len(new_tools))

    detail = f"Distribution shift: {score:.2f}."
    if new_tools:
        detail += f" New tools not in baseline: {', '.join(new_tools)}."

    return score, detail


def _risk_profile_shift(
    baseline_avg_risk: float,
    current_avg_risk: float,
    baseline_block_rate: float,
    current_block_rate: float,
) -> Tuple[float, str]:
    """Detect significant changes in risk profile."""
    risk_delta = abs(current_avg_risk - baseline_avg_risk)
    block_delta = abs(current_block_rate - baseline_block_rate)

    # Normalize: 30+ point risk change is max signal
    risk_score = min(1.0, risk_delta / 30.0)
    # 20%+ block rate change is max signal
    block_score = min(1.0, block_delta / 0.20)

    score = max(risk_score, block_score)

    detail = (
        f"Risk shift: {baseline_avg_risk:.0f} → {current_avg_risk:.0f} (Δ{risk_delta:+.0f}). "
        f"Block rate: {baseline_block_rate:.1%} → {current_block_rate:.1%}."
    )
    return score, detail


def _operating_hour_anomaly(
    baseline_hours: Dict[int, int],
    current_hour: int,
) -> Tuple[float, str]:
    """Detect if the agent is operating outside its normal hours."""
    if not baseline_hours:
        return 0.0, "No baseline hour data."

    total = sum(baseline_hours.values()) or 1
    hour_freq = baseline_hours.get(current_hour, 0) / total

    # If this hour has < 5% of baseline activity, it's unusual
    if hour_freq < 0.02:
        return 0.8, f"Agent rarely operates at hour {current_hour:02d} UTC ({hour_freq:.1%} of baseline)."
    if hour_freq < 0.05:
        return 0.4, f"Uncommon operating hour {current_hour:02d} UTC ({hour_freq:.1%} of baseline)."
    return 0.0, f"Normal operating hour {current_hour:02d} UTC ({hour_freq:.1%} of baseline)."


def _action_velocity_anomaly(
    baseline_rate_per_hour: float,
    current_rate_per_hour: float,
) -> Tuple[float, str]:
    """Detect abnormal action velocity (too fast or unusual patterns)."""
    if baseline_rate_per_hour < 0.1:
        return 0.0, "Insufficient baseline rate data."

    ratio = current_rate_per_hour / baseline_rate_per_hour if baseline_rate_per_hour > 0 else 0

    if ratio > 5.0:
        return 0.9, f"Action rate {ratio:.1f}x baseline ({current_rate_per_hour:.1f}/hr vs {baseline_rate_per_hour:.1f}/hr)."
    if ratio > 3.0:
        return 0.6, f"Elevated rate {ratio:.1f}x baseline ({current_rate_per_hour:.1f}/hr vs {baseline_rate_per_hour:.1f}/hr)."
    if ratio > 2.0:
        return 0.3, f"Slightly elevated rate {ratio:.1f}x baseline."
    return 0.0, f"Normal rate ({current_rate_per_hour:.1f}/hr, baseline {baseline_rate_per_hour:.1f}/hr)."


def _scope_expansion(
    baseline_tools: Dict[str, int],
    current_tool: str,
) -> Tuple[float, str]:
    """Detect when an agent starts using tools it never used before."""
    if not baseline_tools:
        return 0.0, "No baseline to compare."

    if current_tool not in baseline_tools:
        return 0.7, f"Tool '{current_tool}' never used in baseline ({BASELINE_WINDOW_DAYS}d history)."

    return 0.0, f"Tool '{current_tool}' is part of normal repertoire."


# ---------------------------------------------------------------------------
# Main drift computation
# ---------------------------------------------------------------------------

def compute_drift_score(
    agent_id: str,
    session_id: Optional[str],
    tool: str,
    result: Dict[str, Any],
) -> Tuple[float, List[DriftSignal]]:
    """
    Compare current agent behaviour against its historical baseline.

    Returns (drift_score 0.0–1.0, list of DriftSignals).
    """
    now = datetime.now(timezone.utc)
    baseline_cutoff = now - timedelta(days=BASELINE_WINDOW_DAYS)
    current_cutoff = now - timedelta(minutes=CURRENT_WINDOW_MINUTES)
    # Strip tzinfo for SQLite compatibility
    baseline_naive = baseline_cutoff.replace(tzinfo=None)
    current_naive = current_cutoff.replace(tzinfo=None)

    try:
        with db_session() as session:
            # ── Baseline stats (last N days, excluding current window) ────
            baseline_rows = session.execute(
                select(ActionLog)
                .where(ActionLog.agent_id == agent_id)
                .where(ActionLog.created_at >= baseline_naive)
                .where(ActionLog.created_at < current_naive)
                .order_by(ActionLog.created_at.asc())
            ).scalars().all()

            # ── Current session stats ─────────────────────────────────────
            current_stmt = (
                select(ActionLog)
                .where(ActionLog.agent_id == agent_id)
                .where(ActionLog.created_at >= current_naive)
                .order_by(ActionLog.created_at.asc())
            )
            if session_id:
                current_stmt = current_stmt.where(ActionLog.session_id == session_id)
            current_rows = session.execute(current_stmt).scalars().all()

    except Exception:
        return 0.0, []

    # Need minimum baseline to detect drift
    if len(baseline_rows) < MIN_BASELINE_ACTIONS:
        return 0.0, [DriftSignal(
            name="insufficient-baseline",
            description="Not enough historical data to detect drift",
            weight=0.0,
            detail=f"Baseline: {len(baseline_rows)} actions (need {MIN_BASELINE_ACTIONS}+).",
        )]

    # ── Compute baseline statistics ───────────────────────────────────
    baseline_tools: Dict[str, int] = {}
    baseline_risk_sum = 0
    baseline_block_count = 0
    baseline_hours: Dict[int, int] = {}

    for row in baseline_rows:
        baseline_tools[row.tool] = baseline_tools.get(row.tool, 0) + 1
        baseline_risk_sum += row.risk_score
        if row.decision == "block":
            baseline_block_count += 1
        hour = row.created_at.hour
        baseline_hours[hour] = baseline_hours.get(hour, 0) + 1

    baseline_count = len(baseline_rows)
    baseline_avg_risk = baseline_risk_sum / baseline_count
    baseline_block_rate = baseline_block_count / baseline_count

    # Baseline rate: actions per hour over the window
    baseline_hours_span = max(1, (BASELINE_WINDOW_DAYS * 24))
    baseline_rate = baseline_count / baseline_hours_span

    # ── Compute current statistics ────────────────────────────────────
    current_tools: Dict[str, int] = {}
    current_risk_sum = 0
    current_block_count = 0

    for row in current_rows:
        current_tools[row.tool] = current_tools.get(row.tool, 0) + 1
        current_risk_sum += row.risk_score
        if row.decision == "block":
            current_block_count += 1

    current_count = len(current_rows)
    current_avg_risk = current_risk_sum / max(1, current_count)
    current_block_rate = current_block_count / max(1, current_count)
    current_rate = current_count / (CURRENT_WINDOW_MINUTES / 60)

    current_hour = now.hour

    # ── Run drift signals ─────────────────────────────────────────────
    signals: List[DriftSignal] = []

    # 1. Tool distribution shift
    td_score, td_detail = _tool_distribution_shift(baseline_tools, current_tools)
    signals.append(DriftSignal(
        name="tool-distribution",
        description="Shift in tool usage patterns",
        weight=0.30,
        triggered=td_score >= 0.4,
        value=td_score,
        detail=td_detail,
    ))

    # 2. Risk profile shift
    rp_score, rp_detail = _risk_profile_shift(
        baseline_avg_risk, current_avg_risk, baseline_block_rate, current_block_rate,
    )
    signals.append(DriftSignal(
        name="risk-profile",
        description="Change in risk score or block rate",
        weight=0.25,
        triggered=rp_score >= 0.4,
        value=rp_score,
        detail=rp_detail,
    ))

    # 3. Operating hour anomaly
    oh_score, oh_detail = _operating_hour_anomaly(baseline_hours, current_hour)
    signals.append(DriftSignal(
        name="operating-hours",
        description="Activity outside normal operating hours",
        weight=0.15,
        triggered=oh_score >= 0.4,
        value=oh_score,
        detail=oh_detail,
    ))

    # 4. Action velocity
    av_score, av_detail = _action_velocity_anomaly(baseline_rate, current_rate)
    signals.append(DriftSignal(
        name="action-velocity",
        description="Abnormal rate of tool invocations",
        weight=0.15,
        triggered=av_score >= 0.4,
        value=av_score,
        detail=av_detail,
    ))

    # 5. Scope expansion
    se_score, se_detail = _scope_expansion(baseline_tools, tool)
    signals.append(DriftSignal(
        name="scope-expansion",
        description="Agent using tools outside its historical repertoire",
        weight=0.15,
        triggered=se_score >= 0.4,
        value=se_score,
        detail=se_detail,
    ))

    # ── Weighted aggregate ────────────────────────────────────────────
    drift_score = sum(s.value * s.weight for s in signals)
    drift_score = min(1.0, drift_score)

    return drift_score, signals
