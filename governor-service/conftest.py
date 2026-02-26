"""
pytest configuration – initialise database tables before tests run.
"""
import pytest
from app.database import Base, engine
from app import models  # noqa: F401 – registers ORM mappings with Base.metadata


@pytest.fixture(autouse=True, scope="session")
def create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
