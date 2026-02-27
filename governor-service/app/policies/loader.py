from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..config import settings
from ..schemas import ActionInput


@dataclass
class Policy:
    id: str
    description: str
    severity: int
    match: Dict[str, Any]
    action: str  # allow | block | review

    def matches(self, action: ActionInput) -> bool:
        """Return True if this policy applies to the given action."""
        m = self.match

        # Tool filter
        if tool := m.get("tool"):
            if tool != action.tool:
                return False

        # URL regex (applies only to http_request)
        url_regex = m.get("url_regex")
        if url_regex and action.tool == "http_request":
            url = str(action.args.get("url", ""))
            if not re.search(url_regex, url):
                return False

        # Generic args regex against flattened payload string
        args_regex = m.get("args_regex")
        if args_regex:
            flat = f"{action.tool} {action.args} {action.context}".lower()
            if not re.search(args_regex, flat):
                return False

        # If the policy has a tool match but no regex constraints → matched
        return True


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _base_policies_path() -> Path:
    configured = settings.policies_path
    # Support both absolute and relative paths
    p = Path(configured)
    if not p.is_absolute():
        p = Path(__file__).parent / "base_policies.yml"
    return p


def load_base_policies() -> List[Policy]:
    """Load policies from the YAML file on disk."""
    path = _base_policies_path()
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    return [
        Policy(
            id=item["id"],
            description=item.get("description", ""),
            severity=int(item.get("severity", 0)),
            match=item.get("match", {}) or {},
            action=item.get("action", "allow"),
        )
        for item in raw
    ]


def load_db_policies() -> List[Policy]:
    """Load dynamically created **active** policies from the database."""
    from sqlalchemy import select
    from ..database import db_session
    from ..models import PolicyModel

    with db_session() as session:
        rows = session.execute(
            select(PolicyModel).where(PolicyModel.is_active == True)  # noqa: E712
        ).scalars().all()
        return [
            Policy(
                id=row.policy_id,
                description=row.description,
                severity=row.severity,
                match=json.loads(row.match_json or "{}"),
                action=row.action,
            )
            for row in rows
        ]


# ---------------------------------------------------------------------------
# Cached loader — avoids re-reading YAML + DB on every evaluation
# ---------------------------------------------------------------------------

_policy_cache: List[Policy] = []
_policy_cache_ts: float = 0.0


def load_all_policies() -> List[Policy]:
    """Return base (YAML) policies followed by dynamic (DB) policies.

    Results are cached for ``settings.policy_cache_ttl_seconds`` (default 10s)
    to avoid hitting disk + DB on every single action evaluation.
    """
    global _policy_cache, _policy_cache_ts

    now = time.monotonic()
    if _policy_cache and (now - _policy_cache_ts) < settings.policy_cache_ttl_seconds:
        return _policy_cache

    _policy_cache = load_base_policies() + load_db_policies()
    _policy_cache_ts = now
    return _policy_cache


def invalidate_policy_cache() -> None:
    """Force the next load_all_policies() call to reload from source."""
    global _policy_cache_ts
    _policy_cache_ts = 0.0
