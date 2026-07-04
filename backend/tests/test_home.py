"""
Tests for the Home aggregation (Phase 4). Exercised at the service level,
matching the suite convention (no TestClient).

Covers: week-over-week volume math (Monday-anchored, empty weeks read 0),
last-run selection, the 75% shoe-alert threshold + worst-first ordering +
replacement-deal counting, top-deals ranking, and the activity strip.
"""
from datetime import date, datetime, timedelta

from app.models.models import (
    Activity, Deal, OwnedShoe, Retailer, Shoe, ShoeRun,
)
from app.services import home as home_svc
from app.services import settings as settings_svc


def _owned(db, brand="Adidas", model="Adios Pro 4", *, mileage, limit,
           status="active", shoe_type=None, nickname=None):
    s = OwnedShoe(
        brand=brand, model=model, nickname=nickname, shoe_type=shoe_type,
        current_mileage=mileage, mileage_limit=limit, status=status,
    )
    db.add(s)
    db.flush()
    return s


def _run(db, shoe_id, run_date, distance_km, *, source="coros", avg_pace=None, avg_hr=None):
    pace_s = None
    if avg_pace:
        mins, secs = avg_pace.split('/')[0].split(':')
        pace_s = int(mins) * 60 + int(secs)
    a = Activity(
        source=source, activity_type="Run", run_date=run_date,
        distance_km=distance_km, avg_pace_s_per_km=pace_s, avg_hr=avg_hr,
    )
    db.add(a)
    db.flush()
    r = ShoeRun(activity_id=a.id, owned_shoe_id=shoe_id)
    db.add(r)
    db.flush()
    return r


def _tracked(db, brand="Nike", model="Vaporfly", *, shoe_type=None, msrp=250.0):
    s = Shoe(brand=brand, model=model, shoe_type=shoe_type, target_price=180.0, msrp=msrp)
    db.add(s)
    db.flush()
    return s


def _retailer(db, name="The Last Hunt"):
    r = Retailer(name=name, base_url="https://example.com")
    db.add(r)
    db.flush()
    return r


def _deal(db, shoe, retailer, *, price, savings_pct, savings_amt=50.0):
    d = Deal(
        shoe_id=shoe.id, retailer_id=retailer.id, current_price=price,
        target_price=180.0, savings_amount=savings_amt, savings_percent=savings_pct,
        product_url="https://example.com/p", is_active=True,
    )
    db.add(d)
    db.flush()
    return d


# ── Training pulse ──────────────────────────────────────────────────────────

def test_training_pulse_week_over_week(db):
    today = date(2026, 7, 8)  # a Wednesday
    shoe = _owned(db, mileage=100, limit=800)
    this_monday = today - timedelta(days=today.weekday())  # Mon Jul 6
    # This week: 10 + 5 = 15
    _run(db, shoe.id, this_monday, 10.0)
    _run(db, shoe.id, today, 5.0)
    # Last week: 8
    _run(db, shoe.id, this_monday - timedelta(days=3), 8.0)
    # Two weeks ago: should be excluded from both
    _run(db, shoe.id, this_monday - timedelta(days=10), 99.0)
    db.commit()

    pulse = home_svc._training_pulse(db, today)
    assert pulse.this_week_km == 15.0
    assert pulse.last_week_km == 8.0
    assert pulse.delta_km == 7.0


def test_training_pulse_empty_week_reads_zero(db):
    today = date(2026, 7, 8)
    shoe = _owned(db, mileage=100, limit=800)
    # Only an old run — this and last week both empty.
    _run(db, shoe.id, today - timedelta(days=30), 12.0)
    db.commit()

    pulse = home_svc._training_pulse(db, today)
    assert pulse.this_week_km == 0.0
    assert pulse.last_week_km == 0.0
    assert pulse.delta_km == 0.0
    # Last run still surfaces even when it's outside both weeks.
    assert pulse.last_run is not None
    assert pulse.last_run.distance_km == 12.0


def test_training_pulse_last_run_is_newest_with_shoe(db):
    today = date(2026, 7, 8)
    shoe = _owned(db, mileage=100, limit=800, nickname="Racer")
    _run(db, shoe.id, today - timedelta(days=2), 6.0, avg_pace="4:30/km", avg_hr=150)
    _run(db, shoe.id, today, 9.0, avg_pace="5:00/km", avg_hr=140)
    db.commit()

    pulse = home_svc._training_pulse(db, today)
    assert pulse.last_run.date == today.isoformat()
    assert pulse.last_run.distance_km == 9.0
    assert pulse.last_run.shoe["nickname"] == "Racer"


