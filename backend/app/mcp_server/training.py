"""Training MCP surface: summaries, trends, personal bests, athlete metrics, races, race-block context."""
from typing import Optional

from app.models.models import Activity
from app.services import rotation, strava_stats, races as races_svc, fitness as fitness_svc, weekly_summary as weekly_summary_svc, race_advisor as race_advisor_svc, training_trends as training_trends_svc
from app.mcp_server import _core
from app.mcp_server._core import mcp


@mcp.tool()
def get_training_summary(period: str = "monthly") -> dict:
    """
    Weekly or monthly training aggregates over the full run history (imported
    Strava runs unioned with live COROS/manual runs): total distance, run
    count, average pace, average heart rate, and elevation gain per period
    (newest first).

    Use this for questions like "how much did I run last month", "what were my
    weekly volumes this year", or "how has my average pace trended".

    Args:
        period: "monthly" (default) or "weekly".
    """
    if period not in ("weekly", "monthly"):
        return {"error": "period must be 'weekly' or 'monthly'"}
    with _core.get_session() as db:
        summaries = strava_stats.training_summary(db, period)
        return {
            "period": period,
            "buckets": [
                {
                    "period": s.period,
                    "total_km": s.total_km,
                    "run_count": s.run_count,
                    "avg_pace": s.avg_pace,
                    "avg_hr": s.avg_hr,
                    "elevation_gain_m": s.elevation_gain_m,
                    **({"rolling_4wk_km": s.rolling_4wk_km} if period == "weekly" else {}),
                }
                for s in summaries
            ],
        }


@mcp.tool()
def get_training_trends(as_of: Optional[str] = None) -> dict:
    """
    The runner's training trends, as two answers: `load` and `form`.

    load — is the runner building, holding or easing their training? Compares
    the last 7 days' km with the average week of the 28 days before (`ratio`),
    and gives a `verdict`: building (ratio above 1.10), holding (0.90–1.10),
    easing (below 0.90), taper (easing with a planned race within 3 weeks —
    `taper_race` names it), or no_baseline (no running in the prior 28 days, so
    nothing to compare). Also returns last-7-day km, run count and longest run,
    and the prior average week and longest run. A heuristic on distance, not a
    physiological load model.

    form — what's the runner's form now?
    - Efficiency in metres per heartbeat (distance ÷ (avg HR × moving
      minutes)) over STEADY runs only: untagged or Easy / Long Run, ≥ 5 km,
      with avg HR, without long stops. Higher = more ground per beat = fitter.
      `verdict` compares the median of the last 42 days' steady runs
      (`recent_m_per_beat`) with the 84 days before (`baseline_m_per_beat`):
      improving (change_pct above +3%), steady (−3% to +3%), slipping (below
      −3%), or not_enough_data (under 5 steady runs in either window). Heat,
      hills and fatigue move HR too — present it as a trend, not a test result.
    - `months`: the monthly median m/beat for the last 12 months (the current
      month is partial); m_per_beat is null when a month had under 4 steady
      runs — say "too few steady runs", not "no running".
    - `best_efforts`: the best 5k and 10k in the last 90 days (`recent`) vs.
      all time (`all_time`), same rules and times as get_personal_bests (elapsed
      time; `segment` true = a stretch inside a longer run). pct_off_all_time
      is how much slower the recent pace is (0.0 = the recent one IS the
      all-time best); recent is null when nothing qualifies in 90 days.
    - `fitness`: COROS VO₂ max, threshold pace (s/km) and running level, one
      point per day a reading changed, oldest first — a step line; COROS's
      model, not Anton's.

    Both verdicts are heuristics — say so if you quote them. Use this for "am I
    building or holding?", "how's my training load?", "am I tapering
    properly?", "what's my form?", "am I getting fitter?". Read-only.

    Args:
        as_of: ISO date the windows end on (inclusive); defaults to today in
            Toronto.
    """
    from dataclasses import asdict
    from datetime import date as _date
    try:
        day = _date.fromisoformat(as_of) if as_of else None
    except ValueError:
        return {"error": "as_of must be an ISO date (YYYY-MM-DD)"}
    with _core.get_session() as db:
        return {
            "load": asdict(training_trends_svc.load_trend(db, as_of=day)),
            "form": asdict(training_trends_svc.form_trend(db, as_of=day)),
        }


