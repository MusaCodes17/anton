# Skill S11 — background-job

## Purpose
Long-running or concurrent work under the single-process reality: locks, per-thread sessions,
SSE progress.

## When to use
Anything taking more than a few seconds; anything concurrent; roadmap R4.1 groundwork.

## Required context
- `docs/architecture.md` §4 (background scrape lifecycle) and §15.2 (the one-worker assumption).
- `docs/design_decisions.md` D4 (one lock, refuse-don't-queue), D5 (threads + SSE replay),
  E5 (APScheduler: declared, unused, undecided).
- Exemplars: `scrapers/scrape_runner.py` + `scrape_state.py`.

## Workflow
1. Decide sync-guarded vs background: `scrape_guard()` returning 409, or `BackgroundTasks`.
2. Acquire the relevant lock **non-blocking**; **the job, not the handler, releases it in
   `finally`** — the job outlives the handler.
3. One DB session per worker thread; never share sessions across threads (CLAUDE.md §9).
4. Publish progress events to a state manager with **replay-on-subscribe** if a UI watches
   (a refreshed browser must not lose the picture).
5. **Refuse concurrency rather than queue** — the documented posture (D4); queued work hides cost.
6. User-visible progress is part of the feature, not optional telemetry (CLAUDE.md §8).

## Common mistakes
- The handler releasing the lock.
- Sharing a session across threads.
- Adding a scheduler/worker without reading E5 + roadmap R4.1 — the in-memory lock is
  silently invalid under multi-process; **exactly one uvicorn worker is a hard operational
  invariant** today.
- Queuing hidden work instead of refusing visibly.
- SSE without replay.

## Checklist
- [ ] Lock ownership correct (release in job `finally`)
- [ ] Per-thread sessions
- [ ] Progress observable and replayable
- [ ] Refuses rather than stacks
- [ ] Single-process assumption unviolated (or the design doc for changing it exists)
- [ ] Wrap up per S13
