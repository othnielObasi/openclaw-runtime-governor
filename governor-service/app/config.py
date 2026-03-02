from __future__ import annotations

import sys
from functools import lru_cache
from typing import List

from pydantic import ConfigDict, field_validator
from pydantic_settings import BaseSettings


_DEFAULT_JWT_SECRET = "change-me-in-production-use-long-random-string"


class Settings(BaseSettings):
    model_config = ConfigDict(env_prefix="GOVERNOR_")

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
    registration_enabled: bool = True  # Set False in production to disable public signup

    # Rate limiting
    login_rate_limit: str = "5/minute"
    evaluate_rate_limit: str = "120/minute"

    # SURGE integration
    surge_governance_fee_enabled: bool = False
    surge_wallet_address: str = ""

    # ── Compliance modules ──────────────────────────────────────────
    modules_enabled: bool = True                       # Master toggle for all optional modules

    # Injection detector (replaces legacy regex firewall)
    injection_detector_enabled: bool = True
    injection_similarity_threshold: float = 0.25

    # PII scanner
    pii_scanner_enabled: bool = True
    pii_risk_boost_per_finding: float = 15.0
    pii_max_risk_boost: float = 50.0
    pii_min_confidence: float = 0.60

    # Budget enforcer
    budget_enforcer_enabled: bool = True
    budget_max_evals_per_session: int = 500
    budget_max_evals_per_hour: int = 1000
    budget_max_evals_per_day: int = 10000
    budget_circuit_breaker_cooldown: float = 300.0

    # Metrics (Prometheus + JSON)
    metrics_enabled: bool = True

    # Compliance exporter
    compliance_exporter_enabled: bool = True

    # Agent fingerprinting
    fingerprinting_enabled: bool = True

    # SURGE v2
    surge_v2_enabled: bool = False                     # Opt-in: replaces v1 receipts
    surge_v2_org: str = "openclaw"
    surge_v2_checkpoint_interval: int = 100

    # Impact assessment
    impact_assessment_enabled: bool = True

    # SIEM integration
    siem_enabled: bool = False                         # Opt-in: requires target URL
    siem_target_url: str = ""
    siem_auth_header: str = ""
    siem_min_severity: str = "medium"                   # low | medium | high | critical

    # Encryption key for notification channel secrets (Fernet key)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str = ""

    # Logging
    log_format: str = "json"  # "json" or "text"

    # SSE
    max_sse_subscribers: int = 500

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

    @field_validator("allow_cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: List[str], info) -> List[str]:
        """Refuse to start in production with CORS wildcard."""
        env = info.data.get("environment", "development")
        if env != "development" and v == ["*"]:
            print(
                "\n🚨 WARNING: GOVERNOR_ALLOW_CORS_ORIGINS is set to ['*'].\n"
                "   Set GOVERNOR_ALLOW_CORS_ORIGINS to your dashboard URL in production.\n",
                file=sys.stderr,
            )
            raise ValueError(
                "CORS origins wildcard ['*'] not allowed in non-development environments. "
                "Set GOVERNOR_ALLOW_CORS_ORIGINS env var."
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Module-level singleton for convenience
settings = get_settings()
