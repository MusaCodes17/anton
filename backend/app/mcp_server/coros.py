"""COROS sync MCP surface: connection status, manual sync, unsynced-run inbox, run confirmation."""
import asyncio
from typing import Optional
from datetime import date as date_type

from app.utils.activity_tags import ACTIVITY_TAGS, is_valid_tag
from app.services import rotation, coros as coros_svc, settings as settings_svc, fitness as fitness_svc, coros_connection as coros_connection_svc, coros_poller as coros_poller_svc, coros_inbox as coros_inbox_svc
from app.mcp_server import _core
from app.mcp_server._core import mcp
from app.mcp_server._shared import _owned_shoe_to_dict


@mcp.tool()
def get_coros_sync_status() -> dict:
    """
    Report the state of Anton's direct COROS sync: whether the connection is
    live, when the background poller last succeeded, the last error (if any),
    and how many new runs are waiting for review. Use this before
    fetch_unsynced_coros_runs. `connection_status` is one of connected,
    reauth_required (the runner must reconnect in Settings → Sync), or
    disconnected. Read-only.
    """
    with _core.get_session() as db:
        conn = coros_connection_svc.get_status(db)
        summary = coros_poller_svc.get_sync_summary(db)
        last_confirm = settings_svc.get_setting(db, "last_coros_sync_at")
    status = conn["status"]
    if not conn["configured"]:
        message = "Direct COROS sync isn't set up on the server (COROS_TOKEN_KEY missing)."
    elif status == "connected":
        message = (f"COROS is connected. {summary['pending_count']} run(s) waiting. "
                   "Call fetch_unsynced_coros_runs to review them.")
        if summary["last_error"]:
            message += f" The last poll failed: {summary['last_error']}"
    elif status == "reauth_required":
        message = "COROS needs to be reconnected (Settings → Sync → Reconnect COROS). No new runs are arriving."
    else:
        message = "COROS is not connected. Connect it in Settings → Sync."
    return {
        "coros_configured": status == "connected",   # legacy key: "direct sync usable right now"
        "connection_status": status,
        "last_success_at": summary["last_success_at"],
        "last_attempt_at": summary["last_attempt_at"],
        "last_error": summary["last_error"],
        "pending_count": summary["pending_count"],
        "poll_interval_min": summary["poll_interval_min"],
        "last_sync_at": last_confirm,                # legacy: when a run was last confirmed
        "message": message,
    }


@mcp.tool()
async def sync_coros_now() -> dict:
    """
    Run Anton's COROS sync right now — the same sync as the app's "Sync now"
    button and the background poller (about every 15 minutes). It pulls new
    runs into the "New runs" inbox and reads the runner's COROS fitness (VO2 max,
    running level, threshold pace, race predictions), saving a fitness snapshot
    when it changed. Use it when the user asks to sync, refresh or update their
    runs or fitness, or when fitness data looks stale.

    No confirmation needed: it never logs a run or touches mileage (new runs
    wait in the inbox — present them with fetch_unsynced_coros_runs and log
    each through confirm_coros_run as usual), and a fitness snapshot is a
    reading COROS computed, saved as-is (design decisions C13).

    Returns `queued` (new runs added to the inbox), `pending_count`,
    `fitness_recorded` (whether the reading changed), the latest `fitness`
    snapshot, and `errors`. `success` is False when COROS isn't connected or a
    sync is already running.
    """
    def _run() -> dict:
        # Own session in the worker thread (one session per thread, CLAUDE.md §9).
        with _core.get_session() as db:
            result = coros_poller_svc.run_tick(db, trigger="manual")
            if result.skipped == "not_connected":
                return {"success": False, "error": "COROS isn't connected. Connect it in Settings → Sync."}
            if result.skipped == "already_running":
                return {"success": False, "error": "A COROS sync is already running; try again in a moment."}
            snap = fitness_svc.latest(db)
            return {
                "success": result.ok,
                "found": result.found,
                "queued": result.queued,
                "pending_count": coros_poller_svc.get_sync_summary(db)["pending_count"],
                "fitness_recorded": result.fitness_recorded,
                "fitness": None if snap is None else {
                    "captured_at": snap.captured_at.isoformat() if snap.captured_at else None,
                    "vo2max": snap.vo2max,
                    "running_level": snap.running_level,
                    "threshold_pace": rotation.seconds_to_pace(snap.threshold_pace_s_per_km)
                    if snap.threshold_pace_s_per_km else None,
                    "race_predictions_s": snap.race_predictions,
                },
                "errors": result.errors,
            }

    # run_tick makes blocking COROS calls; keep them off the event loop.
    return await asyncio.to_thread(_run)


