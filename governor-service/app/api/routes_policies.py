from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..auth.dependencies import require_any, require_operator
from ..database import db_session
from ..models import PolicyModel, User
from ..policies.loader import invalidate_policy_cache
from ..schemas import PolicyCreate, PolicyRead

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=List[PolicyRead])
def list_policies(_user: User = Depends(require_any)) -> List[PolicyRead]:
    """List all dynamic (DB-stored) policies."""
    with db_session() as session:
        rows = session.execute(select(PolicyModel)).scalars().all()
        return [
            PolicyRead(
                policy_id=r.policy_id,
                description=r.description,
                severity=r.severity,
                match_json=json.loads(r.match_json or "{}"),
                action=r.action,
            )
            for r in rows
        ]


@router.post("", response_model=PolicyRead, status_code=201)
def create_policy(
    payload: PolicyCreate,
    _user: User = Depends(require_operator),
) -> PolicyRead:
    """Create a new dynamic policy. Requires operator or admin."""
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

        return PolicyRead(
            policy_id=row.policy_id,
            description=row.description,
            severity=row.severity,
            match_json=payload.match_json,
            action=row.action,
        )


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
