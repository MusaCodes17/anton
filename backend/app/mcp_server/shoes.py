"""Rotation MCP surface: owned shoes, run attribution, notes, reviews, mileage limits, retirement."""
from typing import List, Optional
from datetime import date as date_type

from mcp import types as mcp_types
from mcp.server.fastmcp import Context
from sqlalchemy import desc
from sqlalchemy.orm import contains_eager
from app.models.models import Activity, OwnedShoe, ShoeNote, ShoeRun
from app.utils.shoe_types import default_mileage_limit
from app.utils.activity_tags import ACTIVITY_TAGS, is_valid_tag
from app.services import rotation
from app.mcp_server import _core
from app.mcp_server._core import mcp
from app.mcp_server._shared import _SOURCE_BADGES, _format_mileage_bar, _owned_shoe_payload, _owned_shoes_payload, _shoe_note_payload, _shoe_run_payload


@mcp.tool()
def get_owned_shoes(status_filter: Optional[str] = None) -> List[dict]:
    """
    List shoes in the user's personal rotation with current mileage and
    status. Use this for "what shoes do I have", "which shoes are near
    retirement", or to look up an owned_shoe_id before calling another tool.

    Args:
        status_filter: Filter by status — "active", "retired", or
            "for_sale". Omit for all shoes regardless of status.
    """
    with _core.get_session() as db:
        query = db.query(OwnedShoe)
        if status_filter:
            query = query.filter(OwnedShoe.status == status_filter)
        shoes = query.order_by(OwnedShoe.created_at.desc()).all()
        return _owned_shoes_payload(db, shoes)


@mcp.tool()
def get_shoe_runs(owned_shoe_id: int) -> dict:
    """
    Get the run history logged against an owned shoe (newest first), plus
    that shoe's lifetime average pace, average heart rate, and run count.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
    """
    with _core.get_session() as db:
        runs = (
            db.query(ShoeRun)
            .join(Activity, ShoeRun.activity_id == Activity.id)
            .options(contains_eager(ShoeRun.activity))
            .filter(ShoeRun.owned_shoe_id == owned_shoe_id)
            .order_by(desc(Activity.run_date), desc(ShoeRun.created_at))
            .all()
        )
        stats = rotation.compute_lifetime_stats(db, owned_shoe_id)
        return {
            "owned_shoe_id": owned_shoe_id,
            "runs": [_shoe_run_payload(r) for r in runs],
            "lifetime_avg_pace": stats.lifetime_avg_pace,
            "lifetime_avg_hr": stats.lifetime_avg_hr,
            "total_runs": stats.total_runs,
        }


