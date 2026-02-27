"""
pytest configuration – initialise database tables before tests run.
Provides shared session-scoped admin token to avoid rate limit issues.
"""
import pytest
from fastapi.testclient import TestClient
from app.database import Base, engine
from app import models  # noqa: F401 – registers ORM mappings with Base.metadata
from app.main import app


@pytest.fixture(autouse=True, scope="session")
def create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# Session-scoped admin token — login happens ONCE per test run
_session_token: str | None = None


@pytest.fixture(scope="session")
def admin_token() -> str:
    global _session_token
    if _session_token is None:
        client = TestClient(app)
        resp = client.post("/auth/login", json={"username": "admin", "password": "changeme"})
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        _session_token = resp.json()["access_token"]
    return _session_token
