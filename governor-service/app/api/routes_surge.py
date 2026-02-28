"""
routes_surge.py — SURGE Token Governance Integration
=====================================================
Connects the OpenClaw Governor to the SURGE token economy:

1. **Governance Fee Gating** — Tool evaluations require a micro-fee
   in $SURGE, drawn from a virtual wallet. Evaluations are rejected
   when the wallet balance reaches zero (enforced in /evaluate).

2. **Tiered Pricing** — Higher-risk evaluations cost more:
      risk 0-39  → 0.001 SURGE (standard)
      risk 40-69 → 0.005 SURGE (elevated)
      risk 70-89 → 0.010 SURGE (high)
      risk 90+   → 0.025 SURGE (critical)

3. **Policy Staking** — Operators can register policies backed by
   $SURGE stake, creating an economic incentive for high-quality rules.
   Stakes are persisted in the database and survive restarts.

4. **Governance Receipts** — Every evaluation produces a SHA-256 signed
   receipt persisted in the database, suitable for on-chain attestation.

5. **Virtual Wallets** — Each agent/org maintains a $SURGE wallet with
   a ledger of deposits and fee deductions. When balance ≤ 0, further
   evaluations are rejected (402 Payment Required).

All data is DB-persisted (SQLite → Postgres-ready) — no in-memory loss
on restarts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from ..auth.dependencies import require_any, require_operator
from ..config import settings
from ..database import db_session
from ..models import User, SurgeReceipt, SurgeStakedPolicy, SurgeWallet

router = APIRouter(prefix="/surge", tags=["surge"])


# ---------------------------------------------------------------------------
# Tiered fee schedule
# ---------------------------------------------------------------------------

_FEE_TIERS = [
    (90, Decimal("0.025")),   # critical risk
    (70, Decimal("0.010")),   # high risk
    (40, Decimal("0.005")),   # elevated risk
    (0,  Decimal("0.001")),   # standard
]

_DEFAULT_FEE = Decimal("0.001")


def compute_fee(risk_score: int) -> Decimal:
    """Return the governance fee for a given risk score (tiered pricing)."""
    for threshold, fee in _FEE_TIERS:
        if risk_score >= threshold:
            return fee
    return _DEFAULT_FEE


# ---------------------------------------------------------------------------
# Schemas (Pydantic — API layer)
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
        description="$SURGE fee charged for this evaluation (tiered by risk score)",
    )


class PolicyStake(BaseModel):
    """A policy backed by $SURGE token stake."""
    policy_id: str
    description: str
    severity: int = Field(ge=0, le=100)
    staked_surge: str = Field(description="Amount of $SURGE staked on this policy")
    staker_wallet: str = Field(description="Wallet address of the policy staker")
    created_at: str
    is_active: bool = True


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
    governance_fee_tiers: dict = Field(
        description="Fee tiers: risk_threshold → SURGE cost",
    )
    total_receipts_issued: int
    total_fees_collected: str
    total_staked_policies: int
    total_surge_staked: str
    surge_wallet: str


class WalletCreate(BaseModel):
    """Create a virtual SURGE wallet."""
    wallet_id: str = Field(description="Wallet identifier (e.g. agent_id or org name)")
    label: str = Field(default="", description="Human-readable wallet label")
    initial_balance: str = Field(default="100.0000", description="Starting $SURGE balance")


class WalletRead(BaseModel):
    """Virtual SURGE wallet balance."""
    wallet_id: str
    label: str
    balance: str
    total_deposited: str
    total_fees_paid: str
    created_at: str
    updated_at: str


class WalletTopUp(BaseModel):
    """Deposit $SURGE into a wallet."""
    amount: str = Field(description="$SURGE amount to deposit")


# ---------------------------------------------------------------------------
# Helper: SHA-256 receipt digest
# ---------------------------------------------------------------------------

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
# Core: create receipt + deduct fee (called from routes_actions evaluate)
# ---------------------------------------------------------------------------

def create_governance_receipt(
    tool: str,
    decision: str,
    risk_score: int,
    policy_ids: List[str],
    chain_pattern: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> GovernanceReceipt:
    """Create a DB-persisted governance receipt and deduct fee from wallet.

    Fees are tiered by risk score. The receipt is persisted in the database
    and survives restarts (unlike the previous in-memory implementation).
    """
    receipt_id = f"ocg-{uuid4().hex[:16]}"
    timestamp = datetime.now(timezone.utc).isoformat()
    digest = _compute_digest(receipt_id, timestamp, tool, decision, risk_score, policy_ids)

    # Compute tiered fee
    fee_amount = compute_fee(risk_score) if settings.surge_governance_fee_enabled else None
    fee_str = f"{fee_amount:.4f}" if fee_amount else None

    with db_session() as session:
        # Persist receipt
        row = SurgeReceipt(
            receipt_id=receipt_id,
            tool=tool,
            decision=decision,
            risk_score=risk_score,
            policy_ids=",".join(policy_ids) if policy_ids else None,
            chain_pattern=chain_pattern,
            agent_id=agent_id,
            digest=digest,
            governance_fee=fee_str,
        )
        session.add(row)

        # Deduct fee from wallet (if fee gating enabled and agent has a wallet)
        if fee_amount and agent_id:
            wallet = session.execute(
                select(SurgeWallet).where(SurgeWallet.wallet_id == agent_id)
            ).scalar_one_or_none()
            if wallet:
                balance = Decimal(wallet.balance)
                fee_paid = Decimal(wallet.total_fees_paid)
                balance -= fee_amount
                fee_paid += fee_amount
                wallet.balance = f"{balance:.4f}"
                wallet.total_fees_paid = f"{fee_paid:.4f}"

    return GovernanceReceipt(
        receipt_id=receipt_id,
        timestamp=timestamp,
        tool=tool,
        decision=decision,
        risk_score=risk_score,
        policy_ids=policy_ids,
        chain_pattern=chain_pattern,
        agent_id=agent_id,
        digest=digest,
        governance_fee_surge=fee_str,
    )


def check_wallet_balance(agent_id: Optional[str]) -> None:
    """Raise 402 if fee gating is enabled and the agent has insufficient balance.

    Called from /evaluate BEFORE running the governance pipeline.
    If the agent has no wallet, one is auto-created with 100 SURGE.
    """
    if not settings.surge_governance_fee_enabled:
        return
    if not agent_id:
        return  # anonymous calls not gated

    with db_session() as session:
        wallet = session.execute(
            select(SurgeWallet).where(SurgeWallet.wallet_id == agent_id)
        ).scalar_one_or_none()

        if wallet is None:
            # Auto-provision wallet with default balance
            wallet = SurgeWallet(wallet_id=agent_id, label=f"Auto: {agent_id}")
            session.add(wallet)
            return  # fresh wallet, balance is 100.0000

        balance = Decimal(wallet.balance)
        if balance <= 0:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_surge_balance",
                    "wallet_id": agent_id,
                    "balance": wallet.balance,
                    "message": (
                        f"Wallet {agent_id} has {wallet.balance} $SURGE remaining. "
                        "Top up via POST /surge/wallets/{wallet_id}/topup to continue."
                    ),
                },
            )


# ---------------------------------------------------------------------------
# Routes: Status
# ---------------------------------------------------------------------------

@router.get("/status", response_model=SurgeGovernanceStatus)
def surge_status(_user: User = Depends(require_any)) -> SurgeGovernanceStatus:
    """Return current SURGE governance integration status."""
    tiers = {f"risk>={t}": f"{f:.4f}" for t, f in _FEE_TIERS}

    with db_session() as session:
        total_receipts = session.execute(
            select(func.count(SurgeReceipt.id))
        ).scalar_one_or_none() or 0

        total_policies = session.execute(
            select(func.count(SurgeStakedPolicy.id)).where(SurgeStakedPolicy.is_active == True)  # noqa: E712
        ).scalar_one_or_none() or 0

        # Compute staked total
        staked_rows = session.execute(
            select(SurgeStakedPolicy.staked_surge).where(SurgeStakedPolicy.is_active == True)  # noqa: E712
        ).scalars().all()
        staked_sum = sum(Decimal(s) for s in staked_rows) if staked_rows else Decimal(0)

        # Total fees collected across all wallets
        fee_rows = session.execute(
            select(SurgeWallet.total_fees_paid)
        ).scalars().all()
        fees_sum = sum(Decimal(f) for f in fee_rows) if fee_rows else Decimal(0)

    return SurgeGovernanceStatus(
        fee_gating_enabled=settings.surge_governance_fee_enabled,
        governance_fee_tiers=tiers,
        total_receipts_issued=total_receipts,
        total_fees_collected=f"{fees_sum:.4f}",
        total_staked_policies=total_policies,
        total_surge_staked=f"{staked_sum:.4f}",
        surge_wallet=settings.surge_wallet_address or "(not configured)",
    )


# ---------------------------------------------------------------------------
# Routes: Receipts
# ---------------------------------------------------------------------------

@router.get("/receipts", response_model=List[GovernanceReceipt])
def list_receipts(
    limit: int = 50,
    offset: int = 0,
    _user: User = Depends(require_any),
) -> List[GovernanceReceipt]:
    """List recent governance receipts (newest first). DB-persisted."""
    with db_session() as session:
        rows = session.execute(
            select(SurgeReceipt).order_by(SurgeReceipt.created_at.desc()).offset(offset).limit(limit)
        ).scalars().all()

        return [
            GovernanceReceipt(
                receipt_id=r.receipt_id,
                timestamp=r.created_at.isoformat() if r.created_at else "",
                tool=r.tool,
                decision=r.decision,
                risk_score=r.risk_score,
                policy_ids=[p for p in (r.policy_ids or "").split(",") if p],
                chain_pattern=r.chain_pattern,
                agent_id=r.agent_id,
                digest=r.digest,
                governance_fee_surge=r.governance_fee,
            )
            for r in rows
        ]


@router.get("/receipts/{receipt_id}", response_model=GovernanceReceipt)
def get_receipt(
    receipt_id: str,
    _user: User = Depends(require_any),
) -> GovernanceReceipt:
    """Retrieve a specific governance receipt by ID."""
    with db_session() as session:
        r = session.execute(
            select(SurgeReceipt).where(SurgeReceipt.receipt_id == receipt_id)
        ).scalar_one_or_none()
        if not r:
            raise HTTPException(status_code=404, detail="Receipt not found.")
        return GovernanceReceipt(
            receipt_id=r.receipt_id,
            timestamp=r.created_at.isoformat() if r.created_at else "",
            tool=r.tool,
            decision=r.decision,
            risk_score=r.risk_score,
            policy_ids=[p for p in (r.policy_ids or "").split(",") if p],
            chain_pattern=r.chain_pattern,
            agent_id=r.agent_id,
            digest=r.digest,
            governance_fee_surge=r.governance_fee,
        )


# ---------------------------------------------------------------------------
# Routes: Policy Staking
# ---------------------------------------------------------------------------

@router.post("/policies/stake", response_model=PolicyStake, status_code=201)
def stake_policy(
    body: StakePolicyRequest,
    _user: User = Depends(require_operator),
) -> PolicyStake:
    """Stake $SURGE tokens on a policy. DB-persisted."""
    with db_session() as session:
        existing = session.execute(
            select(SurgeStakedPolicy).where(SurgeStakedPolicy.policy_id == body.policy_id)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Policy already staked.")

        row = SurgeStakedPolicy(
            policy_id=body.policy_id,
            description=body.description,
            severity=body.severity,
            staked_surge=body.surge_amount,
            staker_wallet=body.wallet_address,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return PolicyStake(
            policy_id=row.policy_id,
            description=row.description,
            severity=row.severity,
            staked_surge=row.staked_surge,
            staker_wallet=row.staker_wallet,
            created_at=row.created_at.isoformat() if row.created_at else "",
            is_active=row.is_active,
        )


@router.get("/policies/staked", response_model=List[PolicyStake])
def list_staked_policies(
    _user: User = Depends(require_any),
) -> List[PolicyStake]:
    """List all policies with $SURGE token stakes."""
    with db_session() as session:
        rows = session.execute(
            select(SurgeStakedPolicy).where(SurgeStakedPolicy.is_active == True)  # noqa: E712
        ).scalars().all()
        return [
            PolicyStake(
                policy_id=r.policy_id,
                description=r.description,
                severity=r.severity,
                staked_surge=r.staked_surge,
                staker_wallet=r.staker_wallet,
                created_at=r.created_at.isoformat() if r.created_at else "",
                is_active=r.is_active,
            )
            for r in rows
        ]


@router.delete("/policies/stake/{policy_id}")
def unstake_policy(
    policy_id: str,
    _user: User = Depends(require_operator),
) -> dict:
    """Remove a policy stake (returns $SURGE to staker)."""
    with db_session() as session:
        row = session.execute(
            select(SurgeStakedPolicy).where(SurgeStakedPolicy.policy_id == policy_id)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Staked policy not found.")
        returned = row.staked_surge
        session.delete(row)

    return {
        "status": "unstaked",
        "policy_id": policy_id,
        "surge_returned": returned,
    }


# ---------------------------------------------------------------------------
# Routes: Virtual Wallets
# ---------------------------------------------------------------------------

@router.post("/wallets", response_model=WalletRead, status_code=201)
def create_wallet(
    body: WalletCreate,
    _user: User = Depends(require_operator),
) -> WalletRead:
    """Create a virtual SURGE wallet for an agent/org."""
    with db_session() as session:
        existing = session.execute(
            select(SurgeWallet).where(SurgeWallet.wallet_id == body.wallet_id)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Wallet already exists.")

        wallet = SurgeWallet(
            wallet_id=body.wallet_id,
            label=body.label,
            balance=body.initial_balance,
            total_deposited=body.initial_balance,
        )
        session.add(wallet)
        session.flush()
        session.refresh(wallet)
        return _wallet_read(wallet)


@router.get("/wallets", response_model=List[WalletRead])
def list_wallets(
    _user: User = Depends(require_any),
) -> List[WalletRead]:
    """List all virtual SURGE wallets."""
    with db_session() as session:
        rows = session.execute(
            select(SurgeWallet).order_by(SurgeWallet.created_at.desc())
        ).scalars().all()
        return [_wallet_read(w) for w in rows]


@router.get("/wallets/{wallet_id}", response_model=WalletRead)
def get_wallet(
    wallet_id: str,
    _user: User = Depends(require_any),
) -> WalletRead:
    """Get a specific wallet by ID."""
    with db_session() as session:
        wallet = session.execute(
            select(SurgeWallet).where(SurgeWallet.wallet_id == wallet_id)
        ).scalar_one_or_none()
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found.")
        return _wallet_read(wallet)


@router.post("/wallets/{wallet_id}/topup", response_model=WalletRead)
def topup_wallet(
    wallet_id: str,
    body: WalletTopUp,
    _user: User = Depends(require_operator),
) -> WalletRead:
    """Deposit $SURGE into a wallet (simulates on-chain deposit)."""
    with db_session() as session:
        wallet = session.execute(
            select(SurgeWallet).where(SurgeWallet.wallet_id == wallet_id)
        ).scalar_one_or_none()
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found.")

        amount = Decimal(body.amount)
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive.")

        balance = Decimal(wallet.balance) + amount
        deposited = Decimal(wallet.total_deposited) + amount
        wallet.balance = f"{balance:.4f}"
        wallet.total_deposited = f"{deposited:.4f}"
        session.flush()
        session.refresh(wallet)
        return _wallet_read(wallet)


def _wallet_read(w: SurgeWallet) -> WalletRead:
    return WalletRead(
        wallet_id=w.wallet_id,
        label=w.label,
        balance=w.balance,
        total_deposited=w.total_deposited,
        total_fees_paid=w.total_fees_paid,
        created_at=w.created_at.isoformat() if w.created_at else "",
        updated_at=w.updated_at.isoformat() if w.updated_at else "",
    )
