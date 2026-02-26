from __future__ import annotations

import sys
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


_DEFAULT_JWT_SECRET = "change-me-in-production-use-long-random-string"


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./governor.db"
    log_sql: bool = False

    # Server
    environment: str = "development"
    log_level: str = "info"
    allow_cors_origins: List[str] = ["*"]

    # Policies
    policies_path: str = "app/policies/base_policies.yml"
    policy_cache_ttl_seconds: int = 10

    # Auth
    jwt_secret: str = _DEFAULT_JWT_SECRET
    jwt_expire_minutes: int = 480  # 8 hours

    # Rate limiting
    login_rate_limit: str = "5/minute"
    evaluate_rate_limit: str = "120/minute"

    # SURGE integration
    surge_governance_fee_enabled: bool = False
    surge_wallet_address: str = ""

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        """Refuse to start in production with the default JWT secret."""
        env = info.data.get("environment", "development")
        if env != "development" and v == _DEFAULT_JWT_SECRET:
            print(
                "\n🚨 FATAL: GOVERNOR_JWT_SECRET is set to the default value.\n"
                "   Set GOVERNOR_JWT_SECRET to a strong random string before "
                "running in production.\n"
                "   Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\"\n",
                file=sys.stderr,
            )
            raise ValueError(
                "JWT secret must be changed from default in non-development environments. "
                "Set GOVERNOR_JWT_SECRET env var."
            )
        return v

    class Config:
        env_prefix = "GOVERNOR_"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Module-level singleton for convenience
settings = get_settings()
