"""
Shared pytest fixtures for the backend test suite.

The `db` fixture gives each test a fresh in-memory SQLite database with all app
tables created from the ORM metadata — no migrations, no touching the live
shoe_deals.db. Used by the service-level and model-level tests; the HTTP-layer
tests (test_auth, test_http_smoke) build their own StaticPool engine and
override `get_db` instead, since they drive the app through the ASGI stack.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import models  # noqa: F401 — registers tables on Base.metadata


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
