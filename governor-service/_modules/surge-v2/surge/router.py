"""
SURGE v2 — FastAPI Router
Mount: app.include_router(router, prefix="/surge")
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from . import SurgeEngine, SovereignConfig, GovernanceReceipt

router = APIRouter(tags=["SURGE Governance Receipts"])

# Default engine — will be replaced by module registry's engine when mounted
engine = SurgeEngine(config=SovereignConfig())


def set_engine(e: SurgeEngine) -> None:
    """Allow the governor-service to inject its configured engine."""
    global engine
    engine = e


class IssueRequest(BaseModel):
    tool: str
    decision: str = Field(pattern="^(allow|block|review)$")
    risk_score: int = Field(ge=0, le=100)
    explanation: str = ""
    policy_ids: List[str] = Field(default_factory=list)
    chain_pattern: Optional[str] = None
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    extra_context: Dict[str, Any] = Field(default_factory=dict)


@router.get("/status")
async def surge_status():
    """SURGE engine status and chain integrity."""
    return engine.status()


@router.post("/issue")
async def issue_receipt(req: IssueRequest):
    """Issue a new governance receipt."""
    receipt = engine.issue(
        tool=req.tool, decision=req.decision, risk_score=req.risk_score,
        explanation=req.explanation, policy_ids=req.policy_ids,
        chain_pattern=req.chain_pattern, agent_id=req.agent_id,
        session_id=req.session_id, extra_context=req.extra_context,
    )
    return receipt.to_dict()


@router.get("/receipts")
async def list_receipts(
    limit: int = Query(50, ge=1, le=500),
    agent_id: Optional[str] = None,
    decision: Optional[str] = None,
):
    """List recent governance receipts."""
    receipts = engine.get_receipts(limit=limit, agent_id=agent_id, decision=decision)
    return [r.to_dict() for r in receipts]


@router.get("/receipts/{receipt_id}")
async def get_receipt(receipt_id: str):
    """Get a specific receipt."""
    r = engine.get_receipt(receipt_id)
    if not r:
        raise HTTPException(404, "Receipt not found")
    return r.to_dict()


@router.get("/receipts/{receipt_id}/verify")
async def verify_receipt(receipt_id: str):
    """Verify a single receipt's integrity."""
    return engine.verify_single(receipt_id)


@router.post("/checkpoint")
async def create_checkpoint():
    """Create a Merkle tree checkpoint."""
    cp = engine.checkpoint()
    return cp.to_dict()


@router.get("/checkpoints")
async def list_checkpoints():
    """List all Merkle checkpoints."""
    return [cp.to_dict() for cp in engine.get_checkpoints()]


@router.get("/verify")
async def verify_chain():
    """Verify the entire receipt chain integrity."""
    result = engine.verify_chain()
    return result.to_dict()


@router.get("/export")
async def export_bundle(
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
):
    """Export auditor-ready compliance bundle."""
    bundle = engine.export(period_start=period_start, period_end=period_end)
    return JSONResponse(
        content=bundle.to_dict(),
        headers={"Content-Disposition": "attachment; filename=surge_compliance_bundle.json"},
    )
