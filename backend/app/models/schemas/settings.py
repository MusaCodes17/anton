"""
Pydantic schemas for app-level settings (the UI-configurable nightly scrape
schedule). Re-exported from `app.models.schemas`.
"""
from pydantic import BaseModel, Field, field_validator


# ============== SCHEDULE (#7 — UI-configurable nightly scrape) ==============

class ScheduleUpdate(BaseModel):
    """
    Body for PUT /admin/schedule. The cron string is validated against the
    scheduler's own CronTrigger parser here, so a bad expression is a 422 at the
    boundary and never reaches storage (a saved-but-unparseable cron would let
    the job silently fail to register). America/Toronto is implied — the
    scheduler owns the timezone; clients send only the crontab fields.
    """
    enabled: bool = Field(..., description="Whether nightly scraping is on")
    cron: str = Field(..., description="Crontab string, e.g. '0 3 * * *' (America/Toronto)")

    @field_validator("cron")
    @classmethod
    def _valid_cron(cls, v: str) -> str:
        # Lazy import avoids any import-order coupling between schemas and the
        # schedule service (which imports the settings service + models).
        from app.services.schedule import validate_cron
        validate_cron(v)  # raises ValueError → pydantic surfaces it as 422
        return v