def test_training_pulse_no_runs(db):
    today = date(2026, 7, 8)
    pulse = home_svc._training_pulse(db, today)
    assert pulse.this_week_km == 0.0 and pulse.last_week_km == 0.0
    assert pulse.last_run is None


# ── Shoe alerts ─────────────────────────────────────────────────────────────

def test_shoe_alerts_threshold_and_ordering(db):
    _owned(db, model="Fresh", mileage=100, limit=800)                 # 12% — excluded
    _owned(db, model="Getting there", mileage=612, limit=800)         # 76.5% — in
    worst = _owned(db, model="Overdue", mileage=850, limit=800)       # 106% — in, worst
    _owned(db, model="No limit", mileage=900, limit=None)             # excluded (no limit)
    _owned(db, model="Retired old", mileage=790, limit=800, status="retired")  # excluded
    db.commit()

    alerts = home_svc._shoe_alerts(db)
    assert [a.model for a in alerts] == ["Overdue", "Getting there"]  # worst first
    assert alerts[0].id == worst.id
    assert round(alerts[0].pct, 2) == 1.06


def test_shoe_alerts_replacement_deal_count(db):
    _owned(db, model="Worn Tempo", mileage=700, limit=800, shoe_type="Tempo shoe")
    retailer = _retailer(db)
    # Two active deals on tracked shoes of the same type → count 2.
    t1 = _tracked(db, model="Tempo A", shoe_type="Tempo shoe")
    t2 = _tracked(db, model="Tempo B", shoe_type="Tempo shoe")
    other = _tracked(db, model="Trail X", shoe_type="Trail shoe")
    _deal(db, t1, retailer, price=150, savings_pct=25)
    _deal(db, t2, retailer, price=160, savings_pct=20)
    _deal(db, other, retailer, price=100, savings_pct=40)
    db.commit()

    alerts = home_svc._shoe_alerts(db)
    assert len(alerts) == 1
    assert alerts[0].replacement_deals == 2


def test_shoe_alerts_no_type_means_zero_replacements(db):
    _owned(db, model="Typeless", mileage=700, limit=800, shoe_type=None)
    db.commit()
    alerts = home_svc._shoe_alerts(db)
    assert alerts[0].replacement_deals == 0


# ── Top deals ───────────────────────────────────────────────────────────────

def test_top_deals_ranked_and_capped(db):
    retailer = _retailer(db)
    for i, pct in enumerate([10, 45, 30, 55, 20]):
        s = _tracked(db, model=f"S{i}")
        _deal(db, s, retailer, price=100 + i, savings_pct=pct)
    # An inactive deep discount must not appear.
    s_off = _tracked(db, model="Inactive")
    d = _deal(db, s_off, retailer, price=50, savings_pct=90)
    d.is_active = False
    db.commit()

    top = home_svc._top_deals(db, limit=3)
    assert [round(t.savings_percent) for t in top] == [55, 45, 30]
    assert top[0].retailer == "The Last Hunt"


# ── Activity strip ──────────────────────────────────────────────────────────

def test_activity_strip(db):
    retailer = _retailer(db)
    retailer.last_scraped_at = datetime(2026, 7, 7, 9, 0, 0)
    s = _tracked(db, brand="Saucony", model="Endorphin")
    _deal(db, s, retailer, price=140, savings_pct=30)
    settings_svc.set_setting(db, "last_coros_sync_at", "2026-07-08T06:30:00")
    db.commit()

    strip = home_svc._activity_strip(db)
    assert strip.last_coros_sync_at == datetime(2026, 7, 8, 6, 30, 0)
    assert strip.last_scrape_at == datetime(2026, 7, 7, 9, 0, 0)
    assert strip.newest_deal_label == "Saucony Endorphin"


def test_home_summary_assembles_all_modules(db):
    today = date(2026, 7, 8)
    shoe = _owned(db, mileage=700, limit=800)
    _run(db, shoe.id, today, 10.0)
    retailer = _retailer(db)
    s = _tracked(db)
    _deal(db, s, retailer, price=150, savings_pct=40)
    db.commit()

    summary = home_svc.home_summary(db, today)
    assert summary.training_pulse.this_week_km == 10.0
    assert len(summary.shoe_alerts) == 1
    assert len(summary.top_deals) == 1
    assert summary.activity_strip.newest_deal_label is not None
