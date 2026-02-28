from __future__ import annotations

import re
import time
import unicodedata
from typing import List

from .loader import Policy, load_all_policies
from ..schemas import ActionInput, ActionDecision, TraceStep
from ..state import is_kill_switch_enabled
from ..neuro.risk_estimator import estimate_neural_risk
from ..session_store import get_agent_history
from ..chain_analysis import check_chain_escalation


# ---------------------------------------------------------------------------
# Injection Firewall
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = [
    r"ignore\s+previous\s+instructions",
    r"override\s+all\s+prior\s+rules",
    r"disable\s+safety",
    r"jailbreak",
    r"do\s+anything\s+now",
    r"developer[_\s]mode",
    r"rm\s+-rf\s+/",
    r"format\s+c:",
    r"drop\s+database",
    r"exec\s+xp_cmdshell",
    r"base64_decode\s*\(",
    r"ignore\s+all\s+rules",
    r"you\s+are\s+now\s+in",
    r"pretend\s+you\s+are",
    r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions",
    r"forget\s+(all\s+)?instructions",
    r"system\s*prompt\s*override",
    r"\bsudo\b.*\brm\b",
    r"eval\s*\(",
    r"os\.system\s*\(",
]

# Pre-compile injection patterns for performance
_INJECTION_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def _normalize_text(text: str) -> str:
    """Normalize Unicode and collapse whitespace to defeat obfuscation."""
    # NFKC normalization converts homoglyphs to ASCII equivalents
    text = unicodedata.normalize("NFKC", text)
    # Collapse all whitespace (including zero-width chars) into single spaces
    text = re.sub(r"[\s\u200b\u200c\u200d\ufeff]+", " ", text)
    return text.lower()


def _flatten_payload(action: ActionInput) -> str:
    parts = [action.tool]
    try:
        parts.append(str(action.args))
    except Exception:
        pass
    if action.context is not None:
        try:
            parts.append(str(action.context))
        except Exception:
            pass
    return _normalize_text(" ".join(parts))


def _run_injection_firewall(action: ActionInput) -> tuple[bool, str | None, list[str]]:
    """
    Scan the full flattened action payload for known injection patterns.
    Returns (triggered, reason, matched_patterns).
    """
    payload = _flatten_payload(action)
    for pattern in _INJECTION_COMPILED:
        m = pattern.search(payload)
        if m:
            return True, f"Injection firewall triggered on pattern: '{m.group()}'", [pattern.pattern]
    return False, None, []


# ---------------------------------------------------------------------------
# Scope Enforcer
# ---------------------------------------------------------------------------

def _enforce_scopes(action: ActionInput) -> tuple[bool, str | None]:
    ctx = action.context or {}
    allowed = ctx.get("allowed_tools")
    if isinstance(allowed, list) and allowed:
        if action.tool not in allowed:
            return True, (
                f"Tool '{action.tool}' is not in allowed_tools scope "
                f"({allowed!r}) – blocking for safety."
            )
    return False, None


# ---------------------------------------------------------------------------
# Trace helper
# ---------------------------------------------------------------------------

def _step(
    layer: int,
    name: str,
    key: str,
    outcome: str,
    risk: int,
    matched: list[str],
    detail: str | None,
    start: float,
) -> TraceStep:
    return TraceStep(
        layer=layer,
        name=name,
        key=key,
        outcome=outcome,
        risk_contribution=risk,
        matched_ids=matched,
        detail=detail,
        duration_ms=round((time.perf_counter() - start) * 1000, 2),
    )


# ---------------------------------------------------------------------------
# Core evaluation  — now emits a full execution_trace
# ---------------------------------------------------------------------------

