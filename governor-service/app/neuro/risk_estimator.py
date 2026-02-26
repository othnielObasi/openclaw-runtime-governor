from __future__ import annotations

from ..schemas import ActionInput

# Keywords whose presence in the action payload raises the risk baseline
SENSITIVE_KEYWORDS = [
    "delete",
    "destroy",
    "wipe",
    "format",
    "shutdown",
    "privileged",
    "root",
    "sudo",
    "credential",
    "api key",
    "secret",
    "password",
    "private key",
    "access token",
]

# Tools that are inherently higher risk
HIGH_RISK_TOOLS = {"shell", "exec", "run_code"}
MEDIUM_RISK_TOOLS = {"http_request", "browser_open", "file_write"}


def estimate_neural_risk(action: ActionInput) -> int:
    """
    Heuristic neuro-style risk estimator.

    Returns an integer 0–100 representing how risky the action appears
    based on tool type, payload keywords, and recipient cardinality.
    This score is combined with policy-matched severity in the engine.
    """
    base = 0

    # Tool-based baseline
    if action.tool in HIGH_RISK_TOOLS:
        base = max(base, 40)
    elif action.tool.startswith("surge_"):
        base = max(base, 70)
    elif action.tool in MEDIUM_RISK_TOOLS:
        base = max(base, 20)

    # Flatten payload to a single string for keyword scanning
    payload = f"{action.tool} {action.args} {action.context}".lower()

    # Bulk-messaging cardinality check
    recipients = 0
    for key in ("to", "cc", "bcc", "recipients"):
        val = action.args.get(key)
        if isinstance(val, list):
            recipients += len(val)
        elif isinstance(val, str) and val:
            recipients += 1

    if recipients >= 50:
        base = max(base, 80)
    elif recipients >= 10:
        base = max(base, 60)

    # Keyword-based escalation
    keyword_hits = sum(1 for kw in SENSITIVE_KEYWORDS if kw in payload)
    if keyword_hits >= 3:
        base = max(base, 80)
    elif keyword_hits >= 1:
        base = max(base, 60)

    return max(0, min(100, base))
