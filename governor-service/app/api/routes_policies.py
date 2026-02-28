from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..auth.dependencies import require_any, require_operator
from ..database import db_session
from ..models import PolicyModel, User
from ..policies.loader import invalidate_policy_cache
from ..schemas import PolicyCreate, PolicyRead, PolicyUpdate

router = APIRouter(prefix="/policies", tags=["policies"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_regex_fields(match_json: dict) -> None:
    """Validate that regex patterns in match_json compile without error."""
    for key in ("url_regex", "args_regex"):
        pattern = match_json.get(key)
        if pattern:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid regex in '{key}': {exc}",
                )


def _row_to_read(r: PolicyModel) -> PolicyRead:
    return PolicyRead(
        policy_id=r.policy_id,
        description=r.description,
        severity=r.severity,
        match_json=json.loads(r.match_json or "{}"),
        action=r.action,
        is_active=r.is_active,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=List[PolicyRead])
def list_policies(
    active_only: bool = Query(False, description="If true, return only active policies."),
    _user: User = Depends(require_any),
) -> List[PolicyRead]:
    """List all dynamic (DB-stored) policies."""
    with db_session() as session:
        stmt = select(PolicyModel)
        if active_only:
            stmt = stmt.where(PolicyModel.is_active == True)  # noqa: E712
        rows = session.execute(stmt).scalars().all()
        return [_row_to_read(r) for r in rows]


# ---------------------------------------------------------------------------
# Bulk import / export / template — MUST come before /{policy_id} routes
# ---------------------------------------------------------------------------

@router.get("/export/all", response_model=List[PolicyRead])
def export_policies(
    _user: User = Depends(require_any),
) -> List[PolicyRead]:
    """Export all dynamic policies as JSON (for backup / transfer)."""
    with db_session() as session:
        rows = session.execute(select(PolicyModel)).scalars().all()
        return [_row_to_read(r) for r in rows]


@router.get("/template")
def download_template(
    _user: User = Depends(require_any),
) -> dict:
    """Return a policy template that users can fill in and upload."""
    return {
        "description": "OpenClaw Governor — Policy Import Template",
        "instructions": (
            "Fill in the 'policies' array below. Each policy needs: "
            "policy_id (unique string), description, severity (0-100), "
            "action ('allow'|'block'|'review'), and match_json (matching rules). "
            "Upload this file via POST /policies/import."
        ),
        "policies": [
            {
                "policy_id": "example-block-curl",
                "description": "Block shell commands containing curl to external hosts",
                "severity": 80,
                "action": "block",
                "match_json": {
                    "tool": "shell",
                    "args_regex": "(curl|wget)\\s+https?://(?!localhost)"
                },
            },
            {
                "policy_id": "example-review-file-write",
                "description": "Review file write operations to sensitive paths",
                "severity": 60,
                "action": "review",
                "match_json": {
                    "tool": "file_write",
                    "args_regex": "(/etc/|/var/|~/.ssh/)"
                },
            },
        ],
    }


@router.post("/import", response_model=dict, status_code=201)
def import_policies(
    payload: dict,
    _user: User = Depends(require_operator),
) -> dict:
    """
    Bulk import policies from a JSON template.

    Expects {"policies": [{ policy_id, description, severity, action, match_json }, ...]}.
    Skips policies whose ID already exists. Returns counts of created/skipped/failed.
    """
    policies = payload.get("policies", [])
    if not isinstance(policies, list):
        raise HTTPException(status_code=422, detail="Expected 'policies' array in body.")

    created = 0
    skipped = 0
    failed = []

    with db_session() as session:
        for i, p in enumerate(policies):
            pid = p.get("policy_id", "").strip()
            if not pid:
                failed.append({"index": i, "reason": "Missing policy_id"})
                continue

            # Check for duplicates
            existing = session.execute(
                select(PolicyModel).where(PolicyModel.policy_id == pid)
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue

            # Validate required fields
            action = p.get("action", "").strip()
            if action not in ("allow", "block", "review"):
                failed.append({"index": i, "policy_id": pid, "reason": f"Invalid action: '{action}'"})
                continue

            severity = p.get("severity")
            try:
                severity = int(severity)
                if not (0 <= severity <= 100):
                    raise ValueError()
            except (ValueError, TypeError):
                failed.append({"index": i, "policy_id": pid, "reason": "Severity must be 0-100"})
                continue

            match_json = p.get("match_json", {})
            if isinstance(match_json, dict):
                # Validate regex fields
                for key in ("url_regex", "args_regex"):
                    pattern = match_json.get(key)
                    if pattern:
                        try:
                            re.compile(pattern)
                        except re.error as exc:
                            failed.append({"index": i, "policy_id": pid, "reason": f"Bad regex in {key}: {exc}"})
                            match_json = None
                            break
                if match_json is None:
                    continue
            else:
                match_json = {}

            row = PolicyModel(
                policy_id=pid,
                description=p.get("description", pid),
                severity=severity,
                match_json=json.dumps(match_json),
                action=action,
                is_active=p.get("is_active", True),
            )
            session.add(row)
            created += 1

        if created > 0:
            invalidate_policy_cache()

    return {
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "total_in_payload": len(policies),
    }


# ---------------------------------------------------------------------------
# Single policy CRUD — /{policy_id} routes
# ---------------------------------------------------------------------------

@router.get("/{policy_id}", response_model=PolicyRead)
def get_policy(
    policy_id: str,
    _user: User = Depends(require_any),
) -> PolicyRead:
    """Get a single dynamic policy by ID."""
    with db_session() as session:
        row = session.execute(
            select(PolicyModel).where(PolicyModel.policy_id == policy_id)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found.")
        return _row_to_read(row)


@router.post("", response_model=PolicyRead, status_code=201)
def create_policy(
    payload: PolicyCreate,
    _user: User = Depends(require_operator),
) -> PolicyRead:
    """Create a new dynamic policy. Requires operator or admin."""
    _validate_regex_fields(payload.match_json)

    with db_session() as session:
        existing = session.execute(
            select(PolicyModel).where(PolicyModel.policy_id == payload.policy_id)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Policy with this id already exists.")

        row = PolicyModel(
            policy_id=payload.policy_id,
            description=payload.description,
            severity=payload.severity,
            match_json=json.dumps(payload.match_json),
            action=payload.action,
        )
        session.add(row)
        session.flush()

        invalidate_policy_cache()

        return _row_to_read(row)


@router.patch("/{policy_id}", response_model=PolicyRead)
def update_policy(
    policy_id: str,
    payload: PolicyUpdate,
    _user: User = Depends(require_operator),
) -> PolicyRead:
    """Partially update an existing dynamic policy. Requires operator or admin.

    Only the fields provided in the request body are changed.
    """
    with db_session() as session:
        row = session.execute(
            select(PolicyModel).where(PolicyModel.policy_id == policy_id)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found.")

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(status_code=400, detail="No fields to update.")

        # Validate regex if match_json is being updated
        if "match_json" in changes:
            _validate_regex_fields(changes["match_json"])
            changes["match_json"] = json.dumps(changes["match_json"])

        for field, value in changes.items():
            setattr(row, field, value)

        row.updated_at = datetime.now(timezone.utc)
        session.flush()
        invalidate_policy_cache()

        return _row_to_read(row)


@router.patch("/{policy_id}/toggle", response_model=PolicyRead)
def toggle_policy(
    policy_id: str,
    _user: User = Depends(require_operator),
) -> PolicyRead:
    """Toggle a policy's active state. Requires operator or admin."""
    with db_session() as session:
        row = session.execute(
            select(PolicyModel).where(PolicyModel.policy_id == policy_id)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found.")

        row.is_active = not row.is_active
        row.updated_at = datetime.now(timezone.utc)
        session.flush()
        invalidate_policy_cache()

        return _row_to_read(row)


@router.delete("/{policy_id}")
def delete_policy(
    policy_id: str,
    _user: User = Depends(require_operator),
) -> dict:
    """Delete a dynamic policy by its ID. Requires operator or admin."""
    with db_session() as session:
        row = session.execute(
            select(PolicyModel).where(PolicyModel.policy_id == policy_id)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found.")
        session.delete(row)
        invalidate_policy_cache()
        return {"status": "deleted", "policy_id": policy_id}
