from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .core import hash_password, verify_password, create_access_token, generate_api_key
from .dependencies import get_current_user, require_admin, require_superadmin
from ..config import settings
from ..database import db_session
from ..models import User, LoginHistory
from ..rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    name: str


class UserRead(BaseModel):
    id: int
    username: str
    name: str
    role: str
    is_active: bool
    api_key: Optional[str] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None
    login_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class LoginHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    username: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    method: str
    created_at: datetime


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6)


class UserCreate(BaseModel):
    username: str
    name: str
    password: str
    role: str = Field(default="operator", pattern="^(superadmin|admin|operator|auditor)$")


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = Field(default=None, pattern="^(superadmin|admin|operator|auditor)$")
    is_active: Optional[bool] = None
    password: Optional[str] = None


class MeResponse(BaseModel):
    username: str
    name: str
    role: str
    api_key: Optional[str] = None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, body: LoginRequest) -> TokenResponse:
    with db_session() as session:
        user = session.execute(
            select(User).where(User.username == body.username)
        ).scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid credentials.")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid credentials.")

    # Track login history
    with db_session() as session:
        user_row = session.get(User, user.id)
        if user_row:
            user_row.last_login_at = datetime.now(timezone.utc)
            user_row.login_count = (user_row.login_count or 0) + 1

        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")[:512]
        history = LoginHistory(
            user_id=user.id,
            username=user.username,
            ip_address=ip,
            user_agent=ua,
            method="jwt",
        )
        session.add(history)

    token = create_access_token(subject=user.username, role=user.role)
    return TokenResponse(
        access_token=token,
        role=user.role,
        username=user.username,
        name=user.name,
    )


# ---------------------------------------------------------------------------
# Public signup — creates an operator account (no admin required)
# ---------------------------------------------------------------------------

@router.post("/signup", response_model=TokenResponse, status_code=201)
@limiter.limit("3/minute")
def signup(request: Request, body: SignupRequest) -> TokenResponse:
    if not settings.registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is disabled. Contact an administrator.",
        )
    with db_session() as session:
        existing = session.execute(
            select(User).where(User.username == body.username)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this username already exists.",
            )

        user = User(
            username=body.username,
            name=body.name,
            password_hash=hash_password(body.password),
            role="operator",
            api_key=generate_api_key(),
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.refresh(user)

        token = create_access_token(subject=user.username, role=user.role)
        return TokenResponse(
            access_token=token,
            role=user.role,
            username=user.username,
            name=user.name,
        )


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        username=current_user.username,
        name=current_user.name,
        role=current_user.role,
        api_key=current_user.api_key,
    )


# ---------------------------------------------------------------------------
# User management — admin only
# ---------------------------------------------------------------------------

@router.get("/users", response_model=List[UserRead])
def list_users(admin: User = Depends(require_superadmin)) -> List[UserRead]:
    with db_session() as session:
        users = session.execute(select(User).order_by(User.created_at)).scalars().all()
        return [UserRead.model_validate(u) for u in users]


@router.post("/users", response_model=UserRead, status_code=201)
def create_user(body: UserCreate, admin: User = Depends(require_superadmin)) -> UserRead:
    with db_session() as session:
        existing = session.execute(
            select(User).where(User.username == body.username)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Username already registered.")
        user = User(
            username=body.username,
            name=body.name,
            password_hash=hash_password(body.password),
            role=body.role,
            api_key=generate_api_key(),
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.refresh(user)
        return UserRead.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    body: UserUpdate,
    admin: User = Depends(require_superadmin),
) -> UserRead:
    with db_session() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        if body.name is not None:
            user.name = body.name
        if body.role is not None:
            user.role = body.role
        if body.is_active is not None:
            user.is_active = body.is_active
        if body.password is not None:
            user.password_hash = hash_password(body.password)
        session.flush()
        session.refresh(user)
        return UserRead.model_validate(user)


@router.delete("/users/{user_id}", status_code=204)
def revoke_user(user_id: int, admin: User = Depends(require_superadmin)) -> None:
    with db_session() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        # Soft delete — deactivate rather than drop row (preserves audit trail)
        user.is_active = False


@router.post("/users/{user_id}/rotate-key", response_model=UserRead)
def rotate_api_key(user_id: int, admin: User = Depends(require_superadmin)) -> UserRead:
    with db_session() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        user.api_key = generate_api_key()
        session.flush()
        session.refresh(user)
        return UserRead.model_validate(user)


# ---------------------------------------------------------------------------
# Login history — superadmin only
# ---------------------------------------------------------------------------

@router.get("/login-history", response_model=List[LoginHistoryRead])
def all_login_history(
    limit: int = 100,
    admin: User = Depends(require_superadmin),
) -> List[LoginHistoryRead]:
    """Return recent login history across all users (superadmin only)."""
    with db_session() as session:
        rows = (
            session.execute(
                select(LoginHistory)
                .order_by(LoginHistory.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [LoginHistoryRead.model_validate(r) for r in rows]


@router.get("/users/{user_id}/login-history", response_model=List[LoginHistoryRead])
def user_login_history(
    user_id: int,
    limit: int = 50,
    admin: User = Depends(require_superadmin),
) -> List[LoginHistoryRead]:
    """Return login history for a specific user (superadmin only)."""
    with db_session() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        rows = (
            session.execute(
                select(LoginHistory)
                .where(LoginHistory.user_id == user_id)
                .order_by(LoginHistory.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [LoginHistoryRead.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Self-service API key management — any authenticated user
# ---------------------------------------------------------------------------

@router.post("/me/rotate-key", response_model=MeResponse)
def rotate_own_key(current_user: User = Depends(get_current_user)) -> MeResponse:
    """Let authenticated users regenerate their own API key."""
    with db_session() as session:
        user = session.get(User, current_user.id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        user.api_key = generate_api_key()
        session.flush()
        session.refresh(user)
        return MeResponse(
            username=user.username,
            name=user.name,
            role=user.role,
            api_key=user.api_key,
        )