@mcp.tool()
def get_personal_bests() -> dict:
    """
    The runner's records, as two lists:

    - race_pbs: whole race results at 5k, 10k, half and full — runs tagged Race
      or Parkrun, or linked to a planned race. Call these "race PBs" ("your 10k
      race PB is 34:55 at the Longueuil 10K").
    - best_efforts: the fastest stretch inside ANY run at 1k, mile, 5k, 10k,
      half and full, found from the run's per-second data — e.g. a 5k inside a
      10k race, or a 1k rep in a track session. When `segment` is true, say
      where it came from ("your best 5k effort, 16:58, was inside the Longueuil
      10K"); run_distance_km is the whole run. A run not yet scanned competes
      with its whole time (segment false).

    Times are ELAPSED time (gun time); avg_pace is derived from that time and
    the effort's distance. clock is "moving" for the rare run with no elapsed
    time. avg_hr is the whole run's and is omitted for segments.
    """
    def _row(b):
        return {
            "band": b.band,
            "target_km": b.target_km,
            "run_date": b.run_date,
            "name": b.name,
            "distance_km": b.distance_km,
            "total_time_s": b.total_time_s,
            "avg_pace": b.avg_pace,
            "avg_hr": b.avg_hr,
            "clock": b.clock,
            "segment": b.segment,
            "run_distance_km": b.run_distance_km,
            "source": b.source,
            "shoe": b.shoe,
            "strava_activity_id": b.strava_activity_id,
            "activity_id": b.activity_id,
        }

    with _core.get_session() as db:
        result = strava_stats.personal_bests(db)
        return {
            "note": "Elapsed times. Race PBs are whole race results; best efforts are the fastest stretch inside any run.",
            "race_pbs": [_row(b) for b in result.race_pbs],
            "best_efforts": [_row(b) for b in result.best_efforts],
        }


@mcp.tool()
def record_athlete_metrics(
    vo2max: Optional[float] = None,
    threshold_pace_s_per_km: Optional[int] = None,
    race_predictions: Optional[dict] = None,
    running_level: Optional[float] = None,
) -> dict:
    """
    Record a COROS athlete-level fitness snapshot (VO2 max, lactate-threshold
    pace, race predictions, running level) for the Training tab's fitness card.
    Append-only: each call stores one dated snapshot; the card shows the most recent.

    Anton reads these from COROS itself on every sync (R8.4.1): to refresh
    fitness, call sync_coros_now instead. This tool is the manual path only —
    for values the runner gives you, or read from a COROS connector when
    Anton's own COROS connection is down — and it is confirmed by the runner
    before it runs.

    Args:
        vo2max: VO2 max in ml/kg/min.
        threshold_pace_s_per_km: lactate-threshold pace, seconds per km
            (e.g. 3:45/km → 225).
        race_predictions: dict of distance_km (as a string key) → predicted time
            in seconds, e.g. {"5.0": 1005, "10.0": 2100, "21.0975": 4620,
            "42.195": 9720}.
        running_level: COROS running level score (a composite fitness rating).
    """
    if vo2max is None and threshold_pace_s_per_km is None and not race_predictions and running_level is None:
        return {"success": False, "error": "Provide at least one metric to record."}
    with _core.get_session() as db:
        snap = fitness_svc.record_snapshot(
            db,
            vo2max=vo2max,
            threshold_pace_s_per_km=threshold_pace_s_per_km,
            race_predictions=race_predictions,
            running_level=running_level,
        )
        return {
            "success": True,
            "captured_at": snap.captured_at.isoformat() if snap.captured_at else None,
            "vo2max": snap.vo2max,
            "threshold_pace_s_per_km": snap.threshold_pace_s_per_km,
            "race_predictions": snap.race_predictions,
            "running_level": snap.running_level,
        }


@mcp.tool()
def get_planned_races() -> dict:
    """
    Upcoming and past races the user is training toward, soonest first. Each
    race includes days_remaining / weeks_remaining and a derived target_pace
    ("M:SS/km") when a target time and distance are set.

    Use this to answer "how many weeks until my next race", to reason about
    where the user is in a training block, or to relate recent volume/pace to
    an upcoming goal. A negative days_remaining means the race is in the past.
    """
    with _core.get_session() as db:
        races = races_svc.list_races(db)
        return {"races": [races_svc.race_to_dict(r) for r in races]}


