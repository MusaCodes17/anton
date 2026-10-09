# Spike — automatic fitness snapshots (R8.4.1)

**Date:** 2026-10-09 · **Verdict: GO** · No product code; the fixture is the only artifact.

## Question

Can the backend's own COROS MCP client (C11) read VO₂ max, running level, threshold pace and race predictions, so the poller can record a fitness snapshot without the manual `sync_fitness` prompt? Without that, R8.4.3 has no VO₂ max / threshold history to chart: `athlete_metrics` holds one row (2026-07-09).

## Findings

1. **The tool exists and the backend can reach it.**
   - Tool: `queryFitnessAssessmentOverview`.
   - It is in the backend's own captured tool list (`scripts/spikes/fixtures/tools_list.json`): no arguments, `readOnlyHint: true`.
   - A live call through `CorosMcpClient._request` with the backend's OAuth token returned the same text as the claude.ai connector.
2. **The response is prose, like the other COROS tools.** The text is a JSON string literal, so `_unwrap_text` applies:

   ```
   Fitness Assessment Overview
   ========================

   VO2max: 59
   Running Level: 97
   Threshold Pace: 3:24 /km
   5 km Prediction: 16:17
   10 km Prediction: 33:27
   Half Marathon Prediction: 1:12:29
   Marathon Prediction: 2:27:44
   ```

   Pinned as `backend/tests/fixtures/coros/fitness_overview.json`, the raw JSON-RPC body.
3. **Every field maps onto `athlete_metrics` with no schema change.**

   | COROS line | Column | Value stored |
   |---|---|---|
   | `VO2max` | `vo2max` | float |
   | `Running Level` | `running_level` | float |
   | `Threshold Pace` | `threshold_pace_s_per_km` | via `_pace_s` |
   | the four `Prediction` lines | `race_predictions` | `{"5.0", "10.0", "21.0975", "42.195"}` → seconds |

   The prediction keys are the ones the July snapshot and `PredictionsCard` already use.
4. **COROS returns only the current values, with no history and no date argument.** History therefore starts the day the poller begins recording. The July row is the only earlier point.
5. **COROS reports whole numbers.**
   - VO₂ max and running level come back as integers (59, 97); the July snapshot stored 61.0 / 97.0.
   - Small changes therefore show up as 1-point steps. Charts should use a step line, not imply decimals.

The values have moved since July:

| Metric | 2026-07-09 | 2026-10-09 |
|---|---|---|
| VO₂ max | 61 | 59 |
| Threshold pace | 3:22 /km | 3:24 /km |
| Marathon prediction | 2:26:29 | 2:27:44 |

That is already a trend worth showing.

## Build notes for R8.4.1

- **Parser:** add `parse_fitness_overview(text)` to `coros_mcp_client` with anchored regexes per line.
  - A missing line is `None`, since COROS omits metrics it can't assess yet.
  - A reworded or garbled present line raises `CorosContractError` (CLAUDE.md §6 trap).
  - Add `CorosMcpClient.fitness_overview()`.
- **Poller:** after a clean poll, at most once per Toronto calendar day:
  - Fetch the overview.
  - Append a snapshot via `fitness.record_snapshot` only when it differs from `fitness.latest`.
  - A failure is logged and never fails the poll, same as `_scan_best_efforts`.
- **Gate:** a fitness snapshot is an athlete reading COROS computed, not a run.
  - INV-8 (run confirmation) does not apply, and the ledger is untouched.
  - Record this as a design decision, and fix the stale `services/fitness.py` docstring that says snapshots only arrive from the Claude-Desktop agent (C6 was superseded by C11).
- **Manual path:** the `record_athlete_metrics` MCP tool / `sync_fitness` prompt stay as the manual path.
