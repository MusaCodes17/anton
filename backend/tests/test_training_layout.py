"""
Tests for the Training-page section layout (order + hidden sections) stored
server-side in AppSettings. Covers the normalise-on-read rules, the strict
validation on write, the corrupt-blob fallback, and that the size preference
and the layout don't clobber each other through the preferences router.
"""
import json

import pytest
from fastapi import HTTPException

from app.models.models import AppSettings
from app.routers import preferences as prefs_router
from app.services import settings as settings_svc
from app.services.settings import TRAINING_LAYOUT_KEY, TRAINING_SECTIONS


DEFAULT = {"order": list(TRAINING_SECTIONS), "hidden": []}


def test_default_when_unset(db):
    assert settings_svc.get_training_layout(db) == DEFAULT


def test_roundtrip_save_and_read(db):
    order = ["fitness", "now", "trends", "races", "records", "predictions", "activities"]
    saved = settings_svc.set_training_layout(db, order=order, hidden=["races", "records"])
    db.commit()
    assert saved == {"order": order, "hidden": ["races", "records"]}
    assert settings_svc.get_training_layout(db) == saved


def test_hidden_follows_order_sequence(db):
    # hidden given in a different sequence than `order`; stored in `order` sequence
    saved = settings_svc.set_training_layout(
        db, order=list(TRAINING_SECTIONS), hidden=["activities", "now"]
    )
    assert saved["hidden"] == ["now", "activities"]


def test_unknown_id_in_order_raises(db):
    with pytest.raises(ValueError):
        settings_svc.set_training_layout(db, order=["trends", "bogus"], hidden=[])


def test_unknown_id_in_hidden_raises(db):
    with pytest.raises(ValueError):
        settings_svc.set_training_layout(db, order=list(TRAINING_SECTIONS), hidden=["bogus"])


def test_duplicate_in_order_raises(db):
    with pytest.raises(ValueError):
        settings_svc.set_training_layout(
            db, order=["trends", "now", "trends"], hidden=[]
        )


def test_all_hidden_raises(db):
    with pytest.raises(ValueError):
        settings_svc.set_training_layout(
            db, order=list(TRAINING_SECTIONS), hidden=list(TRAINING_SECTIONS)
        )


def test_missing_sections_appended_in_default_order(db):
    saved = settings_svc.set_training_layout(db, order=["fitness", "now"], hidden=[])
    assert saved["order"] == [
        "fitness", "now", "trends", "races", "records", "predictions", "activities",
    ]


def test_missing_section_is_not_hidden_by_default(db):
    saved = settings_svc.set_training_layout(db, order=["now"], hidden=["now"])
    assert "trends" not in saved["hidden"]
    assert saved["hidden"] == ["now"]


def test_corrupt_json_returns_default(db):
    db.add(AppSettings(key=TRAINING_LAYOUT_KEY, value="{not json"))
    db.commit()
    assert settings_svc.get_training_layout(db) == DEFAULT


@pytest.mark.parametrize("blob", [
    "[]", '"text"', json.dumps({"order": "trends"}), json.dumps({"hidden": ["now"]}),
])
def test_wrong_shape_returns_default(db, blob):
    db.add(AppSettings(key=TRAINING_LAYOUT_KEY, value=blob))
    db.commit()
    assert settings_svc.get_training_layout(db) == DEFAULT


def test_read_drops_unknown_and_duplicate_ids(db):
    blob = json.dumps({
        "order": ["now", "ghost", "now", "trends"],
        "hidden": ["ghost", "trends"],
    })
    db.add(AppSettings(key=TRAINING_LAYOUT_KEY, value=blob))
    db.commit()
    layout = settings_svc.get_training_layout(db)
    assert layout["order"][:2] == ["now", "trends"]
    assert sorted(layout["order"]) == sorted(TRAINING_SECTIONS)
    assert layout["hidden"] == ["trends"]


def test_get_preferences_includes_training_layout(db):
    settings_svc.set_training_layout(db, order=["now"], hidden=["records"])
    db.commit()
    out = prefs_router.get_preferences(db)
    assert out["training_layout"] == settings_svc.get_training_layout(db)
    assert out["training_layout"]["hidden"] == ["records"]


def test_put_training_layout_persists_and_returns_response(db):
    body = prefs_router.TrainingLayoutUpdate(order=["now", "trends"], hidden=["now"])
    out = prefs_router.update_training_layout(body, db)
    assert out["training_layout"] == {
        "order": ["now", "trends", "races", "records", "fitness", "predictions", "activities"],
        "hidden": ["now"],
    }


def test_put_training_layout_invalid_returns_422(db):
    body = prefs_router.TrainingLayoutUpdate(order=["nope"], hidden=[])
    with pytest.raises(HTTPException) as exc:
        prefs_router.update_training_layout(body, db)
    assert exc.value.status_code == 422


def test_size_put_does_not_reset_layout(db):
    settings_svc.set_training_layout(db, order=["fitness"], hidden=["trends"])
    db.commit()
    before = settings_svc.get_training_layout(db)
    prefs_router.update_preferences(
        prefs_router.PreferencesUpdate(preferred_size="10", hide_other_sizes=True), db
    )
    assert settings_svc.get_training_layout(db) == before


def test_layout_put_does_not_reset_size(db):
    prefs_router.update_preferences(
        prefs_router.PreferencesUpdate(preferred_size="10", hide_other_sizes=True), db
    )
    prefs_router.update_training_layout(
        prefs_router.TrainingLayoutUpdate(order=["now"], hidden=[]), db
    )
    out = prefs_router.get_preferences(db)
    assert out["preferred_size"] == 10.0
    assert out["hide_other_sizes"] is True
