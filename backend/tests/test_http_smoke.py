"""
HTTP-layer smoke tests — the second, serialization slice of refactor.md H1.

Where test_deal_store / test_orchestrator test the deal *rules* by calling
services directly, and test_auth exercises the middleware, nothing until now
drove a *domain* aggregate through the full ASGI stack — FastAPI routing,
dependency injection, and Pydantic response serialization over real
relationship-loaded ORM objects. A router that serializes fine in isolation can
still 500 on a nested `from_attributes` payload (a deal's retailer + promos, a
shoe run's proxied activity fields); these tests catch exactly that.

One coherent graph is seeded once (a watched shoe with a live deal + retailer +
promo, an owned shoe with an attributed run, a planned race), then each router
family is hit once. Assertions are deliberately shallow — status 200 plus a
couple of *nested* fields to prove serialization actually ran, not a schema
contract (that's the unit tests' job).

Env/transport notes mirror test_auth.py: ANTON_TOKENS is set before importing
app.main so the middleware (lazily built on the first request) sees the right
token map regardless of which test module imports first; the app is driven via
httpx.ASGITransport since httpx 0.28 dropped TestClient's app= shortcut.
"""
import os

# Must match test_auth's values exactly: Starlette builds the middleware stack
# lazily on the first request, so whichever test module's env settings are active
# at that moment win. Both test files must agree on the full token map so that
# whichever loads first, the other's tests still pass.
TEST_SECRET    = "test-anton-secret-0123456789abcdef"
TEST_OTHER     = "test-other-secret-0123456789abcd00"
TEST_CONNECTOR = "test-connector-secret-0123456789ab"
os.environ["ANTON_TOKENS"]          = f"desktop:{TEST_SECRET},spa:{TEST_OTHER}"
os.environ["ANTON_CONNECTOR_TOKEN"] = TEST_CONNECTOR

import asyncio  # noqa: E402
from datetime import date, datetime  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import models  # noqa: E402

# Shared in-memory DB (StaticPool → one connection, so the threadpool route
# worker sees the rows we seed here — same reasoning as test_auth.py).
_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=_engine)
_Session = sessionmaker(bind=_engine)


def _override_get_db():
    s = _Session()
    try:
        yield s
    finally:
        s.close()


def _seed():
    """One coherent domain graph exercising every serialization path below."""
    db = _Session()
    try:
        retailer = models.Retailer(
            name="The Last Hunt", base_url="https://tlh.example",
            is_active=True, scraping_enabled=True, platform="shopify",
        )
        shoe = models.Shoe(
            brand="Nike", model="Vaporfly", shoe_type="long_distance_racer",
            msrp=250.0, target_price=200.0, is_active=True,
        )
        owned = models.OwnedShoe(
            brand="Nike", model="Pegasus", nickname="Daily",
            shoe_type="daily_trainer", status="active",
            starting_mileage=0.0, current_mileage=10.0,
            purchase_price=180.0, purchase_date=date.today(),
        )
        db.add_all([retailer, shoe, owned])
        db.flush()

        db.add(models.PromoCode(
            retailer_id=retailer.id, code="SAVE15", description="15% off",
            discount_percent=15.0, source="scraped", is_active=True,
            detected_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
        ))
        db.add(models.PriceRecord(
            shoe_id=shoe.id, retailer_id=retailer.id,
            product_url="https://tlh.example/p/vaporfly",
            price=200.0, in_stock=True, size_available=True,
        ))
        db.add(models.Deal(
            shoe_id=shoe.id, retailer_id=retailer.id,
            current_price=200.0, target_price=200.0,
            savings_amount=50.0, savings_percent=20.0,
            product_url="https://tlh.example/p/vaporfly",
            in_stock=True, is_active=True,
        ))

        activity = models.Activity(
            source="manual", activity_type="Run", name="Morning run",
            run_date=date.today(), started_at_local=datetime.now(),
            distance_km=10.0, moving_time_s=2700, elapsed_time_s=2700,
            avg_pace_s_per_km=270, avg_hr=150, activity_tag="Easy",
        )
        db.add(activity)
        db.flush()
        db.add(models.ShoeRun(activity_id=activity.id, owned_shoe_id=owned.id))

        db.add(models.PlannedRace(
            name="Ottawa Marathon", race_date=date.today(),
            distance_km=42.2, target_time_s=9420, location="Ottawa",
            status="planned",
        ))
        db.commit()

        return {"shoe_id": shoe.id, "owned_id": owned.id, "activity_id": activity.id}
    finally:
        db.close()


