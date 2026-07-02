"""
Application settings — thin key/value store backed by the AppSettings table.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import AppSettings


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
