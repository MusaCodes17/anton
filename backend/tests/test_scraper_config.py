"""ScraperConfig input schema: malformed configs are rejected at the API / MCP
boundary (422 / success=False) and the stored dict keeps its plain shape."""
import asyncio
import os
from contextlib import contextmanager

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Same token map as test_http_smoke/test_auth (the middleware is built lazily on
# the first request, so every module must agree on it).
TOKEN = "test-anton-secret-0123456789abcdef"
os.environ["ANTON_TOKENS"] = f"desktop:{TOKEN},spa:test-other-secret-0123456789abcd00"
os.environ["ANTON_CONNECTOR_TOKEN"] = "test-connector-secret-0123456789ab"

from app import mcp_server  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import models  # noqa: E402
from app.models.schemas import ScraperConfig  # noqa: E402

_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
Base.metadata.create_all(bind=_engine)
_Session = sessionmaker(bind=_engine)


def _override_get_db():
    s = _Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _use_db():
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prev


def call(method: str, path: str, json=None):
    async def _body():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.request(method, path, json=json,
                                   headers={"Authorization": f"Bearer {TOKEN}"})
    return asyncio.run(_body())


def _stored(retailer_id):
    s = _Session()
    try:
        return s.get(models.Retailer, retailer_id).scraper_config
    finally:
        s.close()


def _post(name, cfg):
    return call("POST", "/api/retailers/", {
        "name": name, "base_url": "https://x.example", "platform": "custom",
        "scraper_config": cfg,
    })


def test_partial_algolia_config_rejected_with_missing_keys():
    r = _post("SC partial", {"algolia_app_id": "x"})
    assert r.status_code == 422
    assert "algolia_api_key" in r.text and "algolia_index" in r.text


def test_wrong_type_rejected():
    assert _post("SC badtype", {"use_browser": "definitely"}).status_code == 422


def test_free_text_and_unknown_keys_stored_exactly():
    r = _post("SC free", {"notes": "hi", "custom_key": 1})
    assert r.status_code == 201
    assert r.json()["scraper_config"] == {"notes": "hi", "custom_key": 1}
    assert _stored(r.json()["id"]) == {"notes": "hi", "custom_key": 1}


def test_put_full_algolia_config_stored_as_given():
    rid = _post("SC put", None).json()["id"]
    cfg = {"algolia_app_id": "A", "algolia_api_key": "K", "algolia_index": "I"}
    r = call("PUT", f"/api/retailers/{rid}", {"scraper_config": cfg})
    assert r.status_code == 200
    assert _stored(rid) == cfg


def test_put_partial_algolia_config_rejected():
    rid = _post("SC put bad", None).json()["id"]
    assert call("PUT", f"/api/retailers/{rid}", {"scraper_config": {"algolia_index": "I"}}).status_code == 422


def test_response_serializes_legacy_row():
    s = _Session()
    r = models.Retailer(name="SC legacy", base_url="https://l.example", platform="custom",
                        scraper_config={"notes": 5, "weird": [1]})
    s.add(r)
    s.commit()
    rid = r.id
    s.close()
    resp = call("GET", f"/api/retailers/{rid}")
    assert resp.status_code == 200
    assert resp.json()["scraper_config"] == {"notes": 5, "weird": [1]}


def test_mcp_onboard_rejects_partial_algolia_without_writing(monkeypatch):
    calls = []

    @contextmanager
    def fake_session():
        calls.append(1)
        yield None

    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)
    from app.mcp_server import onboarding as mcp_onboarding
    out = mcp_onboarding.onboard_retailer(
        retailer_id=1, platform="algolia", confirm=True,
        scraper_config={"algolia_app_id": "x"},
    )
    assert out["success"] is False
    assert "algolia_api_key" in out["error"]
    assert calls == []  # rejected before any session/write


def test_model_as_stored_omits_unset_keys():
    assert ScraperConfig.model_validate({"notes": "x"}).as_stored() == {"notes": "x"}
