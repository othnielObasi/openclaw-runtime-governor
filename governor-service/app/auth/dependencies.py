from __future__ import annotations

from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from jose import JWTError
from sqlalchemy import select

from .core import decode_token
from ..database import db_session
from ..models import User

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ---------------------------------------------------------------------------
# Resolve current user from JWT or API key
# ---------------------------------------------------------------------------

def get_current_user(
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    api_key: str | None = Security(api_key_header),
    token: str | None = Query(None, description="JWT via query param (for SSE/EventSource)"),
) -> User:
    """
    Accepts any of:
      - Authorization: Bearer <jwt>
      - X-API-Key: ocg_<key>
      - ?token=<jwt>  (query param — needed for EventSource which can't set headers)
    Returns the matching User or raises 401.
    """
    # ── Try JWT from Authorization header first ────────────────
    jwt_token = (bearer.credentials if bearer and bearer.credentials else None) or token

    if jwt_token:
        try:
            payload = decode_token(jwt_token)
            username: str = payload.get("sub", "")
        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid or expired token.")
        with db_session() as session:
            user = session.execute(
                select(User).where(User.username == username)
            ).scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="User not found or inactive.")
        return user

    # ── Try API key ────────────────────────────────────────────
    if api_key:
        with db_session() as session:
            user = session.execute(
                select(User).where(User.api_key == api_key)
            ).scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid API key.")
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No credentials provided.",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ---------------------------------------------------------------------------
# Role guards
# ---------------------------------------------------------------------------

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("superadmin", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Admin access required.")
    return current_user


def require_superadmin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Superadmin access required.")
    return current_user


def require_operator(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("superadmin", "admin", "operator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Operator or Admin access required.")
    return current_user


def require_any(current_user: User = Depends(get_current_user)) -> User:
    """Any authenticated user — admin, operator, or auditor."""
    return current_user