_IDS = _seed()


@pytest.fixture(autouse=True)
def _use_seeded_db():
    """Point get_db at the seeded engine for each test, restoring whatever was
    there before (test_auth also overrides get_db globally)."""
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prev


def get(path: str):
    async def _body():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=True
        ) as client:
            return await client.get(path, headers={"Authorization": f"Bearer {TEST_SECRET}"})

    return asyncio.run(_body())


def _find(items, **match):
    return next((i for i in items if all(i.get(k) == v for k, v in match.items())), None)


# --- deals domain: nested retailer + promos serialize --------------------------

def test_shoe_types_serialize():
    r = get("/api/shoe-types")
    assert r.status_code == 200
    assert "long_distance_racer" in r.json()


def test_retailers_serialize_with_active_promos():
    r = get("/api/retailers/")
    assert r.status_code == 200
    retailer = _find(r.json(), name="The Last Hunt")
    assert retailer is not None
    # active_promo_codes is a computed property serialized through from_attributes.
    assert any(p["code"] == "SAVE15" for p in retailer["active_promo_codes"])


def test_deals_list_serializes_nested_retailer():
    r = get("/api/deals/")
    assert r.status_code == 200
    deal = r.json()[0]
    assert deal["savings_amount"] == 50.0
    assert deal["retailer"]["name"] == "The Last Hunt"  # nested RetailerResponse


def test_watchlist_serializes():
    r = get("/api/watchlist")
    assert r.status_code == 200
    assert any(item["model"] == "Vaporfly" for item in r.json())


# --- rotation / training domain: the ShoeRun proxy serialization path ----------

def test_owned_shoes_list_serializes_computed_fields():
    r = get("/api/owned-shoes/")
    assert r.status_code == 200
    shoe = _find(r.json(), id=_IDS["owned_id"])
    assert shoe is not None
    assert shoe["current_mileage"] == 10.0


def test_owned_shoe_runs_serialize_via_activity_proxy():
    r = get(f"/api/owned-shoes/{_IDS['owned_id']}/runs")
    assert r.status_code == 200
    run = r.json()[0]
    # distance_km / source are property proxies onto the joined Activity — the
    # exact serialization path H4 warns about (N+1 / silent filter breakage).
    assert run["distance_km"] == 10.0
    assert run["source"] == "manual"


def test_activities_feed_serializes():
    r = get("/api/activities")
    assert r.status_code == 200
    assert any(a["activity_id"] == _IDS["activity_id"] for a in r.json())


def test_activity_detail_serializes():
    r = get(f"/api/activities/{_IDS['activity_id']}")
    assert r.status_code == 200
    assert r.json()["distance_km"] == 10.0


def test_training_summary_serializes():
    assert get("/api/training/summary").status_code == 200


def test_races_serialize():
    r = get("/api/races")
    assert r.status_code == 200
    assert any(race["name"] == "Ottawa Marathon" for race in r.json())


# --- aggregate surfaces --------------------------------------------------------

def test_home_aggregate_serializes():
    r = get("/api/home")
    assert r.status_code == 200
    # One round trip composing training pulse + shoe alerts + top deals + strip.
    assert isinstance(r.json(), dict)


def test_dashboard_stats_serialize():
    r = get("/api/dashboard/stats")
    assert r.status_code == 200
    assert r.json()["active_deals"] >= 1
