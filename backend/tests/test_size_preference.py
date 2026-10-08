"""
Tests for the R6.3 my-size deal filter: label normaliser, preference storage,
the per-deal ``size_fit`` stamp, and digest suppression. Label formats under
test are the ones sampled from the live DB (plain, ``9.0``, ``10 / 11.5``).
"""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models.models import Deal, Retailer, Shoe
from app.routers import preferences as prefs_router
from app.services import deals as deals_svc
from app.services import settings as settings_svc
from app.services.deal_alerts import deal_alerts
from app.utils.shoe_sizes import IN, OUT, UNKNOWN, parse_preferred_size, parse_size_label, size_fit


# ---- normaliser -----------------------------------------------------------

@pytest.mark.parametrize("label,expected", [
    ("9", 9.0), ("9.0", 9.0), (" 9.5 ", 9.5), ("10 / 11.5", 10.0), (None, None), ("XL", None),
])
def test_parse_size_label(label, expected):
    assert parse_size_label(label) == expected


def test_size_fit_matches_across_label_formats():
    assert size_fit(["8", "9.0"], 9.0) == IN
    assert size_fit(["10 / 11.5"], 10.0) == IN        # men's value of a unisex pair
    assert size_fit(["10 / 11.5"], 11.5) == OUT       # women's value is not matched
    assert size_fit(["8", "8.5"], 9.0) == OUT


def test_size_fit_unknown_is_never_out():
    assert size_fit(None, 9.0) == UNKNOWN
    assert size_fit([], 9.0) == UNKNOWN
    assert size_fit(["XL"], 9.0) == UNKNOWN


def test_size_fit_none_when_no_preference():
    assert size_fit(["9"], None) is None


@pytest.mark.parametrize("bad", ["abc", "10.3", "2.5", "17", ""])
def test_preferred_size_validation_rejects(bad):
    with pytest.raises(ValueError):
        parse_preferred_size(bad)


def test_preferred_size_boundaries_inclusive():
    assert parse_preferred_size("3") == 3.0
    assert parse_preferred_size("16") == 16.0


# ---- settings + router ----------------------------------------------------

def test_preference_roundtrip_and_clear(db):
    assert settings_svc.get_preferred_size(db) is None
    settings_svc.set_preferred_size(db, "10.5")
    db.commit()
    assert settings_svc.get_preferred_size(db) == 10.5
    settings_svc.set_preferred_size(db, "")
    db.commit()
    assert settings_svc.get_preferred_size(db) is None


def test_router_rejects_invalid_size_with_422(db):
    with pytest.raises(HTTPException) as exc:
        prefs_router.update_preferences(prefs_router.PreferencesUpdate(preferred_size="10.3"), db)
    assert exc.value.status_code == 422


def test_router_persists_size_and_hide_toggle(db):
    out = prefs_router.update_preferences(
        prefs_router.PreferencesUpdate(preferred_size="10", hide_other_sizes=True), db
    )
    assert out == {"preferred_size": 10.0, "hide_other_sizes": True}


# ---- deals + digest -------------------------------------------------------

def _deal(db, sizes, *, detected_at=None, model="Pegasus", retailer=None):
    retailer = retailer or Retailer(name=f"R-{model}", base_url="https://r.example")
    db.add(retailer)
    shoe = Shoe(brand="Nike", model=model, msrp=200.0)
    db.add(shoe)
    db.flush()
    d = Deal(
        shoe_id=shoe.id, retailer_id=retailer.id, current_price=150.0, target_price=0,
        savings_amount=50.0, savings_percent=25.0, product_url=f"https://r.example/{model}",
        in_stock=True, is_active=True, sizes_available=sizes,
        detected_at=detected_at or datetime.utcnow(),
    )
    db.add(d)
    db.commit()
    return d


def test_list_deals_stamps_size_fit_only_when_preference_set(db):
    _deal(db, ["9"], model="A")
    assert [d.size_fit for d in deals_svc.list_deals(db)] == [None]
    settings_svc.set_preferred_size(db, "9")
    db.commit()
    assert [d.size_fit for d in deals_svc.list_deals(db)] == [IN]


def test_list_deals_size_filter_is_numeric(db):
    _deal(db, ["9.0"], model="A")
    _deal(db, ["10 / 11.5"], model="B")
    _deal(db, ["8"], model="C")
    models = {d.shoe.model for d in deals_svc.list_deals(db, size="9")}
    assert models == {"A"}
    assert {d.shoe.model for d in deals_svc.list_deals(db, size="10")} == {"B"}


def test_digest_drops_out_of_size_keeps_unknown_and_counts(db):
    since = datetime.utcnow() - timedelta(days=1)
    _deal(db, ["9"], model="In")
    _deal(db, ["8"], model="Out")
    _deal(db, None, model="Unknown")
    settings_svc.set_preferred_size(db, "9")
    db.commit()
    digest = deal_alerts(db, since=since)
    assert {a.model for a in digest.new_deals} == {"In", "Unknown"}
    assert digest.out_of_size_suppressed == 1


def test_digest_unchanged_without_preference(db):
    since = datetime.utcnow() - timedelta(days=1)
    _deal(db, ["8"], model="Out")
    digest = deal_alerts(db, since=since)
    assert [a.model for a in digest.new_deals] == ["Out"]
    assert digest.out_of_size_suppressed == 0
