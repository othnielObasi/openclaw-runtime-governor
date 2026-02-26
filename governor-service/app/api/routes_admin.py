from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth.dependencies import require_admin, require_any
from ..models import User
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
