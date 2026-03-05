from __future__ import annotations

import os
import sys

from sqlalchemy import select

from .core import hash_password, generate_api_key
from ..database import db_session
from ..models import User


_DEFAULT_PASSWORD = "runtime_ocg"


def seed_admin() -> None:
    """
    Create a default admin account on first startup if no users exist.
    Credentials are read from environment variables so they can be
    overridden before deployment.

    Defaults (for local dev only — change before production):
      GOVERNOR_ADMIN_USERNAME = admin
      GOVERNOR_ADMIN_PASSWORD = changeme
      GOVERNOR_ADMIN_NAME     = Governor Admin
    """
    username = os.getenv("GOVERNOR_ADMIN_USERNAME", "openclaw_gov")
    password = os.getenv("GOVERNOR_ADMIN_PASSWORD", "runtime_ocg")
    name     = os.getenv("GOVERNOR_ADMIN_NAME",     "OpenClaw Governor")

    env = os.getenv("GOVERNOR_ENVIRONMENT", "development")

    with db_session() as session:
        # Only ensure the target account exists — never touch other users
        existing = session.execute(
            select(User).where(User.username == username)
        ).scalars().first()
        if existing:
            return  # Account already exists

        admin = User(
            username=username,
            name=name,
            password_hash=hash_password(password),
            role="superadmin",
            api_key=generate_api_key(),
            is_active=True,
        )
        session.add(admin)
        print(f"[seed] Created account: {username}")