@mcp.tool()
def get_weekly_summary() -> dict:
    """
    Compile the weekly rotation digest for the current ISO week (Monday–Sunday).

    Returns a structured snapshot covering:
    - Volume: this week's km vs last week, with the delta.
    - Per-shoe usage: km and run count for each shoe used this week, most-used first.
      shoe_type is included so you can contextualise race-shoe vs daily-trainer usage.
    - Retirement pipeline: all active shoes at ≥ 75% of their mileage limit, worst first,
      with a count of matching replacement deals.
    - Notable runs: activities tagged Race, Parkrun, Intervals, Tempo, Long Run, or Track
      (the quality-session tags) — does NOT include Easy/Recovery/Workout.
    - Checkpoints: 100km mileage boundaries crossed by any shoe this week.
    - Next race: the soonest upcoming PlannedRace with days/weeks remaining and target pace.

    Call this before composing the weekly_rotation_summary digest, or to answer
    "how was my week?" / "what shoes am I using most?". Read-only — no writes.
    """
    with _core.get_session() as db:
        s = weekly_summary_svc.weekly_summary(db)
        return {
            "week": {"start": s.week_start, "end": s.week_end},
            "volume": {
                "this_week_km": s.this_week_km,
                "last_week_km": s.last_week_km,
                "delta_km": s.delta_km,
            },
            "per_shoe_usage": [
                {
                    "shoe_id": u.shoe_id,
                    "brand": u.brand,
                    "model": u.model,
                    "nickname": u.nickname,
                    "shoe_type": u.shoe_type,
                    "km_this_week": u.km_this_week,
                    "run_count": u.run_count,
                }
                for u in s.per_shoe_usage
            ],
            "pipeline": [
                {
                    "shoe_id": p.shoe_id,
                    "brand": p.brand,
                    "model": p.model,
                    "nickname": p.nickname,
                    "pct": p.pct,
                    "current_mileage": p.current_mileage,
                    "mileage_limit": p.mileage_limit,
                    "replacement_deals": p.replacement_deals,
                    "forecast_status": p.forecast_status,
                    "weekly_km": p.weekly_km,
                    "weeks_to_limit": p.weeks_to_limit,
                    "projected_limit_date": p.projected_limit_date,
                }
                for p in s.pipeline
            ],
            "notable_runs": [
                {
                    "run_date": n.run_date,
                    "distance_km": n.distance_km,
                    "avg_pace": n.avg_pace,
                    "avg_hr": n.avg_hr,
                    "activity_tag": n.activity_tag,
                    "name": n.name,
                    "shoe": n.shoe,
                }
                for n in s.notable_runs
            ],
            "checkpoints_this_week": [
                {
                    "shoe_id": c.shoe_id,
                    "brand": c.brand,
                    "model": c.model,
                    "checkpoint_km": c.checkpoint_km,
                    "triggered_at": c.triggered_at,
                }
                for c in s.checkpoints_this_week
            ],
            "next_race": (
                {
                    "name": s.next_race.name,
                    "race_date": s.next_race.race_date,
                    "days_remaining": s.next_race.days_remaining,
                    "weeks_remaining": s.next_race.weeks_remaining,
                    "distance_km": s.next_race.distance_km,
                    "target_pace": s.next_race.target_pace,
                }
                if s.next_race else None
            ),
        }