@mcp.tool()
def fetch_unsynced_coros_runs(days_back: int = 30) -> dict:
    """
    Return the runs waiting in Anton's "New runs" inbox — the same queue the
    app shows. A background poller pulls them from COROS about every 15
    minutes, already deduplicated against logged runs and with detail
    prefetched, so there is nothing to look up in COROS first. Each run
    carries `suggested_shoe_id` / `suggestion_reason` (the same heuristic the
    app uses; may be null). Present them to the user for shoe assignment,
    then call confirm_coros_run for each confirmed one, passing the fields
    below through unchanged. Read-only; never logs anything.

    Args:
        days_back: Ignored — kept so older callers don't break. The queue
            holds every unresolved run regardless of age.
    """
    with _core.get_session() as db:
        runs = [
            {
                "coros_activity_id": r["label_id"],
                "date": r["run_date"],
                "distance_km": r["distance_km"],
                "avg_pace": r["avg_pace"],
                "avg_hr": r["avg_hr"],
                "moving_time_s": r["moving_time_s"],
                "elapsed_time_s": r["elapsed_time_s"],
                "elevation_gain_m": r["elevation_gain_m"],
                "avg_cadence": r["avg_cadence"],
                "calories": r["calories"],
                "training_load": r["training_load"],
                "training_focus": r["training_focus"],
                "suggested_shoe_id": r["suggested_shoe_id"],
                "suggestion_reason": r["suggestion_reason"],
            }
            for r in coros_inbox_svc.list_pending(db)
        ]
        conn = coros_connection_svc.get_status(db)
        summary = coros_poller_svc.get_sync_summary(db)

    result = {
        "success": True,
        "coros_configured": conn["status"] == "connected",
        "connection_status": conn["status"],
        "runs": runs,
        "already_synced": 0,
        "total_fetched": len(runs),
        "last_success_at": summary["last_success_at"],
    }
    if conn["status"] != "connected":
        result["warning"] = (
            "COROS isn't connected, so no new runs are arriving; the list above is only what was "
            "queued earlier. Reconnect in Settings → Sync."
            if conn["status"] == "reauth_required"
            else "COROS isn't connected. Connect it in Settings → Sync to receive new runs."
        )
    return result


@mcp.tool()
def confirm_coros_run(
    coros_activity_id: str,
    owned_shoe_id: int,
    date: str,
    distance_km: float,
    avg_pace: Optional[str] = None,
    avg_hr: Optional[int] = None,
    notes: Optional[str] = None,
    name: Optional[str] = None,
    elevation_gain_m: Optional[float] = None,
    moving_time_s: Optional[int] = None,
    elapsed_time_s: Optional[int] = None,
    avg_cadence: Optional[float] = None,
    calories: Optional[float] = None,
    training_load: Optional[float] = None,
    training_focus: Optional[str] = None,
    activity_tag: Optional[str] = None,
) -> dict:
    """
    Log a single COROS run to an owned shoe after the user confirms the
    assignment. Call this once per run after fetching unsynced runs and
    getting the user's shoe choice for each. Also clears the run from the
    app's "New runs" inbox, and is safe to repeat: a run already logged
    (by Claude or the app) returns success=False "already logged" instead
    of logging twice.

    Args:
        coros_activity_id: The COROS labelId for this run.
        owned_shoe_id: ID of the owned shoe to log it against.
        date: Run date in YYYY-MM-DD format.
        distance_km: Distance covered in kilometers.
        avg_pace: Average pace as "M:SS/km", e.g. "4:32/km".
        avg_hr: Average heart rate in bpm.
        notes: Optional notes about this run.
        name: COROS activity name/title (e.g. "Morning Run").
        elevation_gain_m: Total ascent in metres.
        moving_time_s / elapsed_time_s: Moving vs total elapsed time, seconds.
        avg_cadence: Average cadence (steps/min).
        calories: Energy in kcal.
        training_load: COROS training-load score for the run.
        training_focus: COROS coaching label (e.g. "Aerobic base").
        activity_tag: One of the ACTIVITY_TAGS vocabulary values (Easy, Long
            Run, Recovery, Tempo, Intervals, Track, Workout, Trail, Parkrun,
            Race). Only pass a tag the runner has CONFIRMED — never infer and
            apply one silently (C9). Omit if the runner didn't set one.
    """
    if activity_tag is not None and not is_valid_tag(activity_tag):
        return {
            "success": False,
            "error": f"'{activity_tag}' is not a valid activity_tag. "
                     f"Use one of: {', '.join(ACTIVITY_TAGS)}.",
        }
    with _core.get_session() as db:
        try:
            result = coros_svc.confirm_run(
                db,
                coros_activity_id=coros_activity_id,
                owned_shoe_id=owned_shoe_id,
                run_date=date_type.fromisoformat(date),
                distance_km=distance_km,
                avg_pace=avg_pace,
                avg_hr=avg_hr,
                notes=notes,
                name=name,
                elevation_gain_m=elevation_gain_m,
                moving_time_s=moving_time_s,
                elapsed_time_s=elapsed_time_s,
                avg_cadence=avg_cadence,
                calories=calories,
                training_load=training_load,
                training_focus=training_focus,
                activity_tag=activity_tag,
            )
        except LookupError:
            return {"success": False, "error": f"Owned shoe {owned_shoe_id} not found"}

        if result is None:
            return {"success": False, "error": f"Run {coros_activity_id} is already logged"}

        stats = rotation.compute_lifetime_stats(db, result.shoe.id)
        return {
            "success": True,
            "checkpoint_reached": result.checkpoint_reached,
            "checkpoint_km": result.checkpoint_km,
            "shoe": _owned_shoe_to_dict(result.shoe, stats),
        }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@mcp.prompt()
