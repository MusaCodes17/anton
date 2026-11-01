"""Measure how large each Anton MCP read tool and resource payload is, before
trimming it (kept tool, from R14 T0). Read-only; not imported by the app.

Usage (on a COPY of the live DB, already at alembic head):
    cd backend && DATABASE_URL="sqlite:////abs/path/to/COPY.db" venv/bin/python scripts/mcp_payload_sizes.py

Make the copy with (never point the script at the live DB):
    sqlite3 -readonly ~/anton-data/shoe_deals.db ".backup /abs/path/to/COPY.db"

The script exits 1 without touching anything if DATABASE_URL is unset or
mentions `anton-data`. DATABASE_URL is read by app.database at import time, so
it is checked before `app` is imported.

Method
- Each read tool / resource is called directly, with default args unless the
  args column says otherwise. Tools are imported from app.mcp_server.
- Tools that write (db.add / commit / delete, settings watermark, prune) or make
  network calls are NOT called; they print `skipped: <reason>`. This was decided
  by reading their bodies and the services they call (see the reasons below).
- Payload: len(str) for resources; len(json.dumps(result, default=str)) for tools.
  Tokens ≈ chars / 4.
- A raising tool prints `ERROR: ...` and the run continues.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
from collections import Counter
from datetime import date

_DB_URL = os.environ.get("DATABASE_URL", "")
if not _DB_URL or "anton-data" in _DB_URL:
    sys.stderr.write(
        "refusing to run: DATABASE_URL must be set to a COPY of the DB "
        "(unset, or pointing at ~/anton-data, is not allowed).\n"
        "Make the copy with: sqlite3 -readonly ~/anton-data/shoe_deals.db \".backup /abs/path/to/COPY.db\"\n"
    )
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.mcp_server import _core  # noqa: E402
from app.mcp_server import (  # noqa: E402
    get_coros_sync_status,
    fetch_unsynced_coros_runs,
    get_deals,
    get_shoe_deals,
    get_watchlist,
    get_shoes,
    get_retailers,
    scrape_health,
    get_dashboard_stats,
    get_price_history,
    get_coupon_opportunities,
    get_owned_shoes,
    get_shoe_runs,
    get_shoe_notes,
    get_shoe_insights,
    get_rotation_insights,
    get_training_summary,
    get_training_trends,
    get_personal_bests,
    get_weekly_summary,
    get_race_block_context,
    get_block_comparison,
    get_onboarding_queue,
    active_deals_resource,
    deals_watchlist_resource,
    retailers_resource,
    brand_deals_resource,
    shoe_rotation_resource,
    shoe_detail_resource,
    shoe_runs_resource,
    shoe_notes_resource,
    shoe_review_resource,
    strava_runs_by_month_resource,
    training_summary_resource,
    training_fitness_resource,
)  # noqa: E402
from app.models.models import OwnedShoe  # noqa: E402

TOKEN_FLAG = 1500

SKIP_DEAL_ALERTS = "writes: get_deal_alerts commits the settings high-water mark (deals.py)"
SKIP_PLANNED_RACES = ("writes: get_planned_races -> races.list_races prunes unrun plans and commits "
                      "(services/races.py prune_unrun_races); race_entries is the read-only path")


def _active_shoe_with_most_mileage() -> int | None:
    with _core.get_session() as db:
        row = (
            db.query(OwnedShoe)
            .filter(OwnedShoe.status == "active")
            .order_by(OwnedShoe.current_mileage.desc(), OwnedShoe.id)
            .first()
        )
        return row.id if row else None


def _try(fn, *args, **kwargs):
    """Preflight lookups only; a failure here just leaves the dependent row to report its own ERROR."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def _measure(fn, args, kwargs):
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    if isinstance(result, str):
        return len(result), result
    return len(json.dumps(result, default=str)), result


def _run(name: str, args_label: str, fn, args: tuple = (), kwargs: dict | None = None) -> dict:
    try:
        chars, result = _measure(fn, args, kwargs or {})
        return {"tool": name, "args": args_label, "chars": chars, "result": result}
    except Exception as exc:  # one tool must not stop the run
        return {"tool": name, "args": args_label, "error": f"ERROR: {type(exc).__name__}: {exc}"}


def _skip(name: str, args_label: str, reason: str) -> dict:
    return {"tool": name, "args": args_label, "skip": f"skipped: {reason}"}


