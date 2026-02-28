from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import settings
from .database import Base, engine
from .rate_limit import limiter
from .api import routes_actions, routes_policies, routes_summary, routes_admin, routes_surge, routes_stream, routes_traces, routes_notifications, routes_verify
from .auth.routes_auth import router as auth_router
from .auth.seed import seed_admin
from .escalation.routes import router as escalation_router
from .escalation import models as _escalation_models  # noqa: F401 — register tables
from . import verification as _verification_models  # noqa: F401 — register VerificationLog table

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    """Configure structured JSON logging when log_format=json (default)."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        try:
            from pythonjsonlogger import jsonlogger
            formatter = jsonlogger.JsonFormatter(
                "%(asctime)s %(name)s %(levelname)s %(message)s",
                rename_fields={"asctime": "timestamp", "levelname": "level"},
            )
            handler.setFormatter(formatter)
        except ImportError:
            # Fall back to standard formatting if python-json-logger not available
            pass
    root.addHandler(handler)

_configure_logging()

# Initialise database tables on startup
Base.metadata.create_all(bind=engine)

# Seed default admin if no users exist
seed_admin()

app = FastAPI(
    title="OpenClaw Governor",
    version="0.4.0",
    description=(
        "Runtime governance, risk, and safety layer for OpenClaw agents. "
        "Intercepts tool calls and applies layered policy + neuro-risk evaluation "
        "with full RBAC, audit trail, and SURGE token governance integration."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allow_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(routes_actions.router)
app.include_router(routes_policies.router)
app.include_router(routes_summary.router)
app.include_router(routes_admin.router)
app.include_router(routes_surge.router)
app.include_router(routes_stream.router)
app.include_router(routes_traces.router)
app.include_router(escalation_router)
app.include_router(routes_notifications.router)
app.include_router(routes_verify.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"status": "ok", "service": "openclaw-governor", "version": "0.4.0"}


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "healthy"}


@app.get("/healthz", tags=["meta"])
def healthz() -> dict:
    """Lightweight health check for Fly.io / load balancer probes."""
    return {"status": "ok"}
