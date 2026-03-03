"""
Fingerprinting — FastAPI Router
Mount: app.include_router(router, prefix="/fingerprint")
"""
from fastapi import APIRouter, Query
from typing import Any, Dict, List, Optional

from . import FingerprintEngine

router = APIRouter(tags=["Agent Fingerprinting"])
engine = FingerprintEngine()


@router.get("/agents")
async def list_fingerprinted_agents():
    """List all agents with behavioural fingerprints."""
    return {
        "agent_count": engine.agent_count,
        "total_evaluations": engine.total_evaluations,
        "agents": engine.list_agents(),
    }


@router.get("/agents/{agent_id}")
async def get_agent_fingerprint(agent_id: str):
    """Get detailed fingerprint for a specific agent."""
    fp = engine.get_fingerprint(agent_id)
    if fp is None:
        return {"error": "No fingerprint found for this agent", "agent_id": agent_id}
    return fp


@router.get("/agents/{agent_id}/maturity")
async def get_agent_maturity(agent_id: str):
    """Get fingerprint maturity level."""
    return {
        "agent_id": agent_id,
        "maturity": engine.get_maturity(agent_id),
    }


@router.delete("/agents/{agent_id}")
async def reset_agent_fingerprint(agent_id: str):
    """Reset an agent's fingerprint (start learning from scratch)."""
    engine.reset(agent_id)
    return {"status": "reset", "agent_id": agent_id}