@mcp.resource(
    "strava://runs/{year}/{month}",
    name="Strava Runs by Month",
    description="Imported Strava runs for a given year/month, so a chat can pull one month without flooding context",
    mime_type="application/json",
)
def strava_runs_by_month_resource(year: str, month: str) -> str:
    """Imported Strava runs for a single month (year/month as YYYY / MM or M)."""
    import json
    from calendar import monthrange
    from datetime import date as _date

    try:
        y, m = int(year), int(month)
        start = _date(y, m, 1)
        end = _date(y, m, monthrange(y, m)[1])
    except (ValueError, TypeError):
        return f"Invalid year/month: {year}/{month} (expected e.g. 2026/07)"

    with _core.get_session() as db:
        runs = (
            db.query(Activity)
            .filter(
                Activity.source == "strava",
                Activity.activity_type == "Run",
                Activity.run_date >= start,
                Activity.run_date <= end,
            )
            .order_by(Activity.run_date)
            .all()
        )

        total_km = round(sum(r.distance_km or 0.0 for r in runs), 1)
        md_lines = [
            f"# Strava Runs — {y}-{m:02d}",
            f"_{len(runs)} run{'s' if len(runs) != 1 else ''} · {total_km}km total_",
            "",
            "| Date | Distance | Pace | HR | Gear |",
            "|------|----------|------|----|------|",
        ]
        run_dicts = []
        for r in runs:
            date_str = r.run_date.strftime("%b %d") if r.run_date else "—"
            pace = rotation.seconds_to_pace(r.avg_pace_s_per_km) if r.avg_pace_s_per_km else "—"
            hr = f"{r.avg_hr}bpm" if r.avg_hr else "—"
            gear = r.gear_name or "—"
            md_lines.append(f"| {date_str} | {r.distance_km:.1f}km | {pace} | {hr} | {gear} |")
            run_dicts.append({
                "strava_activity_id": r.strava_activity_id,
                "run_date": r.run_date.isoformat() if r.run_date else None,
                "distance_km": r.distance_km,
                "avg_pace": pace if pace != "—" else None,
                "avg_hr": r.avg_hr,
                "gear_name": r.gear_name,
                "name": r.name,
            })

        markdown = "\n".join(md_lines)
        payload = json.dumps(
            {"year": y, "month": m, "total_km": total_km, "runs": run_dicts},
            default=str,
        )
        return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "training://summary",
    name="Training Summary",
    description="Last 12 weeks of training volume, pace, HR, and elevation — for chat pre-priming",
    mime_type="application/json",
)
def training_summary_resource() -> str:
    """Last 12 weeks of weekly training data for chat pre-priming."""
    import json
    from datetime import date as _date, timedelta

    today = _date.today()
    date_from = today - timedelta(weeks=12)

    with _core.get_session() as db:
        buckets = strava_stats.training_summary(db, period="weekly", date_from=date_from)

    md_lines = [
        "# Training Summary (last 12 weeks)",
        "",
        "| Week | Distance | Runs | Avg Pace | Avg HR | Elevation |",
        "|------|----------|------|----------|--------|-----------|",
    ]
    for b in buckets:
        pace = b.avg_pace or "—"
        hr = f"{b.avg_hr}bpm" if b.avg_hr else "—"
        elev = f"{round(b.elevation_gain_m)}m" if b.elevation_gain_m else "—"
        md_lines.append(f"| {b.period} | {b.total_km:.1f}km | {b.run_count} | {pace} | {hr} | {elev} |")

    if not buckets:
        md_lines.append("_No runs in the last 12 weeks._")

    markdown = "\n".join(md_lines)
    payload = json.dumps(
        {
            "period": "weekly",
            "date_from": date_from.isoformat(),
            "date_to": today.isoformat(),
            "buckets": [
                {
                    "period": b.period,
                    "total_km": b.total_km,
                    "run_count": b.run_count,
                    "avg_pace": b.avg_pace,
                    "avg_hr": b.avg_hr,
                    "elevation_gain_m": b.elevation_gain_m,
                }
                for b in buckets
            ],
        },
        default=str,
    )
    return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "training://fitness",
    name="Fitness Metrics",
    description="Latest COROS athlete fitness snapshot: VO2 max, threshold pace, race predictions, running level",
    mime_type="application/json",
)
def training_fitness_resource() -> str:
    """Latest athlete fitness snapshot from COROS, for chat pre-priming alongside training://summary."""
    import json

    with _core.get_session() as db:
        snap = fitness_svc.latest(db)

    if snap is None:
        no_data = "# Fitness Metrics\n\n_No fitness data recorded yet. Call `sync_coros_now` to read it from COROS._"
        return f"{no_data}\n\n```json\n{{\"has_data\": false}}\n```"

    threshold_pace = rotation.seconds_to_pace(snap.threshold_pace_s_per_km) if snap.threshold_pace_s_per_km else None
    captured = fitness_svc.captured_local_date(snap).isoformat() if snap.captured_at else "—"

    md_lines = [f"# Fitness Metrics (as of {captured})", ""]
    if snap.vo2max is not None:
        md_lines.append(f"**VO2 Max:** {snap.vo2max:.1f} ml/kg/min")
    if threshold_pace:
        md_lines.append(f"**Threshold pace:** {threshold_pace}")
    if snap.running_level is not None:
        md_lines.append(f"**Running level:** {snap.running_level:.1f}")

    if snap.race_predictions:
        distance_labels = {
            "5.0": "5k", "10.0": "10k", "21.0975": "Half marathon", "42.195": "Marathon"
        }
        md_lines += ["", "**Race predictions:**", "| Distance | Predicted |", "|----------|-----------|"]
        for dist_str, seconds in sorted(snap.race_predictions.items(), key=lambda x: float(x[0])):
            label = distance_labels.get(dist_str, f"{dist_str} km")
            h, rem = divmod(int(seconds), 3600)
            m, s = divmod(rem, 60)
            time_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            md_lines.append(f"| {label} | {time_str} |")

    markdown = "\n".join(md_lines)
    payload = json.dumps(
        {
            "has_data": True,
            "captured_at": snap.captured_at.isoformat() if snap.captured_at else None,
            "vo2max": snap.vo2max,
            "threshold_pace_s_per_km": snap.threshold_pace_s_per_km,
            "threshold_pace": threshold_pace,
            "running_level": snap.running_level,
            "race_predictions": snap.race_predictions,
        },
        default=str,
    )
    return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.prompt()
