"""
Application settings — thin key/value store backed by the AppSettings table.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import AppSettings
from app.utils.shoe_sizes import parse_preferred_size

PREFERRED_SIZE_KEY = "preferred_shoe_size"
HIDE_OTHER_SIZES_KEY = "hide_other_sizes"


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
