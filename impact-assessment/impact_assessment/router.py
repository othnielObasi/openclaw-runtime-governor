"""
Impact Assessment — FastAPI Router
Mount: app.include_router(router, prefix="/impact")
"""
from fastapi import APIRouter, Query
from typing import Optional

from . import ImpactAssessmentEngine, AssessmentPeriod

router = APIRouter(tags=["Impact Assessment"])
engine = ImpactAssessmentEngine()


@router.get("/assess")
async def full_assessment(period: str = Query("30d", regex="^(24h|7d|30d|90d|all)$")):
    """Full impact assessment report for the specified period."""
    p = AssessmentPeriod(period)
    return engine.assess(period=p).to_dict()


@router.get("/assess/agent/{agent_id}")
async def agent_assessment(agent_id: str,
                           period: str = Query("30d", regex="^(24h|7d|30d|90d|all)$")):
    """Risk profile for a specific agent."""
    p = AssessmentPeriod(period)
    return engine.assess_agent(agent_id, period=p).to_dict()


@router.get("/assess/tool/{tool}")
async def tool_assessment(tool: str,
                          period: str = Query("30d", regex="^(24h|7d|30d|90d|all)$")):
    """Risk profile for a specific tool."""
    p = AssessmentPeriod(period)
    return engine.assess_tool(tool, period=p).to_dict()


@router.get("/agents")
async def list_agents(period: str = Query("all", regex="^(24h|7d|30d|90d|all)$")):
    """List all agents with evaluation data."""
    p = AssessmentPeriod(period)
    return {"agents": engine.list_agents(period=p)}


@router.get("/tools")
async def list_tools(period: str = Query("all", regex="^(24h|7d|30d|90d|all)$")):
    """List all tools with evaluation data."""
    p = AssessmentPeriod(period)
    return {"tools": engine.list_tools(period=p)}
