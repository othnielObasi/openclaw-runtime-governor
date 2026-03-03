from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth.dependencies import require_admin, require_any
from ..models import User
from ..modules import modules as gov_modules
from ..schemas import GovernorStatus
from ..state import is_kill_switch_enabled, set_kill_switch

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/status", response_model=GovernorStatus)
def get_status(_user: User = Depends(require_any)) -> GovernorStatus:
    """Return current governor runtime status."""
    return GovernorStatus(kill_switch=is_kill_switch_enabled())


@router.post("/kill", response_model=GovernorStatus)
def enable_kill_switch(_user: User = Depends(require_admin)) -> GovernorStatus:
    """Activate the global kill switch – blocks all subsequent actions."""
    set_kill_switch(True)
    return GovernorStatus(kill_switch=True)


@router.post("/resume", response_model=GovernorStatus)
def disable_kill_switch(_user: User = Depends(require_admin)) -> GovernorStatus:
    """Deactivate the global kill switch – resume normal evaluation."""
    set_kill_switch(False)
    return GovernorStatus(kill_switch=False)


@router.post("/budget/reset")
def reset_budget_circuit_breaker(
    agent_id: str = Query("anonymous", description="Agent whose circuit breaker to reset (default: anonymous)"),
    _user: User = Depends(require_admin),
):
    """Reset the budget enforcer's circuit breaker for an agent.

    This clears consecutive-block counters and disengages the circuit breaker
    so the agent can resume evaluations immediately.
    """
    enforcer = gov_modules.budget_enforcer
    if enforcer is None:
        return {"status": "noop", "detail": "Budget enforcer not loaded"}
    enforcer.reset_agent(agent_id)
    # Also persist the reset
    if enforcer._cb_save:
        try:
            enforcer._cb_save(agent_id, 0.0, 0)
        except Exception:
            pass
    return {"status": "ok", "agent_id": agent_id, "circuit_breaker_engaged": False}


@router.get("/budget/status")
def budget_status(_user: User = Depends(require_any)):
    """View budget enforcer status for all tracked agents."""
    enforcer = gov_modules.budget_enforcer
    if enforcer is None:
        return {"status": "disabled"}
    return enforcer.get_all_status()