def sync_fitness() -> str:
    """
    Sync COROS athlete fitness metrics (VO2 max, threshold pace, race
    predictions, running level) into Anton's Training tab fitness card.
    Normally one call to sync_coros_now; the connector + confirm steps are
    the fallback when Anton's own COROS connection is down.
    """
    return """# COROS Fitness Sync Agent

You are syncing athlete-level fitness metrics from COROS into Anton.

## Step 0 — Use Anton's own COROS sync (normal path)
Call `sync_coros_now`. Anton reads COROS fitness itself and saves a snapshot
when it changed — no confirmation needed (C13). Report the returned
`fitness` values (and whether they changed), then stop.
Only if it fails because COROS isn't connected, fall back to the steps below.

## Step 1 — Fetch fitness assessment from COROS (fallback)
Call `queryFitnessAssessmentOverview` from the COROS MCP connector.
This returns VO2 max, lactate-threshold pace, race predictions, and
running level. Do NOT call record_athlete_metrics yet.

## Step 2 — Present the fetched values for confirmation (C9)
Show every metric you received in a clear table, e.g.:

"COROS reports the following fitness metrics — confirm to record?

| Metric | Value |
|--------|-------|
| VO2 Max | 62.0 ml/kg/min |
| Threshold pace | 3:45/km (225 s/km) |
| Running level | 74.5 |
| Race predictions | 5k: 19:15 · 10k: 40:00 · HM: 1:28:30 · Marathon: 3:03:00 |

Record this snapshot? (yes/no)"

Convert threshold pace to seconds/km for storage (e.g. 3:45/km → 225).
Convert race prediction times to seconds for storage.
Format race_predictions as {"5.0": <s>, "10.0": <s>, "21.0975": <s>, "42.195": <s>}.
Include only distances the COROS response actually provides.

## Step 3 — Wait for runner confirmation
Do NOT call record_athlete_metrics until the runner says yes (or equivalent).
If the runner corrects a value, use the corrected version.

## Step 4 — Record the confirmed snapshot
Call record_athlete_metrics with the confirmed values:
- vo2max (Float, ml/kg/min)
- threshold_pace_s_per_km (Integer, seconds/km)
- race_predictions (dict, distance string → seconds Integer)
- running_level (Float)

## Step 5 — Confirm success
"Fitness snapshot recorded (captured_at: <timestamp>). The Training tab
fitness card will now show the updated metrics."

## General rules
- Never record metrics without explicit runner confirmation (C9)
- Never invent or extrapolate values not present in the COROS response
- If queryFitnessAssessmentOverview fails or returns no data, say so and stop
- Keep the tone direct and concise
"""