def sync_coros_runs(days_back: int = 2) -> str:
    """
    Review the runs waiting in Anton's "New runs" inbox (pulled from COROS
    by the backend poller) and assign them to shoes in your rotation.
    Suggests shoe assignments based on pace and distance, and logs
    confirmed runs after your review.
    """
    return f"""# COROS Sync Agent

You are acting as a COROS run sync agent for Anton, the user's
personal running platform. Follow this exact process.

## Step 1 — Get the queued runs from Anton
Call fetch_unsynced_coros_runs. Anton's backend polls COROS itself about
every 15 minutes, so this returns the same "New runs" inbox the app shows:
already deduplicated against logged runs, with the rich per-run detail
(elevation, times, cadence, calories, load, focus) already attached and a
server-side shoe suggestion (`suggested_shoe_id`, `suggestion_reason`).
Do NOT query the COROS connector to build this list.

If `runs` is empty, say so and stop. If `warning` is present (COROS not
connected / reconnect needed), relay it — the runner fixes that in
Settings → Sync. You may call get_coros_sync_status for details.

## Step 2 — Get current rotation
Call get_owned_shoes to see all active shoes with their shoe_type
and current mileage.

## Step 3 — Suggest shoe assignment for each run
For each unsynced run, reason about the best shoe match using BOTH
signals below — do not rely on pace alone.

Each queued run already carries a suggestion computed by exactly the rules
below. Start from it; apply your own judgement only when it is null or you
have a clear reason to differ (say why).

### Pace signal (primary)
- < 3:30/km → favors short_distance_racer or intervals
- 3:30–4:15/km → favors tempo long_distance_racer or tempo
- 4:00–4:30/km → favors long_run
- 4:30–5:30/km → favors daily_trainer
- > 5:30/km → favors recovery or daily_trainer

### Distance signal (secondary, refines the pace signal)
- < 5km → favors intervals or short_distance_racer
- 5–16km → favors daily_trainer
- 16–22km → favors tempo or daily_trainer
- > 21km → favors long_run or long_distance_racer

### Resolution
- If pace and distance signals agree on a shoe_type, that's the
  suggestion.
- If they conflict, pick the shoe_type with an active shoe in the
  rotation, preferring the one with lower current mileage.
- Only suggest shoes that are status=active. Never suggest a
  retired shoe.
- If multiple active shoes share the matched shoe_type, suggest
  the one with lower mileage (spread wear more evenly).
- If no shoe in the rotation matches the inferred shoe_type, say so
  explicitly rather than forcing a bad match.

## Step 4 — Present all suggestions together
Show every unsynced run with its suggested shoe and a brief reason,
in a single structured response.

Format:
"Here are my suggestions for [N] unsynced runs:

[Date] · [distance]km · [pace]/km · [hr]bpm
→ [Brand Model] ([shoe_type], [current_mileage]km)
Reason: [one short sentence]

...repeat for each run...

Confirm all, adjust specific runs, or skip any?"

## Step 5 — Wait for user confirmation
Do not log anything until the user responds. Accept any natural
language mix of confirmations, changes, and skips. If ambiguous,
ask for clarification.

## Step 6 — Log confirmed runs

For EACH confirmed run call confirm_coros_run with the values exactly as
returned by fetch_unsynced_coros_runs — the detail is already prefetched, so
do NOT call getActivityDetail:
- coros_activity_id, owned_shoe_id (the confirmed shoe)
- date, distance_km, avg_pace, avg_hr
- moving_time_s, elapsed_time_s, elevation_gain_m, avg_cadence, calories,
  training_load, training_focus (omit any that are null)

COROS provides no run name, so only suggest an activity_tag if the runner
told you what the run was (e.g. "that was the tempo"); the vocabulary is
Easy, Long Run, Recovery, Tempo, Intervals, Track, Workout, Trail, Parkrun,
Race. Never apply a tag without the runner's confirmation (C9); omit it
otherwise.

Runs the user skips simply stay in the inbox (they are not dismissed) — tell
them they can dismiss a run in the app (New runs → Dismiss) if it should not
count toward any shoe.

## Step 7 — Summarise results
"Logged [N] runs:
- [Shoe name]: +[total km added]km (now [new total]km)
...
[Skipped: N runs]"

## Step 8 — Proactive threshold check
For any shoe that crossed 600km, 700km, or 800km, flag it and offer
to check replacement deals or add a note.

## General rules
- Never log a run without explicit user confirmation
- Never invent data — every field comes from fetch_unsynced_coros_runs
  (Step 1)
- If confirm_coros_run says a run is "already logged", it was handled
  elsewhere (e.g. in the app) — note it and move on
- If confirm_coros_run returns success: false for any run, report
  the specific error and continue processing the rest
- Keep the tone direct and concise — this user is a competitive
  runner who wants clear information, not chattiness
"""
