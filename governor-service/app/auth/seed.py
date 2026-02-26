from __future__ import annotations

import os
import sys

from sqlalchemy import select

from .core import hash_password, generate_api_key
from ..database import db_session
from ..models import User


_DEFAULT_PASSWORD = "changeme"


def seed_admin() -> None:
    """
    Create a default admin account on first startup if no users exist.
    Credentials are read from environment variables so they can be
    overridden before deployment.

    Defaults (for local dev only — change before production):
      GOVERNOR_ADMIN_EMAIL    = admin@openclaw.io
      GOVERNOR_ADMIN_PASSWORD = changeme
      GOVERNOR_ADMIN_NAME     = Governor Admin
    """
    email    = os.getenv("GOVERNOR_ADMIN_EMAIL",    "admin@openclaw.io")
    password = os.getenv("GOVERNOR_ADMIN_PASSWORD", _DEFAULT_PASSWORD)
    name     = os.getenv("GOVERNOR_ADMIN_NAME",     "Governor Admin")

    env = os.getenv("GOVERNOR_ENVIRONMENT", "development")

    with db_session() as session:
        existing = session.execute(select(User)).scalar_one_or_none()
        if existing:
            return  # Users already seeded — don't overwrite

        if password == _DEFAULT_PASSWORD:
            print(
                "\n⚠️  WARNING: Seeding admin with DEFAULT password 'changeme'.\n"
                "   Set GOVERNOR_ADMIN_PASSWORD before deploying to production.\n",
                file=sys.stderr,
            )
            if env != "development":
                print(
                    "🚨 REFUSING to seed default password in non-development "
                    f"environment ({env}).\n"
                    "   Set GOVERNOR_ADMIN_PASSWORD env var.\n",
                    file=sys.stderr,
                )
                return

        admin = User(
            email=email,
            name=name,
            password_hash=hash_password(password),
            role="admin",
            api_key=generate_api_key(),
            is_active=True,
        )
        session.add(admin)
        print(f"[seed] Default admin created: {email}")
