"""COROS direct sync §2 — connect flow, encrypted token storage, locked refresh.

No network: the module's two HTTP seams (`_http_get_json`, `_http_post`) are
replaced with a scripted fake. Rules under test, not plumbing: rotation is
persisted, a dead refresh token stops everything (reauth_required, no retry
storm), concurrent refreshes burn at most one refresh token, state is
single-use, and tokens never appear in the status payload or in plaintext
at rest.
"""
import asyncio
import os
import threading
import time
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("ANTON_TOKENS", "desktop:test-coros-token-0123456789abcdef")

import httpx
import pytest
import requests
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import models  # noqa: F401
from app.models.models import CorosConnection, CorosOAuthState
from app.services import coros_connection as svc

META = {
    "authorization_endpoint": "https://c.test/oauth2/authorize",
    "token_endpoint": "https://c.test/oauth2/token",
    "registration_endpoint": "https://c.test/connect/register",
    "revocation_endpoint": "https://c.test/oauth2/revoke",
}


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeCoros:
    """Scripted token endpoint. Each refresh hands out the next numbered pair."""

    def __init__(self):
        self.posts = []          # (url, data/json)
        self.refresh_status = 200
        self.exchange_status = 200
        self.n = 0
        self.delay = 0.0
        self.revoke_status = 200
        self.revoke_raises = False

    def get(self, url):
        return META

    def post(self, url, *, json=None, data=None):
        self.posts.append((url, json if json is not None else data))
        if url == META["revocation_endpoint"]:
            if self.revoke_raises:
                raise requests.ConnectionError("down")
            return FakeResp(self.revoke_status)
        if url == META["registration_endpoint"]:
            return FakeResp(201, {"client_id": "client-1"})
        grant = (data or {}).get("grant_type")
        if grant == "authorization_code":
            if self.exchange_status != 200:
                return FakeResp(self.exchange_status)
            return FakeResp(200, self._tok())
        if self.delay:
            time.sleep(self.delay)
        if self.refresh_status != 200:
            return FakeResp(self.refresh_status)
        return FakeResp(200, self._tok())

    def _tok(self):
        self.n += 1
        return {"access_token": f"access-{self.n}", "refresh_token": f"refresh-{self.n}",
                "expires_in": 2591999, "scope": "mcp.tools openid offline_access"}

    def refresh_posts(self):
        return [p for p in self.posts if (p[1] or {}).get("grant_type") == "refresh_token"]


@pytest.fixture()
def fake(monkeypatch):
    f = FakeCoros()
    svc._as_metadata_cache.clear()
    monkeypatch.setattr(svc, "_http_get_json", f.get)
    monkeypatch.setattr(svc, "_http_post", f.post)
    monkeypatch.setenv("COROS_TOKEN_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ANTON_HOST_URL", "https://anton.test")
    return f


def _connect(db, fake):
    url = svc.start_connect(db)
    state = parse_qs(urlparse(url).query)["state"][0]
    svc.complete_connect(db, state=state, code="the-code")
    return url, state


# --- connect flow -------------------------------------------------------------

def test_start_connect_builds_pkce_url_and_registers_once(db, fake):
    url = svc.start_connect(db)
    q = parse_qs(urlparse(url).query)
    assert q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["https://anton.test/api/coros/callback"]
    assert q["resource"] == [svc.DEFAULT_MCP_URL]
    assert q["client_id"] == ["client-1"]
    svc.start_connect(db)
    regs = [p for p in fake.posts if p[0] == META["registration_endpoint"]]
    assert len(regs) == 1, "client_id must be reused, not re-registered"
    assert db.query(CorosOAuthState).count() == 2


def test_redirect_uri_change_reregisters(db, fake, monkeypatch):
    svc.start_connect(db)
    monkeypatch.setenv("ANTON_HOST_URL", "https://other.test")
    svc.start_connect(db)
    assert len([p for p in fake.posts if p[0] == META["registration_endpoint"]]) == 2


def test_start_connect_without_key_is_not_configured_and_makes_no_call(db, fake, monkeypatch):
    monkeypatch.delenv("COROS_TOKEN_KEY")
    with pytest.raises(svc.CorosNotConfigured):
        svc.start_connect(db)
    assert fake.posts == []


def test_complete_connect_stores_encrypted_tokens(db, fake):
    _connect(db, fake)
    row = db.get(CorosConnection, 1)
    assert row.status == "connected" and row.connected_at is not None
    assert "access-1" not in row.access_token_enc and "refresh-1" not in row.refresh_token_enc
    assert svc.get_access_token(db) == "access-1"