@mcp.tool()
async def log_run_to_shoe(
    owned_shoe_id: int,
    distance_km: float,
    run_date: str,
    ctx: Context,
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
    Log a run against an owned shoe, adding to its current mileage.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
        distance_km: Distance covered in this run, in kilometers.
        run_date: Date of the run, in YYYY-MM-DD format.
        avg_pace: Optional average pace for the run, format "M:SS/km"
            (e.g. "3:52/km").
        avg_hr: Optional average heart rate for the run, in beats per minute.
        notes: Optional notes about the run.
        name: Activity name/title (e.g. "Morning Run").
        elevation_gain_m: Total ascent in metres.
        moving_time_s: Moving time in seconds.
        elapsed_time_s: Elapsed (wall-clock) time in seconds.
        avg_cadence: Average cadence in steps/min.
        calories: Energy in kcal.
        training_load: Training-load score.
        training_focus: Coaching label (e.g. "Aerobic base").
        activity_tag: One of the ACTIVITY_TAGS vocabulary values (Easy, Long
            Run, Recovery, Tempo, Intervals, Track, Workout, Trail, Parkrun,
            Race). Only pass a tag the runner has CONFIRMED (C9).
    """
    if activity_tag is not None and not is_valid_tag(activity_tag):
        return {
            "success": False,
            "error": f"'{activity_tag}' is not a valid activity_tag. "
                     f"Use one of: {', '.join(ACTIVITY_TAGS)}.",
        }
    try:
        with _core.get_session() as db:
            shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
            if not shoe:
                return {"success": False, "error": f"Owned shoe with id {owned_shoe_id} not found"}

            result = rotation.log_run(
                db,
                owned_shoe_id,
                distance_km=distance_km,
                run_date=date_type.fromisoformat(run_date),
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
            shoe = result.shoe

            threshold_crossed, threshold_message = result.threshold_crossed, result.threshold_message

            if threshold_crossed is not None:
                try:
                    await ctx.log(
                        "warning",
                        f"⚠️ {shoe.brand} {shoe.model} has reached {threshold_crossed}km — {threshold_message}.",
                        logger_name="shoe-tracker",
                    )
                except Exception:
                    pass

            return {
                "success": True,
                "run_id": result.run.id,
                "shoe": f"{shoe.brand} {shoe.model}",
                "new_mileage": round(shoe.current_mileage, 2),
                "checkpoint_reached": result.checkpoint_reached,
                "checkpoint_km": result.checkpoint_km,
                "threshold_crossed": threshold_crossed,
                "threshold_message": threshold_message,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def delete_shoe_run(run_id: int) -> dict:
    """
    Delete a logged run, subtracting its distance back out of the parent
    shoe's current mileage.

    Args:
        run_id: ID of the run to delete (from get_shoe_runs).
    """
    try:
        with _core.get_session() as db:
            run = db.query(ShoeRun).filter(ShoeRun.id == run_id).first()
            if not run:
                return {"success": False, "error": f"Run with id {run_id} not found"}
            distance = run.activity.distance_km if run.activity else None
            try:
                shoe = rotation.delete_run(db, run_id)
            except LookupError as exc:
                return {"success": False, "error": str(exc)}
            return {"success": True, "removed_km": distance, "updated_mileage": round(shoe.current_mileage, 2)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_shoe_notes(owned_shoe_id: int) -> List[dict]:
    """
    Get the notes journal for an owned shoe (feel, observations, mileage
    checkpoints), newest first — replaces the old single free-text notes
    field with a timestamped, mileage-anchored history.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
    """
    with _core.get_session() as db:
        notes = (
            db.query(ShoeNote)
            .filter(ShoeNote.owned_shoe_id == owned_shoe_id)
            .order_by(desc(ShoeNote.created_at))
            .all()
        )
        return [_shoe_note_payload(n) for n in notes]


@mcp.tool()
def add_shoe_note(owned_shoe_id: int, body: str) -> dict:
    """
    Add a manual journal entry to an owned shoe's notes. The shoe's current
    mileage at the time of writing is recorded automatically alongside it.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
        body: The note content.
    """
    try:
        with _core.get_session() as db:
            try:
                note = rotation.add_note(db, owned_shoe_id, body)
            except LookupError as exc:
                return {"success": False, "error": str(exc)}
            shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
            return {
                "success": True,
                "note_id": note.id,
                "shoe": f"{shoe.brand} {shoe.model}",
                "mileage_at_note": note.mileage_at_note,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def draft_shoe_review(owned_shoe_id: int, ctx: Context) -> dict:
    """
    Draft a structured shoe review based on logged notes and run history
    for a specific owned shoe. Uses MCP sampling to generate the review
    text via the connected client's LLM — the server sends a sampling
    request back through the MCP protocol and the client handles the LLM
    call. Returns a structured review draft ready for editing and posting.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
    """
    with _core.get_session() as db:
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
        if not shoe:
            return {"success": False, "error": "Shoe not found"}

        notes = (
            db.query(ShoeNote)
            .filter(ShoeNote.owned_shoe_id == owned_shoe_id)
            .order_by(ShoeNote.created_at)
            .all()
        )
        if not notes:
            return {
                "success": False,
                "error": "No notes found for this shoe. Add some notes first via add_shoe_note.",
            }

        runs = (
            db.query(ShoeRun)
            .join(Activity, ShoeRun.activity_id == Activity.id)
            .options(contains_eager(ShoeRun.activity))
            .filter(ShoeRun.owned_shoe_id == owned_shoe_id)
            .order_by(Activity.run_date)
            .all()
        )

        stats = rotation.compute_lifetime_stats(db, owned_shoe_id)
        total_runs = stats.total_runs
        lifetime_avg_pace = stats.lifetime_avg_pace or "—"
        lifetime_avg_hr = stats.lifetime_avg_hr

        first_run_date = runs[0].activity.run_date.isoformat() if runs and runs[0].activity.run_date else "—"
        last_run_date = runs[-1].activity.run_date.isoformat() if runs and runs[-1].activity.run_date else "—"

        formatted_notes = "\n".join(
            f"- [{round(n.mileage_at_note)}km · {n.created_at.strftime('%Y-%m-%d') if n.created_at else '—'}] {n.body}"
            for n in notes
        )

        nickname_part = f" ({shoe.nickname})" if shoe.nickname else ""
        shoe_type = shoe.shoe_type or "unspecified"
        avg_hr_str = f"{lifetime_avg_hr}bpm" if lifetime_avg_hr else "—"

        context = f"""Shoe: {shoe.brand} {shoe.model}{nickname_part}
Type: {shoe_type}
Total distance: {round(shoe.current_mileage, 1)}km over {total_runs} runs
Period: {first_run_date} to {last_run_date}
Avg pace: {lifetime_avg_pace} | Avg HR: {avg_hr_str}
Status: {shoe.status}

Notes logged during use:
{formatted_notes}"""

        sampling_prompt = f"""Based on the following running shoe data and personal notes, write a structured shoe review suitable for posting on Reddit (r/RunningShoeGeeks or similar subreddit).

{context}

Format the review as:
## [Shoe Name] Review — [Total Distance]km

**The Shoe:** [1-2 sentence overview]

**What I Used It For:** [workout types based on shoe_type and pace data]

**The Good:** [positive observations from notes]

**The Bad:** [negative observations or limitations from notes]

**Mileage & Durability:** [observations about how it held up]

**Who Is It For:** [recommendation based on shoe_type and experience]

**Verdict:** [1-2 sentence summary and rating /10]

Keep it honest, specific, and useful. Use the notes as the primary source — do not invent observations not present in the notes."""

    try:
        result = await ctx.session.create_message(
            messages=[
                mcp_types.SamplingMessage(
                    role="user",
                    content=mcp_types.TextContent(type="text", text=sampling_prompt),
                )
            ],
            max_tokens=1000,
        )
        review_text = (
            result.content.text
            if isinstance(result.content, mcp_types.TextContent)
            else str(result.content)
        )
        # Auto-save the draft to the shoe so the runner can retrieve it later
        # without re-running the workflow. save_shoe_review overwrites this if
        # the runner edits the text and calls save_shoe_review explicitly.
        with _core.get_session() as save_db:
            rotation.store_shoe_review(save_db, owned_shoe_id, review_text)
        return {
            "success": True,
            "shoe": f"{shoe.brand} {shoe.model}",
            "mileage": round(shoe.current_mileage, 1),
            "review_draft": review_text,
            "saved": True,
            "note": "Draft saved to the shoe. Edit it and call save_shoe_review to update the stored version.",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Connected client does not support sampling. Try this tool from Claude Desktop. ({e})",
        }


@mcp.tool()
def save_shoe_review(owned_shoe_id: int, review_text: str) -> dict:
    """
    Persist a runner-edited shoe review draft on an owned shoe (R3.3).

    Call this after the runner has edited the text produced by draft_shoe_review.
    Overwrites the previously stored draft — only one review per shoe is kept.
    The stored text is returned by the shoes://review/{id} resource and exposed
    on the shoe via GET /api/owned-shoes/{id}.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
        review_text: The final (or further-edited) review text to store.
    """
    if not review_text or not review_text.strip():
        return {"success": False, "error": "review_text must not be empty"}
    try:
        with _core.get_session() as db:
            try:
                shoe = rotation.store_shoe_review(db, owned_shoe_id, review_text)
            except LookupError as exc:
                return {"success": False, "error": str(exc)}
            return {
                "success": True,
                "shoe": f"{shoe.brand} {shoe.model}",
                "review_stored": True,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def set_shoe_mileage_limit(owned_shoe_id: int, limit_km: Optional[float] = None) -> dict:
    """
    Change the km at which an owned shoe counts as due for replacement. Use this
    when the runner says a shoe still feels good past its limit (raise it) or
    wants it retired sooner (lower it). Omit limit_km to reset to the default
    for the shoe's type.

    The default is a heuristic and the runner's judgment wins, but make the
    trade-off explicit: the result includes recommended_limit_km, so tell the
    runner when the new limit is above the recommendation. Does not change
    current mileage or retire the shoe.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
        limit_km: New limit in km (> 0), or omit to reset to the type default.
    """
    try:
        with _core.get_session() as db:
            shoe = rotation.set_mileage_limit(db, owned_shoe_id, limit_km)
            return {
                "success": True,
                "shoe": f"{shoe.brand} {shoe.model}",
                "mileage_limit": shoe.mileage_limit,
                "recommended_limit_km": default_mileage_limit(shoe.shoe_type),
                "current_mileage": round(shoe.current_mileage, 2),
            }
    except (LookupError, ValueError) as exc:
        return {"success": False, "error": str(exc)}


@mcp.tool()
def retire_shoe(owned_shoe_id: int) -> dict:
    """
    Mark an owned shoe as retired (status="retired"). Use this when a shoe
    has hit its mileage limit or is otherwise done being used for running.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
    """
    try:
        with _core.get_session() as db:
            shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
            if not shoe:
                return {"success": False, "error": f"Owned shoe with id {owned_shoe_id} not found"}

            shoe.status = "retired"
            db.commit()
            db.refresh(shoe)

            note_count = db.query(ShoeNote).filter(ShoeNote.owned_shoe_id == owned_shoe_id).count()
            result: dict = {
                "success": True,
                "shoe": f"{shoe.brand} {shoe.model}",
                "final_mileage": round(shoe.current_mileage, 2),
            }
            # Nudge the review workflow when the shoe has logged notes — now is
            # when the runner's experience is freshest (R3.3).
            if note_count > 0:
                result["review_prompt"] = (
                    f"This shoe has {note_count} journal note(s). "
                    f"Run draft_shoe_review({owned_shoe_id}) to write a review "
                    "while the experience is fresh."
                )
            return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Static resources
# ---------------------------------------------------------------------------

@mcp.resource(
    "shoes://rotation",
    name="My Shoe Rotation",
    description="Current owned shoe rotation with mileage, status and lifetime stats for all active shoes",
    mime_type="application/json",
)
def shoe_rotation_resource() -> str:
    """Current owned shoe rotation with mileage and lifetime stats"""
    import json

    with _core.get_session() as db:
        shoes = db.query(OwnedShoe).order_by(OwnedShoe.created_at.desc()).all()
        active = [s for s in shoes if s.status == "active"]
        retired = [s for s in shoes if s.status != "active"]

        # One bulk attach feeds both the JSON block and the markdown stats below
        # (sets s.lifetime_avg_pace / lifetime_avg_hr / total_runs on each instance).
        shoe_dicts = _owned_shoes_payload(db, active + retired)

        md_lines = ["# My Shoe Rotation", "", "**Active Shoes**"]
        for s in active:
            bar = _format_mileage_bar(s.current_mileage, s.mileage_limit)
            label = s.nickname or ""
            name = f"{s.brand} {s.model}" + (f" ({label})" if label else "")
            pace = s.lifetime_avg_pace or "—"
            hr = f"{s.lifetime_avg_hr}bpm" if s.lifetime_avg_hr else "—"
            runs = s.total_runs
            type_tag = f" [{s.shoe_type}]" if s.shoe_type else ""
            md_lines.append(f"- {name}{type_tag} — {round(s.current_mileage)}km  {bar}")
            md_lines.append(f"  Avg pace: {pace} · Avg HR: {hr} · {runs} runs")

        if not active:
            md_lines.append("_(none)_")

        if retired:
            md_lines += ["", "**Retired Shoes**"]
            for s in retired:
                label = s.nickname or ""
                name = f"{s.brand} {s.model}" + (f" ({label})" if label else "")
                md_lines.append(f"- {name} — {round(s.current_mileage)}km (retired)")

        markdown = "\n".join(md_lines)
        payload = json.dumps({"shoes": shoe_dicts}, default=str)
        return f"{markdown}\n\n```json\n{payload}\n```"


# ---------------------------------------------------------------------------
# Templated resources
# ---------------------------------------------------------------------------

@mcp.resource(
    "shoes://owned/{shoe_id}",
    name="Shoe Detail",
    description="Full detail for a specific owned shoe including stats, recent runs and notes",
    mime_type="application/json",
)
def shoe_detail_resource(shoe_id: int) -> str:
    """Full detail for a specific owned shoe"""
    import json

    with _core.get_session() as db:
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == shoe_id).first()
        if not shoe:
            return f"No shoe found with id {shoe_id}"

        stats = rotation.compute_lifetime_stats(db, shoe.id)
        cost_per_km = rotation.cost_per_km(shoe)
        mileage_limit = shoe.mileage_limit
        label = shoe.nickname or ""
        name = f"{shoe.brand} {shoe.model}" + (f" ({label})" if label else "")
        pct = round(shoe.current_mileage / mileage_limit * 100) if mileage_limit else None
        mileage_line = f"{round(shoe.current_mileage)}km / {round(mileage_limit)}km ({pct}%)" if mileage_limit else f"{round(shoe.current_mileage)}km"

        type_line = f" | **Type:** {shoe.shoe_type}" if shoe.shoe_type else ""
        md_lines = [
            f"# {name}",
            f"**Status:** {shoe.status.capitalize()} | **Mileage:** {mileage_line}{type_line}",
        ]
        if shoe.purchase_price:
            md_lines.append(
                f"**Purchase price:** ${shoe.purchase_price:.2f}"
                + (f" | **Cost per km:** ${cost_per_km:.2f}" if cost_per_km else "")
            )
        pace = stats.lifetime_avg_pace or "—"
        hr = f"{stats.lifetime_avg_hr}bpm" if stats.lifetime_avg_hr else "—"
        runs_count = stats.total_runs
        md_lines.append(f"**Lifetime stats:** Avg {pace} · {hr} · {runs_count} runs")

        recent_runs = (
            db.query(ShoeRun)
            .join(Activity, ShoeRun.activity_id == Activity.id)
            .options(contains_eager(ShoeRun.activity))
            .filter(ShoeRun.owned_shoe_id == shoe_id)
            .order_by(desc(Activity.run_date), desc(ShoeRun.created_at))
            .limit(5)
            .all()
        )
        if recent_runs:
            md_lines += ["", "## Recent Runs"]
            for r in recent_runs:
                a = r.activity
                date_str = a.run_date.strftime("%b %d") if a.run_date else "—"
                p = rotation.seconds_to_pace(a.avg_pace_s_per_km) if a.avg_pace_s_per_km else "—"
                h = f"{a.avg_hr}bpm" if a.avg_hr else "—"
                md_lines.append(f"- {date_str} · {a.distance_km:.1f}km · {p} · {h}")

        recent_notes = (
            db.query(ShoeNote)
            .filter(ShoeNote.owned_shoe_id == shoe_id)
            .order_by(desc(ShoeNote.created_at))
            .limit(3)
            .all()
        )
        if recent_notes:
            md_lines += ["", "## Notes"]
            for n in recent_notes:
                km_tag = f"[{round(n.mileage_at_note)}km]" if n.mileage_at_note else ""
                md_lines.append(f"- {km_tag} {n.body}")

        markdown = "\n".join(md_lines)
        payload = json.dumps(
            {
                "shoe": _owned_shoe_payload(db, shoe),
                "recent_runs": [_shoe_run_payload(r) for r in recent_runs],
                "recent_notes": [_shoe_note_payload(n) for n in recent_notes],
            },
            default=str,
        )
        return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "shoes://owned/{shoe_id}/runs",
    name="Shoe Run History",
    description="Complete run history for a specific owned shoe",
    mime_type="application/json",
)
def shoe_runs_resource(shoe_id: int) -> str:
    """Complete run history for a specific owned shoe, newest first"""
    import json

    with _core.get_session() as db:
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == shoe_id).first()
        if not shoe:
            return f"No shoe found with id {shoe_id}"

        runs = (
            db.query(ShoeRun)
            .join(Activity, ShoeRun.activity_id == Activity.id)
            .options(contains_eager(ShoeRun.activity))
            .filter(ShoeRun.owned_shoe_id == shoe_id)
            .order_by(desc(Activity.run_date), desc(ShoeRun.created_at))
            .all()
        )
        label = shoe.nickname or ""
        name = f"{shoe.brand} {shoe.model}" + (f" ({label})" if label else "")

        md_lines = [
            f"# Run History — {name}",
            f"_{len(runs)} run{'s' if len(runs) != 1 else ''} logged_",
            "",
            "| Date | Distance | Pace | HR | Source |",
            "|------|----------|------|----|--------|",
        ]
        for r in runs:
            a = r.activity
            date_str = a.run_date.strftime("%b %d, %Y") if a.run_date else "—"
            pace = rotation.seconds_to_pace(a.avg_pace_s_per_km) if a.avg_pace_s_per_km else "—"
            hr = f"{a.avg_hr}bpm" if a.avg_hr else "—"
            source_badge = _SOURCE_BADGES.get(a.source, "✍ manual")
            md_lines.append(f"| {date_str} | {a.distance_km:.1f}km | {pace} | {hr} | {source_badge} |")

        stats = rotation.compute_lifetime_stats(db, shoe_id)
        markdown = "\n".join(md_lines)
        payload = json.dumps(
            {
                "shoe_id": shoe_id,
                "runs": [_shoe_run_payload(r) for r in runs],
                "lifetime_avg_pace": stats.lifetime_avg_pace,
                "lifetime_avg_hr": stats.lifetime_avg_hr,
                "total_runs": stats.total_runs,
            },
            default=str,
        )
        return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "shoes://owned/{shoe_id}/notes",
    name="Shoe Notes Journal",
    description="Timestamped notes journal for a specific owned shoe",
    mime_type="application/json",
)
def shoe_notes_resource(shoe_id: int) -> str:
    """Timestamped notes journal for a specific owned shoe"""
    import json

    with _core.get_session() as db:
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == shoe_id).first()
        if not shoe:
            return f"No shoe found with id {shoe_id}"

        notes = (
            db.query(ShoeNote)
            .filter(ShoeNote.owned_shoe_id == shoe_id)
            .order_by(desc(ShoeNote.created_at))
            .all()
        )
        label = shoe.nickname or ""
        name = f"{shoe.brand} {shoe.model}" + (f" ({label})" if label else "")

        md_lines = [f"# Notes — {name}", ""]
        if not notes:
            md_lines.append("_No notes yet._")
        for n in notes:
            date_str = n.created_at.strftime("%b %d, %Y") if n.created_at else "—"
            km_str = f"{round(n.mileage_at_note)}km" if n.mileage_at_note is not None else ""
            badge = "🏁 checkpoint" if n.triggered_by == "checkpoint" else "✍ manual"
            md_lines.append(f"[{date_str} · {km_str}] {badge}")
            md_lines.append(n.body)
            md_lines.append("")

        markdown = "\n".join(md_lines).rstrip()
        payload = json.dumps({"shoe_id": shoe_id, "notes": [_shoe_note_payload(n) for n in notes]}, default=str)
        return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "shoes://review/{shoe_id}",
    name="Shoe Review",
    description="Stored review draft for a specific owned shoe (R3.3)",
    mime_type="text/plain",
)
def shoe_review_resource(shoe_id: int) -> str:
    """
    Return the stored review draft for an owned shoe, or a prompt to start
    the review workflow if none exists yet.

    Readable from Claude Desktop to retrieve the draft without re-running the
    LLM call. The draft is written by draft_shoe_review (auto-save) and
    overwritten by save_shoe_review (runner-edited).
    """
    with _core.get_session() as db:
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == shoe_id).first()
        if not shoe:
            return f"No shoe found with id {shoe_id}"

        label = shoe.nickname or ""
        name = f"{shoe.brand} {shoe.model}" + (f" ({label})" if label else "")

        if not shoe.review_draft:
            note_count = db.query(ShoeNote).filter(ShoeNote.owned_shoe_id == shoe_id).count()
            note_hint = (
                f" It has {note_count} journal note(s) to draw from."
                if note_count > 0 else " Add some notes first via add_shoe_note."
            )
            return (
                f"# Review — {name}\n\n"
                f"_No review stored yet._{note_hint}\n\n"
                f"Run `draft_shoe_review({shoe_id})` to generate a draft from the notes journal."
            )

        return f"# Review — {name}\n\n{shoe.review_draft}"


@mcp.prompt()
def weekly_rotation_summary() -> str:
    """
    Generate the runner's weekly rotation digest — volume vs last week,
    per-shoe usage, retirement pipeline, notable runs, 100km checkpoints,
    and next-race countdown. Read-only; no confirmation or writes needed.
    Typically run on Mondays to review the previous week.
    """
    return """# Weekly Rotation Summary

You are composing the runner's weekly training and rotation digest.
This is READ-ONLY — no writes, no confirmation gates.

## Step 1 — Fetch the weekly snapshot
Call `get_weekly_summary()`. It returns a single structured object covering
the current ISO week (Monday through Sunday): volume, per-shoe usage,
retirement pipeline, notable runs, 100km checkpoints, and next race.

## Step 2 — Compose and present the digest
Use this exact structure. Omit any section whose data list is empty.

---
**Week of [week_start] – [week_end]**

**Volume:** [this_week_km] km
[If last_week_km > 0: "(↑ [delta_km] km vs [last_week_km] km last week)" if delta_km > 0,
 else "(↓ [|delta_km|] km vs [last_week_km] km last week)" if delta_km < 0,
 else "(= same as last week's [last_week_km] km)"]
[If last_week_km == 0 and this_week_km > 0: "(no runs last week)"]

**Shoes used this week:**
[For each entry in per_shoe_usage, most-used first:]
- [Brand] [Model][" (nickname)" if nickname] — [km_this_week] km · [run_count] run(s)[" · " + shoe_type if shoe_type]

**Retirement pipeline — [count] shoe(s) at ≥ 75% of limit:**
[For each entry in pipeline, worst-first:]
- [Brand] [Model][" (nickname)" if nickname] — [current_mileage] km / [mileage_limit] km ([pct×100 rounded to 0dp]%)[" · " + replacement_deals + " replacement deal(s) available" if replacement_deals > 0]

**Notable runs:**
[For each entry in notable_runs, newest-first:]
- [run_date] · [activity_tag] · [distance_km] km @ [avg_pace or —][ · avg_hr bpm if avg_hr set][ · shoe label if shoe set][ · name if name set]

**Checkpoints this week:**
[For each entry in checkpoints_this_week:]
- [Brand] [Model] crossed [checkpoint_km] km ([triggered_at])

**Next race:** [If next_race:
[name] — [race_date] ([days_remaining] day(s) / [weeks_remaining] week(s) away)[", target " + target_pace if target_pace]
Else: "No upcoming races scheduled."]
---

## Rules
- Never invent data not present in get_weekly_summary's response
- If per_shoe_usage is empty: state "No attributed runs this week"
- Pipeline pct display: multiply by 100 and round to the nearest whole number
  (e.g. 0.8234 → 82%) — never show raw fractions
- delta_km direction: positive means more volume this week (↑), negative means less (↓)
- Keep the tone informative and direct; no cheerleading ("Great job!" etc.)
- Do not add observations not grounded in the data (no invented training advice)
"""


@mcp.tool()
def get_shoe_insights(owned_shoe_id: int) -> dict:
    """
    Longitudinal analytics for one owned shoe: how it performs and how it wears.
    Use for "how does this shoe run compared to others", "how worn is it", or
    "when do shoes like this usually get retired".

    Returns `performance` (this pair), `model` (the same numbers pooled across
    every pair of this shoe model), `wear` (weekly km and cumulative km since
    purchase, plus current mileage, limit and pct_of_limit) and `type_wear`
    (where retired shoes of this type actually ended; null if none retired).

    Performance is a comparison of STEADY runs only (untagged or Easy / Long
    Run, 5 km+, with heart rate, no long stops): median metres per heartbeat,
    pace (s/km) and avg HR. It is a heuristic. Pace by shoe mostly reflects what
    the shoe was used for, so ALWAYS state the run counts (`runs`, `steady_runs`)
    and the `caveat` when answering, and do not call a shoe faster or better
    from small gaps. A null median means not enough data (`enough_data` false:
    fewer than `min_steady_runs` steady runs) — say so rather than guessing.
    `suggested_limit_km` in type_wear is advisory only; changing a limit is a
    separate step via set_shoe_mileage_limit that the runner must confirm.
    Read-only.

    Args:
        owned_shoe_id: id of the owned shoe (see get_owned_shoes).
    """
    from dataclasses import asdict
    from app.models.schemas.insights import ShoeInsightsResponse
    from app.services import insights
    with _core.get_session() as db:
        try:
            return ShoeInsightsResponse(**asdict(insights.shoe_insights(db, owned_shoe_id))).model_dump()
        except LookupError as e:
            return {"error": str(e)}


@mcp.tool()
def get_rotation_insights() -> dict:
    """
    Rotation-wide analytics: `models` compares shoe models by their steady-run
    medians (metres per heartbeat, pace s/km, avg HR) pooled across pairs, and
    `wear_by_type` shows the mileage at which retired shoes of each type ended,
    against the default limit, with an advisory `suggested_limit_km`.

    Steady runs only (untagged or Easy / Long Run, 5 km+, with heart rate, no
    long stops); a heuristic. Pace by shoe mostly reflects what the shoe was
    used for, so ALWAYS give the run counts (`runs`, `steady_runs`) and the
    `caveat` when answering. A null median means not enough data
    (`enough_data` false) — say so. The suggested limit is advisory: never
    apply it without the runner's confirmation (set_shoe_mileage_limit).
    Read-only.
    """
    from dataclasses import asdict
    from app.models.schemas.insights import RotationInsightsResponse
    from app.services import insights
    with _core.get_session() as db:
        return RotationInsightsResponse(**asdict(insights.rotation_insights(db))).model_dump()
