from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..auth.dependencies import require_any, require_operator
from ..database import db_session
from ..models import PolicyModel, PolicyAuditLog, PolicyVersion, User
from ..policies.loader import invalidate_policy_cache
from ..schemas import (
    PolicyCreate, PolicyRead, PolicyUpdate, PolicyAuditRead, PolicyVersionRead,
)

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
        version=getattr(r, "version", 1) or 1,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _snapshot_version(
    session,
    row: PolicyModel,
    *,
    created_by: str | None = None,
    note: str | None = None,
) -> PolicyVersion:
    """Create an immutable version snapshot of the current policy state."""
    ver = PolicyVersion(
        policy_id=row.policy_id,
        version=row.version or 1,
        description=row.description,
        severity=row.severity,
        match_json=row.match_json,
        action=row.action,
        is_active=row.is_active,
        created_by=created_by,
        note=note,
    )
    session.add(ver)
    return ver


def _log_policy_audit(
    session,
    action: str,
    policy_id: str,
    user: User,
    changes: dict | None = None,
    note: str | None = None,
) -> None:
    """Write an immutable audit trail entry for a policy mutation."""
    entry = PolicyAuditLog(
        action=action,
        policy_id=policy_id,
        username=user.username,
        user_role=user.role,
        changes_json=json.dumps(changes) if changes else None,
        note=note,
    )
    session.add(entry)


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
    user: User = Depends(require_operator),
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
            _log_policy_audit(
                session, "import", pid, user,
                changes={"severity": severity, "action": action},
                note=f"Imported from bulk upload ({len(policies)} total in payload)",
            )
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
# Policy audit trail — query endpoint (before /{policy_id} routes)
# ---------------------------------------------------------------------------

def _audit_to_read(row: PolicyAuditLog) -> PolicyAuditRead:
    return PolicyAuditRead(
        id=row.id,
        created_at=row.created_at,
        action=row.action,
        policy_id=row.policy_id,
        username=row.username,
        user_role=row.user_role,
        changes_json=json.loads(row.changes_json) if row.changes_json else None,
        note=row.note,
    )


