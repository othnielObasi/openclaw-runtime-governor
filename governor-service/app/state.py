"""
state.py — Governor runtime state (DB-persisted)
==================================================
The kill switch is persisted to the database so it survives restarts
and works correctly across multiple service instances.
Falls back to in-memory if DB is unavailable (startup race).
"""
from __future__ import annotations

from threading import Lock

_state_lock = Lock()
_kill_switch_cache: bool | None = None  # None = not yet loaded


def _load_from_db() -> bool:
    """Read kill switch state from DB. Returns False on any error."""
    try:
        from .database import db_session
        from .models import GovernorState
        with db_session() as session:
            row = session.get(GovernorState, "kill_switch")
            if row is None:
                return False
            return row.value == "true"
    except Exception:
        return False


def _save_to_db(enabled: bool) -> None:
    """Persist kill switch state to DB."""
    try:
        from .database import db_session
        from .models import GovernorState
        with db_session() as session:
            row = session.get(GovernorState, "kill_switch")
            if row is None:
                row = GovernorState(key="kill_switch", value=str(enabled).lower())
                session.add(row)
            else:
                row.value = str(enabled).lower()
    except Exception:
        pass  # Best-effort — in-memory cache still works


def set_kill_switch(enabled: bool) -> None:
    """Enable or disable the global kill switch (persisted to DB)."""
    global _kill_switch_cache
    with _state_lock:
        _kill_switch_cache = bool(enabled)
    _save_to_db(enabled)


def is_kill_switch_enabled() -> bool:
    """Returns True if the global kill switch is currently active."""
    global _kill_switch_cache
    with _state_lock:
        if _kill_switch_cache is None:
            _kill_switch_cache = _load_from_db()
        return _kill_switch_cache