def _cell(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


def main() -> None:
    S = _active_shoe_with_most_mileage()

    deal_rows = _try(get_deals, limit=1, detail=True) or []
    first_deal = deal_rows[0] if deal_rows else {}
    brand = first_deal.get("brand", "")
    model = first_deal.get("model", "")

    # Brief get_watchlist returns {"entries", "total", "has_more"}.
    watchlist = (_try(get_watchlist) or {}).get("entries", [])
    W = watchlist[0].get("shoe_id") if watchlist else None

    year, month = str(date.today().year), f"{date.today().month:02d}"

    entries: list[dict] = [
        _run("get_coros_sync_status", "default", get_coros_sync_status),
        _run("fetch_unsynced_coros_runs", "default", fetch_unsynced_coros_runs),
        _run("get_deals", "default (limit=20)", get_deals),
        _run("get_deals", "detail=True (limit=20)", get_deals, (), {"detail": True}),
        _run("get_shoe_deals", f"brand={brand!r}, model={model!r}", get_shoe_deals, (brand, model)),
        _run("get_shoe_deals", f"brand={brand!r}, model={model!r}, detail=True", get_shoe_deals,
             (brand, model), {"detail": True}),
        _run("get_watchlist", "default", get_watchlist),
        _run("get_watchlist", "detail=True", get_watchlist, (), {"detail": True}),
        _run("get_shoes", "default", get_shoes),
        _run("get_shoes", "detail=True", get_shoes, (), {"detail": True}),
        _run("get_retailers", "default", get_retailers),
        _run("scrape_health", "default", scrape_health),
        _run("scrape_health", "detail=True", scrape_health, (), {"detail": True}),
        _run("get_dashboard_stats", "default", get_dashboard_stats),
    ]
    if W is None:
        entries.append(_skip("get_price_history", "shoe_id=<first watchlist shoe>", "no watchlist shoe"))
    else:
        entries.append(_run("get_price_history", f"shoe_id={W}", get_price_history, (W,)))
        entries.append(_run("get_price_history", f"shoe_id={W}, detail=True", get_price_history, (W,),
                            {"detail": True}))
    entries += [
        _skip("get_deal_alerts", "default", SKIP_DEAL_ALERTS),
        _run("get_coupon_opportunities", "default", get_coupon_opportunities),
        _run("get_coupon_opportunities", "detail=True", get_coupon_opportunities, (), {"detail": True}),
        _run("get_owned_shoes", "default (status_filter=None)", get_owned_shoes),
        _run("get_owned_shoes", "status_filter='active'", get_owned_shoes, (), {"status_filter": "active"}),
        _run("get_owned_shoes", "detail=True (status_filter=None)", get_owned_shoes, (), {"detail": True}),
        _run("get_shoe_runs", f"owned_shoe_id={S}", get_shoe_runs, (S,)),
        _run("get_shoe_runs", f"owned_shoe_id={S}, limit=200, detail=True", get_shoe_runs, (S,),
             {"limit": 200, "detail": True}),
        _run("get_shoe_notes", f"owned_shoe_id={S}", get_shoe_notes, (S,)),
        _run("get_shoe_insights", f"owned_shoe_id={S}", get_shoe_insights, (S,)),
        _run("get_rotation_insights", "default", get_rotation_insights),
        _run("get_rotation_insights", "detail=True", get_rotation_insights, (), {"detail": True}),
        _run("get_training_summary", "default (period='monthly')", get_training_summary),
        _run("get_training_trends", "default", get_training_trends),
        _run("get_personal_bests", "default", get_personal_bests),
        _skip("get_planned_races", "default", SKIP_PLANNED_RACES),
        _run("get_weekly_summary", "default", get_weekly_summary),
        _run("get_race_block_context", "default", get_race_block_context),
        _run("get_race_block_context", "detail=True", get_race_block_context, (), {"detail": True}),
        _run("get_block_comparison", "default (race_class='marathon')", get_block_comparison),
        _run("get_onboarding_queue", "default", get_onboarding_queue),
        # resources (measured as str length)
        _run("resource shoes://deals/active", "-", active_deals_resource),
        _run("resource deals://watchlist", "-", deals_watchlist_resource),
        _run("resource shoes://retailers", "-", retailers_resource),
        _run("resource shoes://deals/{brand}", f"brand={brand!r}", brand_deals_resource, (brand,)),
        _run("resource shoes://rotation", "-", shoe_rotation_resource),
        _run("resource shoes://owned/{shoe_id}", f"shoe_id={S}", shoe_detail_resource, (S,)),
        _run("resource shoes://owned/{shoe_id}/runs", f"shoe_id={S}", shoe_runs_resource, (S,)),
        _run("resource shoes://owned/{shoe_id}/notes", f"shoe_id={S}", shoe_notes_resource, (S,)),
        _run("resource shoes://review/{shoe_id}", f"shoe_id={S}", shoe_review_resource, (S,)),
        _run("resource strava://runs/{year}/{month}", f"year={year!r}, month={month!r}",
             strava_runs_by_month_resource, (year, month)),
        _run("resource training://summary", "-", training_summary_resource),
        _run("resource training://fitness", "-", training_fitness_resource),
    ]

    measured = [e for e in entries if "chars" in e]
    others = [e for e in entries if "chars" not in e]
    measured.sort(key=lambda e: e["chars"], reverse=True)

    print("| tool | args | chars | ≈tokens |")
    print("| --- | --- | ---: | ---: |")
    for e in measured:
        print(f"| {_cell(e['tool'])} | {_cell(e['args'])} | {e['chars']:,} | {e['chars'] // 4:,} |")
    for e in others:
        note = e.get("skip") or e.get("error")
        print(f"| {_cell(e['tool'])} | {_cell(e['args'])} | {_cell(note)} | — |")

    heavy = [e for e in measured if e["chars"] // 4 > TOKEN_FLAG]
    if heavy:
        listing = ", ".join(f"{e['tool']} [{e['args']}] ({e['chars'] // 4:,})" for e in heavy)
    else:
        listing = "none"
    print(f"\nRows over {TOKEN_FLAG:,} tokens: {listing}")

    owned = next((e for e in entries if e["tool"] == "get_owned_shoes" and "chars" in e
                  and e["args"].startswith("default")), None)
    if owned and isinstance(owned["result"], list):
        shoes = owned["result"]
        statuses = Counter(s.get("status") for s in shoes)
        per_item = [(s.get("status"), len(json.dumps(s, default=str))) for s in shoes]
        total = sum(c for _, c in per_item) or 1
        non_active = sum(c for st, c in per_item if st != "active")
        print(
            f"get_owned_shoes (default): {statuses.get('active', 0)} active, "
            f"{statuses.get('retired', 0)} retired, "
            f"{sum(v for k, v in statuses.items() if k not in ('active', 'retired'))} other "
            f"({dict(statuses)}); share of payload chars from non-active shoes: "
            f"{non_active / total:.1%}"
        )


if __name__ == "__main__":
    main()