@mcp.tool()
def get_race_block_context(weeks_back: int = 12, as_of: Optional[str] = None) -> dict:
    """
    Compile the race-block training context for the advisor prompt (R3.6), and
    answer "am I ready for my next race?" (R8.4.4).

    Returns a structured snapshot covering:
    - Next upcoming race: name, date, distance, days/weeks to race, target pace.
    - Recent weekly volumes: last `weeks_back` weeks of km, run count, avg pace,
      avg HR — newest first. Used to assess whether current volume is on track
      for the goal race.
    - Retirement pipeline: active shoes at ≥ 75% of their mileage limit.
      Includes shoe_type so you can flag race-shoe wear concerns specifically.
    - Latest fitness snapshot: VO2 max, lactate-threshold pace (as "M:SS/km"),
      race predictions, and running level from COROS (if ever synced).
    - `readiness`: the same readiness checklist the Training page shows
      (`GET /api/races/readiness`). `readiness.has_race` false → no race ahead;
      don't talk about readiness. Otherwise `readiness.checklist` is a list of
      items {key, label, status, rule, value, target, unit}: weeks_to_go and
      peak_week are `info`; longest_run, long_runs (runs ≥ `long_run_km` in the
      block — 28 km for a marathon) and key_effort (the recent best effort at
      ~half race distance vs. target pace, in s/km — lower is faster) are
      `met` / `not_met`, or `n/a` with the reason in `rule`. Quote the numbers
      and the rule; it is a heuristic checklist, NOT a score — never sum it
      into one. The block is `block_start`→`block_end` (a fixed number of
      weeks ending race week, by race distance); `recent_efforts` carry
      `vs_target_s_per_km` (negative = faster than target pace).

    This is read-only — no writes, no confirmation gate needed.
    Call this before running the race_block_advisor prompt, or for "am I ready
    for my race?".

    Args:
        weeks_back: Number of recent weekly buckets to include (default 12, max 52).
        as_of: ISO date to answer for (default today). Use a past date to ask
            "was I ready for <race>?" — a completed race still counts before its date.
    """
    from dataclasses import asdict
    from datetime import date as _date
    try:
        day = _date.fromisoformat(as_of) if as_of else None
    except ValueError:
        return {"error": "as_of must be an ISO date (YYYY-MM-DD)"}
    weeks_back = max(1, min(weeks_back, 52))
    with _core.get_session() as db:
        ctx = race_advisor_svc.race_block_context(db, today=day, weeks_back=weeks_back)

    result: dict = {
        "readiness": asdict(ctx.readiness) if ctx.readiness else None,
        "has_next_race": ctx.has_next_race,
        "next_race": None,
        "recent_weeks": [
            {
                "period": w.period,
                "total_km": w.total_km,
                "run_count": w.run_count,
                "avg_pace": w.avg_pace,
                "avg_hr": w.avg_hr,
            }
            for w in ctx.recent_weeks
        ],
        "avg_weekly_km": ctx.avg_weekly_km,
        "pipeline": [
            {
                "shoe_id": p.shoe_id,
                "brand": p.brand,
                "model": p.model,
                "nickname": p.nickname,
                "shoe_type": p.shoe_type,
                "pct": p.pct,
                "current_mileage": p.current_mileage,
                "mileage_limit": p.mileage_limit,
                "replacement_deals": p.replacement_deals,
                "forecast_status": p.forecast_status,
                "weekly_km": p.weekly_km,
                "weeks_to_limit": p.weeks_to_limit,
                "projected_limit_date": p.projected_limit_date,
            }
            for p in ctx.pipeline
        ],
        "has_fitness": ctx.has_fitness,
        "fitness": None,
    }

    if ctx.next_race:
        r = ctx.next_race
        result["next_race"] = {
            "name": r.name,
            "race_date": r.race_date,
            "distance_km": r.distance_km,
            "days_to_race": r.days_to_race,
            "weeks_to_race": r.weeks_to_race,
            "target_pace": r.target_pace,
            "target_time_s": r.target_time_s,
        }

    if ctx.fitness:
        f = ctx.fitness
        result["fitness"] = {
            "vo2max": f.vo2max,
            "threshold_pace": f.threshold_pace,
            "race_predictions": f.race_predictions,
            "running_level": f.running_level,
            "captured_at": f.captured_at,
        }

    return result


