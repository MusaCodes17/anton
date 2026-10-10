"""
Shared pytest fixtures for the backend test suite.

The `db` fixture gives each test a fresh in-memory SQLite database with all app
tables created from the ORM metadata — no migrations, no touching the live
shoe_deals.db. Used by the service-level and model-level tests; the HTTP-layer
tests (test_auth, test_http_smoke) build their own StaticPool engine and
override `get_db` instead, since they drive the app through the ASGI stack.
"""
import os

# main.py reads ANTON_HOST_URL once, at import, to decide whether the OAuth
# routes exist — so whichever test module first imports app.main fixes that for
# the whole session. Set the OAuth env here (conftest loads before any test
# module, and before app.database's load_dotenv(), which never overrides) so
# the suite doesn't depend on test order or on a developer's backend/.env.
# Values match test_oauth.py's. test_auth.py still toggles ANTON_HOST_URL
# per-test for its dev-mode cases.
os.environ["ANTON_HOST_URL"] = "https://test.example.com"
os.environ["ANTON_OAUTH_CLIENT_ID"] = "test-client"
os.environ["ANTON_OAUTH_REDIRECT_URI"] = "https://test.example.com/callback"

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import models  # noqa: E402,F401 — registers tables on Base.metadata


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