def evaluate_action(action: ActionInput) -> ActionDecision:
    """
    Evaluate a tool-call against all governor layers and return a decision
    with a full execution_trace describing exactly which layers fired, their
    outcome, matched policy/pattern IDs, and wall-clock duration.

    Evaluation order (short-circuit on first block):
      1. Global kill switch
      2. Injection firewall
      3. Scope enforcement
      4. Policy engine (YAML + DB policies via Policy.matches())
      5. Neuro risk estimator (raises risk_score but does not change decision)
    """
    trace: list[TraceStep] = []

    # ── Layer 1: Kill switch ──────────────────────────────────────────
    t = time.perf_counter()
    if is_kill_switch_enabled():
        trace.append(_step(1, "Kill Switch", "kill", "block", 100,
                           ["kill-switch"],
                           "Global kill switch enabled — all actions blocked.", t))
        return ActionDecision(
            decision="block", risk_score=100,
            explanation="Global kill switch is enabled; all actions are blocked.",
            policy_ids=["kill-switch"], execution_trace=trace,
        )
    trace.append(_step(1, "Kill Switch", "kill", "pass", 0, [],
                       "Kill switch inactive.", t))

    # ── Layer 2: Injection firewall ───────────────────────────────────
    t = time.perf_counter()
    triggered, reason, inj_matched = _run_injection_firewall(action)
    if triggered:
        trace.append(_step(2, "Injection Firewall", "firewall", "block", 95,
                           inj_matched, reason, t))
        return ActionDecision(
            decision="block", risk_score=95,
            explanation=reason or "Injection firewall blocked this action.",
            policy_ids=["injection-firewall"], execution_trace=trace,
        )
    trace.append(_step(2, "Injection Firewall", "firewall", "pass", 0, [],
                       f"Scanned {len(_INJECTION_COMPILED)} patterns — none matched.", t))

    # ── Layer 3: Scope enforcement ────────────────────────────────────
    t = time.perf_counter()
    scoped_blocked, scope_reason = _enforce_scopes(action)
    if scoped_blocked:
        trace.append(_step(3, "Scope Enforcer", "scope", "block", 90,
                           ["scope-violation"], scope_reason, t))
        return ActionDecision(
            decision="block", risk_score=90,
            explanation=scope_reason or "Tool not permitted by provided scope.",
            policy_ids=["scope-violation"], execution_trace=trace,
        )
    ctx = action.context or {}
    allowed_tools = ctx.get("allowed_tools")
    scope_detail = (
        f"Tool '{action.tool}' permitted within scope."
        if allowed_tools else
        "No allowed_tools constraint — unrestricted."
    )
    trace.append(_step(3, "Scope Enforcer", "scope", "pass", 0, [], scope_detail, t))

    # ── Layer 4: Policy engine ────────────────────────────────────────
    t = time.perf_counter()
    policies: List[Policy] = load_all_policies()
    matched: list[str] = []
    risk_score = 0
    decision = "allow"
    explanation_parts: list[str] = []

    for p in policies:
        if not p.matches(action):
            continue
        matched.append(p.id)
        risk_score = max(risk_score, p.severity)
        explanation_parts.append(f"Matched policy '{p.id}': {p.description}.")
        if p.action == "block":
            decision = "block"
        elif p.action == "review" and decision != "block":
            decision = "review"

    policy_outcome = "block" if decision == "block" else ("review" if decision == "review" else "pass")
    policy_detail = (
        f"Matched {len(matched)}/{len(policies)} policies: {', '.join(matched)}."
        if matched else
        f"Checked {len(policies)} policies — no matches."
    )
    trace.append(_step(4, "Policy Engine", "policy", policy_outcome, risk_score,
                       matched, policy_detail, t))

    # ── Layer 5: Neuro risk estimator + chain analysis ───────────────
    t = time.perf_counter()

    # Retrieve persistent session history from DB (sandboxed by agent_id + session_id)
    ctx_data = action.context or {}
    agent_id  = ctx_data.get("agent_id")
    session_id = ctx_data.get("session_id")
    history = get_agent_history(agent_id, session_id) if agent_id else []

    neural_risk = estimate_neural_risk(action)

    # Chain escalation check against persistent history
    chain = check_chain_escalation(history)
    chain_boost = 0
    chain_detail = "No escalation chain detected."
    if chain.triggered:
        chain_boost = chain.boost
        neural_risk = min(100, neural_risk + chain_boost)
        chain_detail = (
            f"Chain '{chain.pattern}' detected: {chain.description}. "
            f"+{chain_boost} risk. {chain.evidence or ''}"
        )
        explanation_parts.append(
            f"Behavioural chain '{chain.pattern}' detected: {chain.description}."
        )

    neuro_raised = neural_risk > risk_score
    if neuro_raised:
        risk_score = neural_risk
        explanation_parts.append(f"Neuro risk estimator raised risk score to {neural_risk}.")

    # Promote to review if chain pushed risk high enough
    if chain.triggered and risk_score >= 80 and decision == "allow":
        decision = "review"
        explanation_parts.append("Decision promoted to 'review' due to chain escalation.")

    neuro_matched = []
    if neural_risk > 0:
        neuro_matched.append(f"neural:{neural_risk}")
    if chain.triggered:
        neuro_matched.append(f"chain:{chain.pattern}")

    neuro_detail = (
        f"Neural score: {neural_risk}. "
        f"{'↑ Raised overall risk.' if neuro_raised else 'Below policy score.'} "
        f"Session depth: {len(history)} actions. {chain_detail}"
    )
    trace.append(_step(5, "Neuro Estimator", "neuro", "pass", neural_risk,
                       neuro_matched, neuro_detail, t))

    if not explanation_parts:
        explanation_parts.append("No policies matched; default allow.")

    return ActionDecision(
        decision=decision,
        risk_score=risk_score,
        explanation="; ".join(explanation_parts),
        policy_ids=matched,
        modified_args=None,
        execution_trace=trace,
        chain_pattern=chain.pattern if chain.triggered else None,
        chain_description=chain.description if chain.triggered else None,
        session_depth=len(history),
    )
