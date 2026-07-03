"""
Pytest fixtures for the Strava-import test suite.

Each test gets a fresh in-memory SQLite database with all app tables created
from the ORM metadata — no migrations, no touching the real shoe_deals.db.
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
