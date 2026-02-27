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
