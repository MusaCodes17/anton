"""
R9.3 tests: GET /api/public/deals — the first deliberately public data endpoint.

Pins the exact field allowlist (so a new Deal/Shoe column can't leak by
default), a leak check on personal fields, active-only, rate limiting, caching,
no scrape work, read-only verbs, and `checked_at` semantics. Harness mirrors
test_auth.py: ASGI transport + asyncio.run, per-test in-memory StaticPool DB
via a get_db override (restored afterwards so other modules' overrides survive).
"""
import os

os.environ.setdefault("ANTON_TOKENS", "desktop:test-public-deals-token-0123456789")

import asyncio  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import models  # noqa: E402,F401
from app.models.models import Deal, PromoCode, Retailer, ScrapeRun, Shoe  # noqa: E402
from app.services import settings as settings_svc  # noqa: E402
from app.services.rate_limit import KeyedRateLimiter  # noqa: E402

DEAL_KEYS = {
    "id", "shoe_id", "brand", "model", "shoe_type", "colorway", "image_url",
    "current_price", "msrp", "savings_amount", "savings_percent",
    "sizes_available", "in_stock", "retailer_id", "retailer_name",
    "product_url", "promo_codes", "detected_at",
}
PROMO_KEYS = {"code", "description", "discount_percent", "discount_amount"}


@pytest.fixture()
def Session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)

    def _override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    # Fresh limiter per test: no shared bucket state.
    monkeypatch.setattr(
        "app.routers.public._public_limiter",
        KeyedRateLimiter(capacity=1000, refill_per_s=1000.0),
    )
    yield factory
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous
    engine.dispose()


def call(method="GET", path="/api/public/deals", **kw):
    async def _body():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.request(method, path, **kw)
    return asyncio.run(_body())


def seed_deal(db, *, active=True, brand="Nike", model="Vaporfly", notes=None,
              target_price=None, with_promo=True):
    shoe = Shoe(brand=brand, model=model, msrp=250.0, shoe_type="long_distance_racer",
                notes=notes, target_price=target_price)
    retailer = Retailer(name=f"R-{brand}-{model}", base_url="https://r.example")
    db.add_all([shoe, retailer])
    db.flush()
    if with_promo:
        db.add(PromoCode(retailer_id=retailer.id, code="SAVE10", description="10% off",
                         discount_percent=10.0, is_active=True))
    deal = Deal(shoe_id=shoe.id, retailer_id=retailer.id, current_price=200.0,
                target_price=target_price, savings_amount=50.0, savings_percent=20.0,
                product_url="https://r.example/p", in_stock=True, sizes_available=["9", "10"],
                image_url="https://img.example/x.jpg", colorway="Black", is_active=active)
    db.add(deal)
    db.commit()
    return deal


def test_logged_out_exact_key_sets(Session):
    with Session() as db:
        seed_deal(db)
    r = call()
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"deals", "checked_at"}
    assert len(body["deals"]) == 1
    d = body["deals"][0]
    assert set(d) == DEAL_KEYS
    assert d["msrp"] == 250.0 and d["brand"] == "Nike"
    assert len(d["promo_codes"]) == 1
    assert set(d["promo_codes"][0]) == PROMO_KEYS


def test_no_personal_fields_leak(Session):
    with Session() as db:
        seed_deal(db, notes="SECRET-NOTE", target_price=123.45)
        settings_svc.set_preferred_size(db, "10.5")
        db.commit()
    r = call()
    assert r.status_code == 200
    for needle in ("SECRET-NOTE", "123.45", "size_fit", "target_price", "notes", "scraper_config"):
        assert needle not in r.text


def test_only_active_deals(Session):
    with Session() as db:
        seed_deal(db, brand="Nike", model="Active")
        seed_deal(db, brand="Hoka", model="Gone", active=False)
    models_ = [d["model"] for d in call().json()["deals"]]
    assert models_ == ["Active"]


def test_429_after_burst(Session, monkeypatch):
    monkeypatch.setattr(
        "app.routers.public._public_limiter",
        KeyedRateLimiter(capacity=2, refill_per_s=0.0001),
    )
    assert call().status_code == 200
    assert call().status_code == 200
    r = call()
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


def test_cache_control_header(Session):
    r = call()
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "public, max-age=300"


def test_no_scrape_work(Session, monkeypatch):
    from app.scrapers import lock as lock_mod
    from app.scrapers.orchestrator import ScrapeOrchestrator

    class _Boom:
        def acquire(self, *a, **k):
            raise AssertionError("public endpoint touched the scrape lock")

    def _boom(*a, **k):
        raise AssertionError("public endpoint invoked the orchestrator")

    monkeypatch.setattr(lock_mod, "_scrape_lock", _Boom())
    for name in ("scrape_retailer", "scrape_shoe", "scrape_all_shoes",
                 "scrape_retailer_for_shoe", "detect_all_promo_codes"):
        monkeypatch.setattr(ScrapeOrchestrator, name, _boom)
    with Session() as db:
        seed_deal(db)
    assert call().status_code == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_write_verbs_not_allowed(Session, method):
    assert call(method).status_code == 405


def test_checked_at_latest_success_only(Session):
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    assert call().json()["checked_at"] is None
    with Session() as db:
        r = Retailer(name="X", base_url="https://x.example")
        db.add(r)
        db.flush()
        db.add(ScrapeRun(retailer_id=r.id, status="success", finished_at=now))
        db.add(ScrapeRun(retailer_id=r.id, status="error", finished_at=now + timedelta(hours=5)))
        db.commit()
    checked = call().json()["checked_at"]
    assert checked is not None
    assert datetime.fromisoformat(checked).replace(tzinfo=timezone.utc).hour == 12
