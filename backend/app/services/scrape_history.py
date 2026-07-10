"""
Scrape-health read model — the data behind Settings → Sync & Scraping's
per-retailer observability surface (R2.5).

Turns the durable `scrape_runs` telemetry (written by
`ScrapeOrchestrator.scrape_retailer`) into two answers:

- **health per retailer**: its latest run's outcome, distilled to one of
  `ok` / `warning` / `error` / `unknown`, plus a short recent-run trend.
  "warning" is the "quietly broken" case the whole feature exists for — a run
  that finished cleanly (`success`) but brought back zero products, which no
  error status would ever surface.
- **recent runs**: a flat, newest-first activity log across all retailers.

Read-only and derived-never-stored (CLAUDE.md §7): `health` is computed here at
read time, never persisted on the row. Personal scale (a dozen retailers, a
handful of runs each per scrape) makes the per-retailer "latest + last N" query
trivially cheap.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Retailer, ScrapeRun

# How many recent runs per retailer feed the trend sparkline / product counts.
_TREND_LEN = 5
# Default page size for the flat recent-runs log.
_RECENT_DEFAULT = 20
# Consecutive bad runs (error or warning) before the watchdog fires (R4.2).
# Must be ≤ _TREND_LEN so the check has enough data.
_WATCHDOG_THRESHOLD = 3


def _run_summary(run: ScrapeRun) -> dict:
    """One scrape run, projected to the fields the UI/MCP need."""
    return {
        "id": run.id,
        "status": run.status,
        "trigger": run.trigger,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "shoes_scraped": run.shoes_scraped,
        "products_found": run.products_found,
        "prices_recorded": run.prices_recorded,
        "deals_found": run.deals_found,
        "error": run.error,
    }


def _derive_health(latest: Optional[ScrapeRun]) -> str:
    """
    Distill a retailer's latest run into a single health verdict:

    - `unknown`  — never scraped (no runs), or the latest is still `running`.
    - `error`    — the latest run recorded an exception.
    - `warning`  — the latest run finished cleanly but found **zero products**
                   (the "quietly broken" signal — the site changed under us).
    - `ok`       — the latest run finished cleanly with products.
    """
    if latest is None or latest.status == "running":
        return "unknown"
    if latest.status == "error":
        return "error"
    if latest.products_found == 0:
        return "warning"
    return "ok"


def _derive_watchdog_alert(trend: list) -> tuple[bool, Optional[str]]:
    """
    Flag a retailer that has produced nothing but failures for _WATCHDOG_THRESHOLD
    consecutive completed runs (R4.2).

    "Bad" means status == "error" OR (status == "success" with products_found == 0,
    i.e. the warning case). Running runs are skipped — an in-flight scrape must
    not mask a pre-existing streak.

    Returns (alert: bool, reason: str | None).
    """
    completed = [r for r in trend if r.status != "running"]
    if len(completed) < _WATCHDOG_THRESHOLD:
        return False, None
    streak = completed[:_WATCHDOG_THRESHOLD]
    bad = [r for r in streak if r.status == "error" or r.products_found == 0]
    if len(bad) < _WATCHDOG_THRESHOLD:
        return False, None
    kinds = set(r.status for r in streak)
    if kinds == {"error"}:
        reason = f"last {_WATCHDOG_THRESHOLD} runs all errored"
    elif kinds <= {"success"}:
        reason = f"last {_WATCHDOG_THRESHOLD} runs returned 0 products"
    else:
        reason = f"last {_WATCHDOG_THRESHOLD} runs all failed (errors and/or 0-product runs)"
    return True, reason


def retailer_health(db: Session) -> list[dict]:
    """
    Per-retailer scrape health, one entry per active retailer, ordered by name.

    Each entry carries the derived `health` verdict, the latest run's summary
    (or None if never scraped), and a `trend` of the last `_TREND_LEN` runs
    (newest first) for a compact product-count sparkline.
    """
    retailers = (
        db.query(Retailer)
        .filter(Retailer.is_active == True)  # noqa: E712 (SQLAlchemy column truthiness)
        .order_by(Retailer.name)
        .all()
    )

    out: list[dict] = []
    for r in retailers:
        recent = (
            db.query(ScrapeRun)
            .filter(ScrapeRun.retailer_id == r.id)
            .order_by(ScrapeRun.started_at.desc(), ScrapeRun.id.desc())
            .limit(_TREND_LEN)
            .all()
        )
        latest = recent[0] if recent else None
        watchdog_alert, watchdog_reason = _derive_watchdog_alert(recent)
        out.append({
            "retailer_id": r.id,
            "name": r.name,
            "platform": r.platform,
            "scraping_enabled": r.scraping_enabled,
            "health": _derive_health(latest),
            "latest_run": _run_summary(latest) if latest else None,
            "trend": [_run_summary(run) for run in recent],
            "watchdog_alert": watchdog_alert,
            "watchdog_reason": watchdog_reason,
        })
    return out


def recent_runs(db: Session, *, limit: int = _RECENT_DEFAULT) -> list[dict]:
    """Flat newest-first log of scrape runs across all retailers."""
    runs = (
        db.query(ScrapeRun)
        .order_by(ScrapeRun.started_at.desc(), ScrapeRun.id.desc())
        .limit(limit)
        .all()
    )
    # Attach the retailer name at the boundary — the flat log needs it and the
    # relationship is already loaded cheaply at this scale.
    summaries = []
    for run in runs:
        summary = _run_summary(run)
        summary["retailer_id"] = run.retailer_id
        summary["retailer_name"] = run.retailer.name if run.retailer else None
        summaries.append(summary)
    return summaries


def scrape_health(db: Session, *, recent_limit: int = _RECENT_DEFAULT) -> dict:
    """
    The aggregate scrape-observability payload for one round trip: per-retailer
    health plus a flat recent-runs log, and the watchdog summary (R4.2).
    Backs both GET /api/scrape/history and the MCP `scrape_health` tool
    (REST/MCP parity, CLAUDE.md §4.2).
    """
    retailers = retailer_health(db)
    needing_attention = [
        {"name": r["name"], "reason": r["watchdog_reason"]}
        for r in retailers
        if r["watchdog_alert"]
    ]
    return {
        "retailers": retailers,
        "recent_runs": recent_runs(db, limit=recent_limit),
        "retailers_needing_attention": needing_attention,
    }
