"""
PII Scanner — FastAPI Router
Mount: app.include_router(router, prefix="/pii")
"""
from fastapi import APIRouter, Body
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from . import PIIScanner, PIIEntityType

router = APIRouter(tags=["PII Scanner"])
_scanner = PIIScanner()


class PIIScanRequest(BaseModel):
    tool: str = Field(..., description="Tool name")
    args: Dict[str, Any] = Field(..., description="Tool arguments to scan")
    context: Optional[Dict[str, Any]] = Field(None, description="Optional context")
    result: Optional[Dict[str, Any]] = Field(None, description="Tool output to scan")
    enabled_entities: Optional[List[str]] = Field(None, description="Entity types to scan for")


class PIIScanResponse(BaseModel):
    input_scan: Dict[str, Any]
    output_scan: Optional[Dict[str, Any]] = None
    total_findings: int
    has_pii: bool
    risk_boost: float


@router.post("/scan", response_model=PIIScanResponse)
async def scan_for_pii(req: PIIScanRequest):
    """Scan tool call inputs and outputs for PII."""
    scanner = _scanner
    if req.enabled_entities:
        entities = {PIIEntityType(e) for e in req.enabled_entities if e in PIIEntityType.__members__.values()}
        scanner = PIIScanner(enabled_entities=entities)

    input_result = scanner.scan_input(req.tool, req.args, req.context)
    output_result = None
    if req.result:
        output_result = scanner.scan_output(req.result)

    total = len(input_result.findings) + (len(output_result.findings) if output_result else 0)
    boost = input_result.risk_boost + (output_result.risk_boost if output_result else 0)

    return PIIScanResponse(
        input_scan=input_result.to_dict(),
        output_scan=output_result.to_dict() if output_result else None,
        total_findings=total,
        has_pii=input_result.has_pii or (output_result.has_pii if output_result else False),
        risk_boost=min(boost, 50.0),
    )


@router.get("/entities")
async def list_entity_types():
    """List all supported PII entity types."""
    return {"entities": [e.value for e in PIIEntityType]}