def test_state_is_single_use(db, fake):
    _, state = _connect(db, fake)
    with pytest.raises(ValueError, match="invalid_state"):
        svc.complete_connect(db, state=state, code="again")


def test_unknown_and_expired_state_rejected(db, fake):
    svc.start_connect(db)
    with pytest.raises(ValueError, match="invalid_state"):
        svc.complete_connect(db, state="nope", code="x")
    st = db.query(CorosOAuthState).one()
    st.expires_at = time.time() - 1
    db.commit()
    with pytest.raises(ValueError, match="invalid_state"):
        svc.complete_connect(db, state=st.state, code="x")
    assert db.get(CorosConnection, 1).status == "disconnected"


def test_rejected_code_does_not_connect(db, fake):
    url = svc.start_connect(db)
    fake.exchange_status = 400
    with pytest.raises(ValueError, match="exchange_rejected"):
        svc.complete_connect(db, state=parse_qs(urlparse(url).query)["state"][0], code="bad")
    assert db.get(CorosConnection, 1).status == "disconnected"


# --- refresh --------------------------------------------------------------------

def test_fresh_token_is_not_refreshed(db, fake):
    _connect(db, fake)
    svc.get_access_token(db)
    assert fake.refresh_posts() == []


def test_expired_token_refreshes_and_rotated_refresh_token_is_persisted(db, fake):
    _connect(db, fake)
    db.get(CorosConnection, 1).expires_at = time.time() + 10  # inside the skew window
    db.commit()
    assert svc.get_access_token(db) == "access-2"
    assert fake.refresh_posts()[0][1]["refresh_token"] == "refresh-1"
    # force a second one: it must present the *rotated* token
    db.get(CorosConnection, 1).expires_at = time.time() + 10
    db.commit()
    svc.get_access_token(db)
    assert fake.refresh_posts()[1][1]["refresh_token"] == "refresh-2"
    assert db.get(CorosConnection, 1).last_refresh_at is not None


def test_rejected_refresh_requires_reauth_and_stops_retrying(db, fake):
    _connect(db, fake)
    db.get(CorosConnection, 1).expires_at = time.time() - 1
    db.commit()
    fake.refresh_status = 400
    with pytest.raises(svc.CorosAuthError):
        svc.get_access_token(db)
    assert svc.get_status(db)["status"] == "reauth_required"
    n = len(fake.posts)
    with pytest.raises(svc.CorosAuthError):  # no further network traffic
        svc.get_access_token(db)
    assert len(fake.posts) == n


def test_server_error_on_refresh_propagates_and_keeps_connection(db, fake):
    _connect(db, fake)
    db.get(CorosConnection, 1).expires_at = time.time() - 1
    db.commit()
    fake.refresh_status = 503
    with pytest.raises(requests.HTTPError):
        svc.get_access_token(db)
    assert svc.get_status(db)["status"] == "connected"


def test_concurrent_refreshes_burn_only_one_refresh_token(tmp_path, fake):
    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    S = sessionmaker(bind=engine)
    setup = S()
    _connect(setup, fake)
    setup.get(CorosConnection, 1).expires_at = time.time() - 1
    setup.commit()
    setup.close()
    fake.delay = 0.2
    results = []

    def worker():
        s = S()
        try:
            results.append(svc.get_access_token(s))
        finally:
            s.close()

    ts = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(fake.refresh_posts()) == 1
    assert set(results) == {"access-2"}


def test_undecryptable_tokens_demand_reconnect(db, fake, monkeypatch):
    _connect(db, fake)
    monkeypatch.setenv("COROS_TOKEN_KEY", Fernet.generate_key().decode())  # key changed
    with pytest.raises(svc.CorosAuthError):
        svc.get_access_token(db)


def test_status_never_contains_tokens(db, fake):
    _connect(db, fake)
    blob = str(svc.get_status(db))
    assert "access-1" not in blob and "refresh-1" not in blob
    assert svc.get_status(db)["status"] == "connected"
    assert svc.get_status(db)["scopes"] == ["mcp.tools", "openid", "offline_access"]


def test_status_when_never_connected(db, fake):
    s = svc.get_status(db)
    assert s["status"] == "disconnected" and s["configured"] is True


# --- disconnect ---------------------------------------------------------------

def _revokes(fake):
    return [p for p in fake.posts if p[0] == META["revocation_endpoint"]]


