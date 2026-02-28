"""
verification/engine.py — Post-execution compliance verification
================================================================
After an agent executes a tool call, it submits the result here.
The verification engine runs a battery of checks against the actual
output/diff and compares it with the original pre-execution decision.

This closes the intent-vs-reality gap: the policy engine gates *intent*,
the verification engine validates *outcome*.

Checks are independent and run in sequence. Each produces a Finding
that is aggregated into a VerificationVerdict. If any check fails,
the verdict is "violation"; if any is suspicious, "suspicious";
otherwise "compliant".

The verdict is:
  - Logged to VerificationLog (full audit trail)
  - Fed back into chain analysis (updates session history)
  - Optionally triggers escalation for violations
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .drift import compute_drift_score, DriftSignal


# ---------------------------------------------------------------------------
# Finding & Verdict data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """Result of a single verification check."""
    check: str              # machine key: credential-scan, scope-compliance, etc.
    result: str             # pass | fail | warn
    detail: str             # human-readable explanation
    risk_contribution: int = 0
    duration_ms: float = 0.0


@dataclass
class VerificationVerdict:
    """Aggregated output of the full verification pipeline."""
    verification: str       # compliant | violation | suspicious
    risk_delta: int = 0     # risk score adjustment from verification
    findings: List[Finding] = field(default_factory=list)
    escalated: bool = False
    drift_score: Optional[float] = None
    drift_signals: List[DriftSignal] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Credential / Secret patterns — broader than the injection firewall because
# we scan the actual OUTPUT, which may contain leaked secrets
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    (r"\b[A-Za-z0-9+/]{40,}={0,2}\b", "base64-blob"),               # Long base64
    (r"\b(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}\b", "aws-access-key"),
    (r"\bghp_[A-Za-z0-9]{36,}\b", "github-pat"),
    (r"\bgho_[A-Za-z0-9]{36,}\b", "github-oauth"),
    (r"\bglpat-[A-Za-z0-9\-]{20,}\b", "gitlab-pat"),
    (r"\bsk-[A-Za-z0-9]{32,}\b", "openai-key"),
    (r"\bxox[bpsa]-[A-Za-z0-9\-]{10,}\b", "slack-token"),
    (r"\b(?:password|passwd|secret|api[_\s]?key|access[_\s]?token|private[_\s]?key|client[_\s]?secret)\s*[:=]\s*\S+", "credential-assignment"),
    (r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----", "pem-private-key"),
    (r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*\b", "bearer-token"),
    (r"\bey[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b", "jwt-token"),
]

_SECRET_COMPILED = [(re.compile(p, re.IGNORECASE), name) for p, name in _SECRET_PATTERNS]


# ---------------------------------------------------------------------------
# Destructive output patterns — evidence of dangerous side-effects
# ---------------------------------------------------------------------------

_DESTRUCTIVE_OUTPUT_PATTERNS = [
    (r"(?:deleted|removed|destroyed)\s+\d+\s+(?:files?|rows?|records?|tables?|databases?)", "mass-deletion"),
    (r"(?:drop(?:ped)?|truncat(?:ed|ing))\s+(?:table|database|collection|index)", "schema-destruction"),
    (r"(?:format(?:ted|ting)?)\s+(?:drive|disk|partition|volume)", "disk-format"),
    (r"permission(?:s)?\s+changed?\s+(?:to\s+)?(?:777|0777|rwxrwxrwx)", "permission-escalation"),
    (r"(?:chown|chmod)\s+.*(?:root|0:0)", "ownership-escalation"),
    (r"(?:disabl|deactivat)(?:ed?|ing|es)?\s+(?:the\s+)?(?:firewall|selinux|apparmor|antivirus|auth)", "security-disabling"),
    (r"(?:kill(?:ed|ing)?|terminat(?:ed|ing))\s+(?:all|process|pid|\d+)\s+(?:processes?|services?)?", "process-termination"),
]

_DESTRUCTIVE_COMPILED = [(re.compile(p, re.IGNORECASE), name) for p, name in _DESTRUCTIVE_OUTPUT_PATTERNS]


# ---------------------------------------------------------------------------
# Individual verification checks
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Normalize for scanning — same approach as injection firewall."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\s\u200b\u200c\u200d\ufeff]+", " ", text)
    return text


def _flatten_result(result: Dict[str, Any]) -> str:
    """Flatten a result dict into a single string for scanning."""
    parts = []
    for v in result.values():
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, dict):
            parts.append(str(v))
        elif isinstance(v, list):
            parts.append(" ".join(str(i) for i in v))
        else:
            parts.append(str(v))
    return _normalize(" ".join(parts))


def check_credential_leak(result_text: str) -> Finding:
    """Scan the tool output for leaked secrets, API keys, tokens."""
    t = time.perf_counter()
    found = []
    for pattern, name in _SECRET_COMPILED:
        if pattern.search(result_text):
            found.append(name)

    dur = round((time.perf_counter() - t) * 1000, 2)
    if found:
        return Finding(
            check="credential-scan",
            result="fail",
            detail=f"Potential credential(s) detected in output: {', '.join(found)}",
            risk_contribution=min(95, 60 + len(found) * 10),
            duration_ms=dur,
        )
    return Finding(
        check="credential-scan",
        result="pass",
        detail="No credentials detected in output.",
        duration_ms=dur,
    )


def check_destructive_output(result_text: str) -> Finding:
    """Scan for evidence of dangerous/destructive side-effects."""
    t = time.perf_counter()
    found = []
    for pattern, name in _DESTRUCTIVE_COMPILED:
        if pattern.search(result_text):
            found.append(name)

    dur = round((time.perf_counter() - t) * 1000, 2)
    if found:
        return Finding(
            check="destructive-output",
            result="fail",
            detail=f"Destructive side-effects detected: {', '.join(found)}",
            risk_contribution=min(90, 50 + len(found) * 15),
            duration_ms=dur,
        )
    return Finding(
        check="destructive-output",
        result="pass",
        detail="No destructive patterns detected in output.",
        duration_ms=dur,
    )


def check_scope_compliance(
    tool: str,
    result: Dict[str, Any],
    allowed_tools: Optional[List[str]] = None,
    original_args: Optional[Dict[str, Any]] = None,
) -> Finding:
    """Verify the result is consistent with the allowed scope."""
    t = time.perf_counter()

    # Check 1: tool should still be in allowed_tools
    if allowed_tools and tool not in allowed_tools:
        return Finding(
            check="scope-compliance",
            result="fail",
            detail=f"Tool '{tool}' not in allowed_tools after execution — mismatch.",
            risk_contribution=85,
            duration_ms=round((time.perf_counter() - t) * 1000, 2),
        )

    # Check 2: if the original args contained file paths, check result paths
    if original_args:
        # Extract any file paths from result output
        result_text = _flatten_result(result)
        original_text = str(original_args)

        # Detect if the result references paths outside the original scope
        path_pattern = re.compile(r"(/(?:etc|proc|sys|boot|root|var/log)/\S+)")
        result_paths = set(path_pattern.findall(result_text))
        original_paths = set(path_pattern.findall(original_text))
        suspicious_paths = result_paths - original_paths

        if suspicious_paths:
            return Finding(
                check="scope-compliance",
                result="warn",
                detail=f"Result references system paths not in original args: {suspicious_paths}",
                risk_contribution=40,
                duration_ms=round((time.perf_counter() - t) * 1000, 2),
            )

    return Finding(
        check="scope-compliance",
        result="pass",
        detail="Result is consistent with allowed scope.",
        duration_ms=round((time.perf_counter() - t) * 1000, 2),
    )


def check_diff_size(result: Dict[str, Any]) -> Finding:
    """Flag unexpectedly large changes (diffs, file modifications)."""
    t = time.perf_counter()

    diff_text = result.get("diff", "")
    output_text = result.get("output", "")

    # Count lines in diff
    diff_lines = len(diff_text.strip().splitlines()) if diff_text else 0
    output_size = len(output_text) if output_text else 0

    dur = round((time.perf_counter() - t) * 1000, 2)

    if diff_lines > 500:
        return Finding(
            check="diff-size",
            result="warn",
            detail=f"Large diff detected: {diff_lines} lines. May warrant manual review.",
            risk_contribution=30,
            duration_ms=dur,
        )
    if output_size > 100_000:  # 100KB
        return Finding(
            check="diff-size",
            result="warn",
            detail=f"Large output detected: {output_size:,} bytes. May contain exfiltrated data.",
            risk_contribution=25,
            duration_ms=dur,
        )
    return Finding(
        check="diff-size",
        result="pass",
        detail=f"Diff: {diff_lines} lines, output: {output_size:,} bytes — within normal range.",
        duration_ms=dur,
    )


def check_result_intent_alignment(
    original_decision: str,
    original_risk: int,
    tool: str,
    result: Dict[str, Any],
) -> Finding:
    """Compare the pre-execution decision with the actual result.

    Catches cases where:
    - An allowed action produced a clearly dangerous output
    - A tool that was marked 'review' somehow ran without approval
    - The result contradicts what the policy intended
    """
    t = time.perf_counter()
    result_text = _flatten_result(result)
    status = result.get("status", "").lower()
    error = result.get("error", "")

    dur_fn = lambda: round((time.perf_counter() - t) * 1000, 2)

    # If the original decision was block but the agent still executed
    if original_decision == "block":
        return Finding(
            check="intent-alignment",
            result="fail",
            detail=(
                f"Tool '{tool}' was BLOCKED by governance but agent submitted a result. "
                "Agent is executing blocked actions — potential policy bypass."
            ),
            risk_contribution=95,
            duration_ms=dur_fn(),
        )

    # If the original was review but wasn't explicitly approved
    # (The agent submitting a result implies execution)
    if original_decision == "review":
        return Finding(
            check="intent-alignment",
            result="warn",
            detail=(
                f"Tool '{tool}' was flagged for REVIEW. Agent executed without "
                "waiting for approval — possible review bypass."
            ),
            risk_contribution=50,
            duration_ms=dur_fn(),
        )

    # Low-risk allow that produced error — interesting but not alarming
    if status == "error" and original_risk < 30:
        return Finding(
            check="intent-alignment",
            result="warn",
            detail=f"Low-risk action resulted in error: {error[:200] if error else 'unknown'}",
            risk_contribution=10,
            duration_ms=dur_fn(),
        )

    return Finding(
        check="intent-alignment",
        result="pass",
        detail=f"Result status '{status or 'success'}' is consistent with '{original_decision}' decision.",
        duration_ms=dur_fn(),
    )


def check_output_injection(result_text: str) -> Finding:
    """Detect prompt injection or jailbreak patterns embedded in tool outputs.

    Agents can be manipulated by malicious content returned from tools
    (indirect prompt injection). This check catches common patterns.
    """
    t = time.perf_counter()

    _OUTPUT_INJECTION_PATTERNS = [
        (r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", "ignore-instructions"),
        (r"you\s+are\s+now\s+(?:a|an|in)\s+", "role-hijack"),
        (r"system\s*prompt\s*:\s*", "system-prompt-inject"),
        (r"<\|(?:im_start|system|assistant)\|>", "special-token-inject"),
        (r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", "llama-token-inject"),
        (r"(?:admin|root|sudo)\s+access\s+granted", "fake-privilege-escalation"),
        (r"(?:override|bypass|disable)\s+(?:all\s+)?(?:safety|security|governance|restrictions)", "safety-bypass"),
    ]

    compiled = [(re.compile(p, re.IGNORECASE), name) for p, name in _OUTPUT_INJECTION_PATTERNS]
    found = []
    for pattern, name in compiled:
        if pattern.search(result_text):
            found.append(name)

    dur = round((time.perf_counter() - t) * 1000, 2)
    if found:
        return Finding(
            check="output-injection",
            result="fail",
            detail=f"Prompt injection detected in tool output: {', '.join(found)}. "
                   "The tool may be returning adversarial content.",
            risk_contribution=min(90, 60 + len(found) * 10),
            duration_ms=dur,
        )
    return Finding(
        check="output-injection",
        result="pass",
        detail="No prompt injection patterns detected in output.",
        duration_ms=dur,
    )


# ---------------------------------------------------------------------------
# Independent re-verification — second-pass using the SAME policy engine
# but evaluated against the RESULT payload rather than the intent
# ---------------------------------------------------------------------------

def independent_reverify(
    tool: str,
    result: Dict[str, Any],
    original_risk: int,
) -> Finding:
    """Re-evaluate the tool call using the policy engine against the result.

    Acts as an independent "second pair of eyes": the original evaluation
    checked the INTENT (tool + args). This check runs the same policies
    against the OUTCOME (tool + result), catching cases where the output
    contains policy-violating content the intent didn't predict.
    """
    from ..schemas import ActionInput
    from ..policies.loader import load_all_policies

    t = time.perf_counter()

    # Build a synthetic ActionInput from the result
    synthetic_action = ActionInput(
        tool=tool,
        args=result,  # Treat result as "args" for policy matching
        context=None,
    )

    policies = load_all_policies()
    matched = []
    max_severity = 0

    for p in policies:
        if p.matches(synthetic_action):
            matched.append(p.id)
            max_severity = max(max_severity, p.severity)

    dur = round((time.perf_counter() - t) * 1000, 2)

    if matched:
        severity_delta = max_severity - original_risk
        if max_severity >= 80:
            return Finding(
                check="independent-reverify",
                result="fail",
                detail=(
                    f"Independent re-verification matched {len(matched)} policies "
                    f"against the tool result: {', '.join(matched)}. "
                    f"Max severity: {max_severity} (original risk: {original_risk}, delta: {severity_delta:+d})."
                ),
                risk_contribution=max_severity,
                duration_ms=dur,
            )
        return Finding(
            check="independent-reverify",
            result="warn",
            detail=(
                f"Re-verification matched {len(matched)} policies: {', '.join(matched)}. "
                f"Severity {max_severity} (below block threshold)."
            ),
            risk_contribution=max(0, severity_delta),
            duration_ms=dur,
        )

    return Finding(
        check="independent-reverify",
        result="pass",
        detail=f"Re-verified against {len(policies)} policies — no matches in output.",
        duration_ms=dur,
    )


# ---------------------------------------------------------------------------
# Main verification pipeline
# ---------------------------------------------------------------------------

def verify_execution(
    action_id: int,
    tool: str,
    result: Dict[str, Any],
    original_decision: str,
    original_risk: int,
    original_args: Optional[Dict[str, Any]] = None,
    allowed_tools: Optional[List[str]] = None,
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> VerificationVerdict:
    """
    Run the full verification pipeline against a tool execution result.

    Checks (in order):
      1. Credential leak scan
      2. Destructive output detection
      3. Scope compliance
      4. Diff size anomaly
      5. Result-intent alignment
      6. Output injection detection
      7. Independent re-verification (policy engine on result)
      8. Cross-session drift detection

    Returns a VerificationVerdict with aggregated findings.
    """
    result_text = _flatten_result(result)

    findings: List[Finding] = [
        check_credential_leak(result_text),
        check_destructive_output(result_text),
        check_scope_compliance(tool, result, allowed_tools, original_args),
        check_diff_size(result),
        check_result_intent_alignment(original_decision, original_risk, tool, result),
        check_output_injection(result_text),
        independent_reverify(tool, result, original_risk),
    ]

    # ── Cross-session drift detection ─────────────────────────────────
    drift_score = 0.0
    drift_signals: List[DriftSignal] = []
    if agent_id:
        drift_score, drift_signals = compute_drift_score(agent_id, session_id, tool, result)
        if drift_score >= 0.7:
            findings.append(Finding(
                check="drift-detection",
                result="fail" if drift_score >= 0.85 else "warn",
                detail=(
                    f"Cross-session drift score: {drift_score:.2f}. "
                    f"Signals: {', '.join(s.name for s in drift_signals if s.triggered)}."
                ),
                risk_contribution=int(drift_score * 50),
            ))
        else:
            findings.append(Finding(
                check="drift-detection",
                result="pass",
                detail=f"Drift score: {drift_score:.2f} — within normal range.",
            ))

    # ── Aggregate verdict ─────────────────────────────────────────────
    has_fail = any(f.result == "fail" for f in findings)
    has_warn = any(f.result == "warn" for f in findings)
    risk_delta = sum(f.risk_contribution for f in findings if f.result in ("fail", "warn"))

    if has_fail:
        verdict = "violation"
    elif has_warn:
        verdict = "suspicious"
    else:
        verdict = "compliant"

    return VerificationVerdict(
        verification=verdict,
        risk_delta=min(100, risk_delta),
        findings=findings,
        escalated=False,  # Set by the route after escalation check
        drift_score=drift_score if agent_id else None,
        drift_signals=drift_signals,
    )
