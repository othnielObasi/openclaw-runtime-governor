"""
routes_surge.py — SURGE Token Governance Integration
=====================================================
Connects the OpenClaw Governor to the SURGE token economy:

1. **Governance Fee Gating** — Tool evaluations can require a micro-fee
   in $SURGE, enabling a pay-per-governance model for premium safety.

2. **Policy Staking** — Operators can register policies backed by
   $SURGE stake, creating an economic incentive for high-quality rules.

3. **Governance Receipts** — Every evaluation produces a signed receipt
   suitable for on-chain attestation (compliance proof).

This module demonstrates how runtime AI governance can integrate with
tokenised agent economies — a key differentiator for the SURGE × OpenClaw
hackathon's "Compliance-Ready Tokenization" track.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth.dependencies import require_any, require_operator
from ..config import settings
from ..models import User

router = APIRouter(prefix="/surge", tags=["surge"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GovernanceReceipt(BaseModel):
    """Signed receipt of a governance evaluation — suitable for on-chain attestation."""
    receipt_id: str = Field(description="Unique receipt identifier")
    timestamp: str = Field(description="ISO-8601 evaluation timestamp")
    tool: str = Field(description="Tool that was evaluated")
    decision: str = Field(description="allow | block | review")
    risk_score: int = Field(ge=0, le=100)
    policy_ids: List[str] = Field(default_factory=list)
    chain_pattern: Optional[str] = None
    agent_id: Optional[str] = None
    digest: str = Field(description="SHA-256 digest of receipt payload for integrity verification")
    governance_fee_surge: Optional[str] = Field(
        default=None,
        description="$SURGE micro-fee charged for this evaluation (null if fee gating disabled)",
    )


class PolicyStake(BaseModel):
    """A policy backed by $SURGE token stake."""
    policy_id: str
    description: str
    severity: int = Field(ge=0, le=100)
    staked_surge: str = Field(description="Amount of $SURGE staked on this policy")
    staker_wallet: str = Field(description="Wallet address of the policy staker")
    created_at: str
    effectiveness_score: float = Field(
        default=0.0,
        ge=0.0, le=100.0,
        description="Computed effectiveness: (matches / total_evaluations) × 100",
    )


class StakePolicyRequest(BaseModel):
    policy_id: str
    description: str
    severity: int = Field(ge=0, le=100)
    match_json: dict = Field(default_factory=dict)
    action: str = Field(pattern="^(allow|block|review)$")
    surge_amount: str = Field(description="$SURGE tokens to stake")
    wallet_address: str = Field(description="Staker's wallet address")


class SurgeGovernanceStatus(BaseModel):
    """Status of the SURGE governance integration."""
    fee_gating_enabled: bool
    governance_fee_per_eval: str
    total_receipts_issued: int
    total_staked_policies: int
    total_surge_staked: str
    surge_wallet: str


# ---------------------------------------------------------------------------
# In-memory store (production would use DB + on-chain verification)
# ---------------------------------------------------------------------------

_receipts: List[GovernanceReceipt] = []
_staked_policies: List[PolicyStake] = []

# Governance fee: 0.001 SURGE per evaluation (micro-fee model)
_GOVERNANCE_FEE = "0.001"


def _compute_digest(
    receipt_id: str,
    timestamp: str,
    tool: str,
    decision: str,
    risk_score: int,
    policy_ids: List[str],
) -> str:
    """SHA-256 digest of receipt payload for integrity verification."""
    payload = f"{receipt_id}|{timestamp}|{tool}|{decision}|{risk_score}|{','.join(policy_ids)}"
    return sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Public: create receipt from evaluation (called by engine)
# ---------------------------------------------------------------------------

def create_governance_receipt(
    tool: str,
    decision: str,
    risk_score: int,
    policy_ids: List[str],
    chain_pattern: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> GovernanceReceipt:
    """Create a governance receipt for an evaluation.

    This receipt can be submitted on-chain as a compliance attestation,
    proving that a specific tool call was evaluated by the governor
    before execution.
    """
    receipt_id = f"ocg-{uuid4().hex[:16]}"
    timestamp = datetime.now(timezone.utc).isoformat()

    digest = _compute_digest(receipt_id, timestamp, tool, decision, risk_score, policy_ids)

    fee = _GOVERNANCE_FEE if settings.surge_governance_fee_enabled else None

    receipt = GovernanceReceipt(
        receipt_id=receipt_id,
        timestamp=timestamp,
        tool=tool,
        decision=decision,
        risk_score=risk_score,
        policy_ids=policy_ids,
        chain_pattern=chain_pattern,
        agent_id=agent_id,
        digest=digest,
        governance_fee_surge=fee,
    )
    _receipts.append(receipt)
    return receipt


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/status", response_model=SurgeGovernanceStatus)
def surge_status(_user: User = Depends(require_any)) -> SurgeGovernanceStatus:
    """Return current SURGE governance integration status."""
    total_staked = sum(float(p.staked_surge) for p in _staked_policies)
    return SurgeGovernanceStatus(
        fee_gating_enabled=settings.surge_governance_fee_enabled,
        governance_fee_per_eval=_GOVERNANCE_FEE,
        total_receipts_issued=len(_receipts),
        total_staked_policies=len(_staked_policies),
        total_surge_staked=f"{total_staked:.4f}",
        surge_wallet=settings.surge_wallet_address or "(not configured)",
    )


@router.get("/receipts", response_model=List[GovernanceReceipt])
def list_receipts(
    limit: int = 50,
    _user: User = Depends(require_any),
) -> List[GovernanceReceipt]:
    """List recent governance receipts (newest first)."""
    return list(reversed(_receipts[-limit:]))


@router.get("/receipts/{receipt_id}", response_model=GovernanceReceipt)
def get_receipt(
    receipt_id: str,
    _user: User = Depends(require_any),
) -> GovernanceReceipt:
    """Retrieve a specific governance receipt by ID."""
    for r in _receipts:
        if r.receipt_id == receipt_id:
            return r
    raise HTTPException(status_code=404, detail="Receipt not found.")


@router.post("/policies/stake", response_model=PolicyStake, status_code=201)
def stake_policy(
    body: StakePolicyRequest,
    _user: User = Depends(require_operator),
) -> PolicyStake:
    """Stake $SURGE tokens on a policy.

    Creates a governance policy backed by an economic stake. Higher-stake
    policies signal higher confidence in the rule's importance.
    In production, this would verify the on-chain stake transaction.
    """
    # Check for duplicate
    for p in _staked_policies:
        if p.policy_id == body.policy_id:
            raise HTTPException(status_code=400, detail="Policy already staked.")

    stake = PolicyStake(
        policy_id=body.policy_id,
        description=body.description,
        severity=body.severity,
        staked_surge=body.surge_amount,
        staker_wallet=body.wallet_address,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _staked_policies.append(stake)
    return stake


@router.get("/policies/staked", response_model=List[PolicyStake])
def list_staked_policies(
    _user: User = Depends(require_any),
) -> List[PolicyStake]:
    """List all policies with $SURGE token stakes."""
    return _staked_policies


@router.delete("/policies/stake/{policy_id}")
def unstake_policy(
    policy_id: str,
    _user: User = Depends(require_operator),
) -> dict:
    """Remove a policy stake (returns $SURGE to staker)."""
    for i, p in enumerate(_staked_policies):
        if p.policy_id == policy_id:
            removed = _staked_policies.pop(i)
            return {
                "status": "unstaked",
                "policy_id": policy_id,
                "surge_returned": removed.staked_surge,
            }
    raise HTTPException(status_code=404, detail="Staked policy not found.")