def test_disconnect_revokes_and_clears_tokens(db, fake):
    _connect(db, fake)
    assert svc.disconnect(db) == {"revoked_remotely": True}
    assert _revokes(fake)[0][1]["token"] == "refresh-1"
    row = db.get(CorosConnection, 1)
    assert row.status == "disconnected" and row.access_token_enc is None and row.refresh_token_enc is None
    assert row.client_id == "client-1"  # registration kept for reconnect
    with pytest.raises(svc.CorosAuthError):
        svc.get_access_token(db)


def test_disconnect_still_deletes_locally_when_revoke_declined_or_unreachable(db, fake):
    _connect(db, fake)
    fake.revoke_status = 401  # public client not allowed to revoke
    assert svc.disconnect(db) == {"revoked_remotely": False}
    assert db.get(CorosConnection, 1).refresh_token_enc is None

    _connect(db, fake)
    fake.revoke_raises = True
    assert svc.disconnect(db) == {"revoked_remotely": False}
    assert db.get(CorosConnection, 1).status == "disconnected"


def test_disconnect_without_key_or_connection_is_harmless(db, fake, monkeypatch):
    assert svc.disconnect(db) == {"revoked_remotely": False}  # never connected
    _connect(db, fake)
    monkeypatch.delenv("COROS_TOKEN_KEY")
    assert svc.disconnect(db) == {"revoked_remotely": False}
    assert db.get(CorosConnection, 1).refresh_token_enc is None


def test_reauth_required_connection_can_be_disconnected_and_reconnected(db, fake):
    _connect(db, fake)
    db.get(CorosConnection, 1).status = "reauth_required"
    db.commit()
    svc.disconnect(db)
    _connect(db, fake)
    assert svc.get_status(db)["status"] == "connected"


# --- HTTP layer: auth boundaries ------------------------------------------------

@pytest.fixture()
def client(fake):
    from app.main import app
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    S = sessionmaker(bind=engine)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()

    # The auth-failure limiter is a process-wide singleton that earlier tests
    # exhaust for 127.0.0.1; clear its buckets so a 401 here is a 401, not a 429.
    from app.services.rate_limit import auth_failure_limiter
    auth_failure_limiter._buckets.clear()

    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db

    def call(method, path, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        async def _go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                         follow_redirects=False) as c:
                return await c.request(method, path, headers=headers)
        return asyncio.run(_go())

    yield call
    if prev is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = prev


def _desktop_token() -> str:
    # test_auth.py overwrites ANTON_TOKENS at collection time (shared process env),
    # so read whatever is live rather than assuming our setdefault won.
    pairs = dict(p.split(":", 1) for p in os.environ["ANTON_TOKENS"].split(","))
    return pairs["desktop"]


TOKEN = _desktop_token()


def test_status_and_connect_require_auth(client):
    assert client("GET", "/api/coros/status").status_code == 401
    assert client("POST", "/api/coros/connect").status_code == 401


def test_connect_and_status_with_auth(client):
    r = client("POST", "/api/coros/connect", TOKEN)
    assert r.status_code == 200 and r.json()["authorize_url"].startswith(META["authorization_endpoint"])
    s = client("GET", "/api/coros/status", TOKEN)
    assert s.status_code == 200 and s.json()["status"] == "disconnected"


def test_callback_is_public_but_bad_state_gets_error_redirect(client):
    r = client("GET", "/api/coros/callback?state=forged&code=abc")
    assert r.status_code == 302
    loc = r.headers["location"]
    assert "/settings/sync" in loc and "coros=error" in loc and "reason=invalid_state" in loc


def test_callback_success_redirects_connected(client):
    url = client("POST", "/api/coros/connect", TOKEN).json()["authorize_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    r = client("GET", f"/api/coros/callback?state={state}&code=good")
    assert r.status_code == 302 and "coros=connected" in r.headers["location"]
    assert client("GET", "/api/coros/status", TOKEN).json()["status"] == "connected"


def test_delete_connection_requires_auth_then_disconnects(client):
    assert client("DELETE", "/api/coros/connection").status_code == 401
    url = client("POST", "/api/coros/connect", TOKEN).json()["authorize_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    client("GET", f"/api/coros/callback?state={state}&code=good")
    r = client("DELETE", "/api/coros/connection", TOKEN)
    assert r.status_code == 200 and r.json() == {"revoked_remotely": True}
    assert client("GET", "/api/coros/status", TOKEN).json()["status"] == "disconnected"


def test_callback_denied_by_user(client):
    r = client("GET", "/api/coros/callback?error=access_denied")
    assert "reason=denied" in r.headers["location"]