@router.get("/audit/trail", response_model=List[PolicyAuditRead])
def list_policy_audit(
    policy_id: Optional[str] = Query(None, description="Filter by policy ID"),
    action: Optional[str] = Query(None, description="Filter: create|edit|archive|activate|delete|import|toggle|bulk_archive|bulk_activate|bulk_delete"),
    username: Optional[str] = Query(None, description="Filter by who made the change"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _user: User = Depends(require_any),
) -> List[PolicyAuditRead]:
    """Query the immutable policy change audit trail."""
    with db_session() as session:
        stmt = select(PolicyAuditLog).order_by(PolicyAuditLog.created_at.desc())
        if policy_id:
            stmt = stmt.where(PolicyAuditLog.policy_id == policy_id)
        if action:
            stmt = stmt.where(PolicyAuditLog.action == action)
        if username:
            stmt = stmt.where(PolicyAuditLog.username == username)
        stmt = stmt.offset(offset).limit(limit)
        rows = session.execute(stmt).scalars().all()
        return [_audit_to_read(r) for r in rows]


@router.get("/audit/stats")
def policy_audit_stats(
    _user: User = Depends(require_any),
) -> dict:
    """Summary statistics for the policy audit trail."""
    from sqlalchemy import func
    with db_session() as session:
        total = session.execute(
            select(func.count(PolicyAuditLog.id))
        ).scalar() or 0

        def _count(col, val):
            return session.execute(
                select(func.count(PolicyAuditLog.id)).where(col == val)
            ).scalar() or 0

        return {
            "total": total,
            "creates": _count(PolicyAuditLog.action, "create"),
            "edits": _count(PolicyAuditLog.action, "edit"),
            "archives": _count(PolicyAuditLog.action, "archive"),
            "activates": _count(PolicyAuditLog.action, "activate"),
            "deletes": _count(PolicyAuditLog.action, "delete"),
            "imports": _count(PolicyAuditLog.action, "import"),
            "toggles": _count(PolicyAuditLog.action, "toggle"),
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
    user: User = Depends(require_operator),
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
            version=1,
        )
        session.add(row)
        session.flush()  # ensure row has defaults before snapshot

        # Create initial version snapshot (v1)
        _snapshot_version(session, row, created_by=user.username, note="Initial creation")

        _log_policy_audit(
            session, "create", payload.policy_id, user,
            changes={"severity": payload.severity, "action": payload.action, "description": payload.description},
        )
        session.flush()

        invalidate_policy_cache()

        return _row_to_read(row)


@router.patch("/{policy_id}", response_model=PolicyRead)
def update_policy(
    policy_id: str,
    payload: PolicyUpdate,
    user: User = Depends(require_operator),
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

        # Capture before-state for audit
        before = {
            "description": row.description,
            "severity": row.severity,
            "action": row.action,
            "match_json": json.loads(row.match_json or "{}"),
            "is_active": row.is_active,
            "version": row.version or 1,
        }

        # Validate regex if match_json is being updated
        if "match_json" in changes:
            _validate_regex_fields(changes["match_json"])
            changes["match_json"] = json.dumps(changes["match_json"])

        for field, value in changes.items():
            setattr(row, field, value)

        # Increment version
        row.version = (row.version or 1) + 1
        row.updated_at = datetime.now(timezone.utc)

        # Snapshot the new version
        _snapshot_version(session, row, created_by=user.username, note="Edited")

        # Build after-state for audit (only changed fields)
        after = {}
        raw_changes = payload.model_dump(exclude_unset=True)
        for k, v in raw_changes.items():
            after[k] = v
        after["version"] = row.version

        _log_policy_audit(
            session, "edit", policy_id, user,
            changes={"before": before, "after": after},
        )
        session.flush()
        invalidate_policy_cache()

        return _row_to_read(row)


@router.patch("/{policy_id}/toggle", response_model=PolicyRead)
def toggle_policy(
    policy_id: str,
    user: User = Depends(require_operator),
) -> PolicyRead:
    """Toggle a policy's active state. Requires operator or admin."""
    with db_session() as session:
        row = session.execute(
            select(PolicyModel).where(PolicyModel.policy_id == policy_id)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found.")

        was_active = row.is_active
        row.is_active = not row.is_active
        row.updated_at = datetime.now(timezone.utc)

        audit_action = "activate" if row.is_active else "archive"
        _log_policy_audit(
            session, audit_action, policy_id, user,
            changes={"is_active": {"before": was_active, "after": row.is_active}},
            note=f"Toggled: {'archived → active' if row.is_active else 'active → archived'}",
        )
        session.flush()
        invalidate_policy_cache()

        return _row_to_read(row)


@router.patch("/{policy_id}/archive", response_model=PolicyRead)
def archive_policy(
    policy_id: str,
    user: User = Depends(require_operator),
) -> PolicyRead:
    """Explicitly archive a policy (set is_active=False). Idempotent.

    Archived policies are preserved in the database but excluded from
    the active evaluation pipeline. They can be re-activated at any time.
    """
    with db_session() as session:
        row = session.execute(
            select(PolicyModel).where(PolicyModel.policy_id == policy_id)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found.")

        if row.is_active:
            row.is_active = False
            row.updated_at = datetime.now(timezone.utc)
            _log_policy_audit(
                session, "archive", policy_id, user,
                changes={"is_active": {"before": True, "after": False}},
            )
            session.flush()
            invalidate_policy_cache()

        return _row_to_read(row)


@router.patch("/{policy_id}/activate", response_model=PolicyRead)
def activate_policy(
    policy_id: str,
    user: User = Depends(require_operator),
) -> PolicyRead:
    """Explicitly activate an archived policy (set is_active=True). Idempotent.

    Re-activates a previously archived policy, putting it back into
    the live evaluation pipeline immediately.
    """
    with db_session() as session:
        row = session.execute(
            select(PolicyModel).where(PolicyModel.policy_id == policy_id)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found.")

        if not row.is_active:
            row.is_active = True
            row.updated_at = datetime.now(timezone.utc)
            _log_policy_audit(
                session, "activate", policy_id, user,
                changes={"is_active": {"before": False, "after": True}},
            )
            session.flush()
            invalidate_policy_cache()

        return _row_to_read(row)


# ---------------------------------------------------------------------------
# Version history & restore
# ---------------------------------------------------------------------------

@router.get("/{policy_id}/versions", response_model=List[PolicyVersionRead])
def list_policy_versions(
    policy_id: str,
    _user: User = Depends(require_any),
) -> List[PolicyVersionRead]:
    """List all saved versions of a policy (newest first)."""
    with db_session() as session:
        # Verify policy exists
        row = session.execute(
            select(PolicyModel).where(PolicyModel.policy_id == policy_id)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found.")

        stmt = (
            select(PolicyVersion)
            .where(PolicyVersion.policy_id == policy_id)
            .order_by(PolicyVersion.version.desc())
        )
        versions = session.execute(stmt).scalars().all()
        return [
            PolicyVersionRead(
                id=v.id,
                policy_id=v.policy_id,
                version=v.version,
                description=v.description,
                severity=v.severity,
                match_json=json.loads(v.match_json or "{}"),
                action=v.action,
                is_active=v.is_active,
                created_by=v.created_by,
                created_at=v.created_at,
                note=v.note,
            )
            for v in versions
        ]


@router.post("/{policy_id}/restore/{version}", response_model=PolicyRead)
def restore_policy_version(
    policy_id: str,
    version: int,
    user: User = Depends(require_operator),
) -> PolicyRead:
    """
    Restore a policy to a previous version.

    Creates a *new* version with the content from the specified historical
    version — history is never rewritten.
    """
    with db_session() as session:
        row = session.execute(
            select(PolicyModel).where(PolicyModel.policy_id == policy_id)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found.")

        target = session.execute(
            select(PolicyVersion)
            .where(PolicyVersion.policy_id == policy_id)
            .where(PolicyVersion.version == version)
        ).scalar_one_or_none()
        if not target:
            raise HTTPException(
                status_code=404,
                detail=f"Version {version} not found for policy '{policy_id}'.",
            )

        before_version = row.version or 1

        # Apply historical values
        row.description = target.description
        row.severity = target.severity
        row.match_json = target.match_json
        row.action = target.action
        row.is_active = target.is_active
        row.version = before_version + 1
        row.updated_at = datetime.now(timezone.utc)

        # Snapshot the restored version
        _snapshot_version(
            session, row,
            created_by=user.username,
            note=f"Restored from v{version}",
        )

        _log_policy_audit(
            session, "restore", policy_id, user,
            changes={
                "restored_from_version": version,
                "new_version": row.version,
            },
            note=f"Restored to content from v{version}",
        )
        session.flush()
        invalidate_policy_cache()

        return _row_to_read(row)


@router.delete("/{policy_id}")
def delete_policy(
    policy_id: str,
    user: User = Depends(require_operator),
) -> dict:
    """Delete a dynamic policy by its ID. Requires operator or admin."""
    with db_session() as session:
        row = session.execute(
            select(PolicyModel).where(PolicyModel.policy_id == policy_id)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found.")

        # Capture full state before deletion for audit
        _log_policy_audit(
            session, "delete", policy_id, user,
            changes={
                "description": row.description,
                "severity": row.severity,
                "action": row.action,
                "is_active": row.is_active,
                "match_json": json.loads(row.match_json or "{}"),
            },
            note="Permanently deleted",
        )

        session.delete(row)
        invalidate_policy_cache()
        return {"status": "deleted", "policy_id": policy_id}