@mcp.prompt()
def race_block_advisor() -> str:
    """
    Generate race-block training observations for the runner's current goal race.

    Reads the race countdown, recent weekly volumes, rotation state, and fitness
    metrics to produce block-level observations — where the runner stands now,
    what the volume trend implies, and any rotation concerns for race day.
    Advisory observations only; no detailed training plan generation.
    Read-only — no writes, no confirmation gate.
    """
    return """# Race-Block Training Advisor

You are producing training-block observations for a competitive runner.
This is READ-ONLY — no writes, no confirmation gates. Advisory only.

## Step 1 — Fetch the context
Call `get_race_block_context()`. It returns the next race, recent weekly
volumes, rotation pipeline state, latest fitness metrics, and the readiness
checklist (`readiness`).

## Step 2 — Produce the advisory

Use the structure below. Omit any section whose data is absent.

---
**Race-Block Summary**

### Goal Race
[If has_next_race:]
**[next_race.name]** — [next_race.race_date]
[days_to_race] days / [weeks_to_race] weeks out[", [next_race.distance_km] km" if distance_km set]
[If target_pace: "Target pace: [target_pace]"]
[Else if no race: "No upcoming races scheduled — observations are general."]

### Volume (last [count of recent_weeks] weeks)
Average: [avg_weekly_km] km/week

[List recent_weeks newest-first, one line each:]
[period] — [total_km] km · [run_count] run(s)[" · " + avg_pace if avg_pace]

**Trend observation:**
[Compare the most recent 2–3 weeks against the 12-week average. Examples:]
- If recent weeks are well above average: "Volume is above the block average — monitor fatigue
  and ensure adequate recovery before [race name]."
- If recent weeks are declining: "Volume has dropped vs the block average. If intentional
  (taper), this is appropriate at [weeks_to_race] weeks out; otherwise worth checking."
- If stable: "Volume is consistent with the block average."
[If has_next_race and weeks_to_race ≤ 3: "At [weeks_to_race] week(s) out, taper should be underway."]
[If has_next_race and weeks_to_race is between 4 and 8: "In the race-specific phase — quality over
 quantity; key workouts at target pace matter more than peak volume."]
[If has_next_race and weeks_to_race > 8: "Still in the base-building window — volume consistency
 is the priority."]

### Readiness
[If readiness.has_race:]
[For each item in readiness.checklist, one line:]
- [label]: [value][" " + unit] [" (target " + target + ")" if target set] — [status] · [rule]
  [For s/km values show them as M:SS/km.]
[Then one sentence naming the not_met items — no score, no verdict word.]

### Rotation
[If pipeline is non-empty:]
[For each shoe in pipeline:]
- **[brand] [model]**[" ([nickname])" if nickname] — [pct×100 rounded to 0dp]%
  of limit ([current_mileage]/[mileage_limit] km)[", type: " + shoe_type if shoe_type]
  [If shoe_type and "Race" in shoe_type and has_next_race:
   "Race shoe at this mileage — consider the replacement timeline vs race day."]
  [If replacement_deals > 0: "[replacement_deals] replacement deal(s) available."]
[Else: "No shoes in the retirement pipeline."]

### Fitness
[If has_fitness:]
VO2 Max: [vo2max if set, else "—"] · Threshold pace: [threshold_pace if set, else "—"]
[If running_level: "Running level: [running_level]"]
[If race_predictions and has_next_race and next_race.distance_km set:]
  [Find the closest distance key in race_predictions to next_race.distance_km:]
  Predicted time at [distance_km] km: [format total_s as H:MM:SS or M:SS depending on length]
[If threshold_pace and has_next_race and next_race.target_pace:
  Compare threshold_pace and target_pace: note if target pace is faster or slower than threshold.
  E.g.: "Target pace ([target_pace]) is [X sec/km] faster than threshold ([threshold_pace]) —
  a demanding goal requiring sustained anaerobic contribution."]
[Else if has_next_race and not has_fitness: "No fitness snapshot on record — sync COROS via
 the sync_fitness prompt for VO2 max and race predictions."]

---

## Rules
- Never invent data not present in get_race_block_context's response
- Volume trend: compare the two most recent non-zero weeks to avg_weekly_km
  (a single anomalous week isn't a trend)
- pct display: multiply by 100 and round to the nearest whole number
- Keep observations concrete and grounded in the numbers; no cheerleading
- Do not generate a full training plan — point out where the runner stands and
  flag concerns; the runner decides what to do with them
- If weeks_to_race ≤ 0, the race is today or in the past — note that and pivot
  to "next goal race" framing if another race exists
"""
