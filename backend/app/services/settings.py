"""
Application settings — thin key/value store backed by the AppSettings table.
"""
import json
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import AppSettings
from app.utils.shoe_sizes import parse_preferred_size

PREFERRED_SIZE_KEY = "preferred_shoe_size"
HIDE_OTHER_SIZES_KEY = "hide_other_sizes"
TRAINING_LAYOUT_KEY = "training_layout"

# Default order AND the closed set of section ids for the Training page. Must
# match the section ids the Training page renders; Trends first is the runner's
# choice. Unknown ids are rejected on write and dropped on read.
TRAINING_SECTIONS = ("trends", "now", "races", "records", "fitness", "predictions", "activities")


def get_setting(db: Session, key: str) -> Optional[str]:
    row = db.query(AppSettings).filter(AppSettings.key == key).first()
    return row.value if row else None


def set_setting(db: Session, key: str, value: str) -> None:
    """Upsert a setting value. Does NOT commit — caller owns the transaction."""
    row = db.query(AppSettings).filter(AppSettings.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSettings(key=key, value=value))


def get_preferred_size(db: Session) -> Optional[float]:
    """The runner's shoe size (R6.3), or None when unset/corrupt (feature off)."""
    raw = get_setting(db, PREFERRED_SIZE_KEY)
    if not raw:
        return None
    try:
        return parse_preferred_size(raw)
    except ValueError:
        return None


def set_preferred_size(db: Session, value: Optional[str]) -> Optional[float]:
    """
    Validate and store the size preference ("" / None clears it). Does NOT
    commit — caller owns the transaction.

    Raises:
        ValueError: if the value isn't a valid half-step shoe size.
    """
    if value is None or str(value).strip() == "":
        set_setting(db, PREFERRED_SIZE_KEY, "")
        return None
    size = parse_preferred_size(value)
    set_setting(db, PREFERRED_SIZE_KEY, f"{size:g}")
    return size


def get_hide_other_sizes(db: Session) -> bool:
    """Whether the Deals page hides out-of-size deals instead of badging them."""
    return get_setting(db, HIDE_OTHER_SIZES_KEY) == "true"


def set_hide_other_sizes(db: Session, hide: bool) -> None:
    """Persist the hide toggle. Does NOT commit."""
    set_setting(db, HIDE_OTHER_SIZES_KEY, "true" if hide else "false")


def _normalize_layout(order: list, hidden: list) -> dict:
    """
    Canonicalise a layout: drop unknown ids and duplicates from `order`, append
    any section missing from it (in default order, so a newly added section
    shows up without a migration), and keep `hidden` in `order` sequence.
    Never raises; callers validate strictly before calling this on writes.
    """
    known = set(TRAINING_SECTIONS)
    seen: list[str] = []
    for sid in order:
        if isinstance(sid, str) and sid in known and sid not in seen:
            seen.append(sid)
    for sid in TRAINING_SECTIONS:
        if sid not in seen:
            seen.append(sid)
    hidden_set = {h for h in hidden if isinstance(h, str) and h in known}
    return {"order": seen, "hidden": [sid for sid in seen if sid in hidden_set]}


def get_training_layout(db: Session) -> dict:
    """
    The runner's Training-page section layout: {"order": [...], "hidden": [...]}.

    Stored as JSON text under TRAINING_LAYOUT_KEY. Missing or corrupt data
    yields the default (all sections, in TRAINING_SECTIONS order, none hidden)
    — a bad layout blob must never break the page.
    """
    default = {"order": list(TRAINING_SECTIONS), "hidden": []}
    raw = get_setting(db, TRAINING_LAYOUT_KEY)
    if not raw:
        return default
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return default
    if not isinstance(data, dict):
        return default
    order = data.get("order")
    hidden = data.get("hidden")
    if not isinstance(order, list):
        return default
    if not isinstance(hidden, list):
        hidden = []
    return _normalize_layout(order, hidden)


def set_training_layout(db: Session, *, order: list[str], hidden: list[str]) -> dict:
    """
    Validate and store the Training-page layout. Does NOT commit — caller owns
    the transaction. Missing ids in `order` are allowed (appended on normalise).

    Returns:
        The normalised layout dict, as stored.

    Raises:
        ValueError: unknown id or duplicate in `order`, unknown id in `hidden`,
            or every section hidden (the page would be empty).
    """
    known = set(TRAINING_SECTIONS)
    if len(set(order)) != len(order):
        raise ValueError("training layout order contains duplicate section ids")
    unknown = [sid for sid in order if sid not in known] + [sid for sid in hidden if sid not in known]
    if unknown:
        raise ValueError(f"unknown training section id(s): {', '.join(map(str, unknown))}")
    if set(hidden) >= known:
        raise ValueError("at least one training section must stay visible")
    layout = _normalize_layout(order, hidden)
    set_setting(db, TRAINING_LAYOUT_KEY, json.dumps(layout))
    return layout
