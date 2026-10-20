# Spike R11.6 — Fast finish in long runs

*2026-10-20. Analysis only; no product code. Script: `backend/scripts/spikes/r11_6_fast_finish.py --db <copy of shoe_deals.db>` (read-only).*

## Question
In a marathon block's long runs, did the runner hold or lift pace late — and can `activity_best_efforts` (R8.2) say so? That table keeps one fastest segment per distance per activity plus `start_offset_m`. It cannot say "the last 10 km".

## What data exists
- **No splits, laps or streams anywhere in the DB.** `activities.raw_json` holds only the Strava CSV export columns (Elapsed Time, Distance, Average Speed, Max Speed, Max Cadence, Average Heart Rate, …) for 929 archive rows: run-level aggregates, no per-km data. `best_km_pace_s` is null on every row (0 of 1,020). There is no splits table.
- `activity_best_efforts`: 1k, mile, 5k, 10k, half (90) and full (3) per scanned activity. One row per (activity, distance) — the single fastest window, with its start offset. Scan status: 745 ok, 13 failed.
- Segment pace below = `elapsed_s` of the segment / km (timer time). Run average = `moving_time_s` / km. They are not the same clock (see failure mode 4).

## Blocks used
Marathons found: TCS Toronto 2025-10-19 and Ottawa 2026-05-24 (both Race-tagged activities with no plan row, so **no target**), and Beneva 2026-10-11 (plan row, target 3:00:00 = 4:16/km). Block = 16 Monday-aligned weeks to the day before the race; long run = running activity of at least 28 km.

**3 blocks, 17 long runs, 15 with segments** (Toronto 6/6, Ottawa 6/6, Beneva 3/5: one scan `failed`, one never scanned).

## Per-run table
`off%` = start of the best segment as % of the run; `end%` = its end. `vs avg` = segment pace minus run average (negative = faster). `vs tgt` only where a target exists.

| Date | km | Avg | Best 5k: off–end% | pace | vs avg | Best 10k: off–end% | pace | vs avg |
|---|---|---|---|---|---|---|---|---|
| **Toronto** | | | | | | | | |
| 2025-07-06 | 33.0 | 4:54 | 9–24 | 4:40 | -13s | 3–33 | 4:43 | -10s |
| 2025-07-16 | 29.0 | 4:18 | 59–77 | 3:47 | -31s | 45–79 | 4:20 | +2s |
| 2025-07-20 | 42.3 | 4:49 | 38–50 | 4:30 | -19s | 3–27 | 4:46 | -2s |
| 2025-08-30 | 30.1 | 4:35 | 7–23 | 4:38 | +3s | 10–43 | 5:12 | +37s |
| 2025-09-13 | 31.1 | 4:45 | 46–63 | 4:35 | -9s | 33–65 | 4:58 | +13s |
| 2025-09-28 | 32.0 | 4:14 | 31–47 | 3:46 | -29s | 69–100 | 4:14 | -1s |
| **Ottawa** | | | | | | | | |
| 2026-02-15 | 30.0 | 4:17 | 0–17 | 4:06 | -11s | 0–33 | 4:12 | -5s |
| 2026-02-22 | 30.0 | 4:01 | 18–35 | 3:56 | -5s | 14–47 | 4:00 | -2s |
| 2026-03-01 | 30.0 | 3:58 | 7–23 | 3:50 | -8s | 7–40 | 3:53 | -5s |
| 2026-03-15 | 34.0 | 4:35 | 72–86 | 4:21 | -13s | 65–95 | 4:23 | -11s |
| 2026-05-03 | 30.0 | 4:17 | 58–75 | 3:47 | -30s | 42–75 | 4:01 | -16s |
| 2026-05-10 | 30.2 | 4:16 | 73–89 | 3:38 | -37s | 56–89 | 3:47 | -29s |
| **Beneva** (target 4:16) | | | | | | | | |
| 2026-07-12 | 31.0 | 4:23 | no segments (scan failed) | | | | | |
| 2026-07-19 | 30.0 | 4:12 | 22–39 | 4:10 | -2s | 6–39 | 4:17 | +4s |
| 2026-08-02 | 30.0 | 3:53 | no segments (never scanned) | | | | | |
| 2026-09-27 | 30.0 | 4:14 | 15–31 | 4:09 | -5s | 2–36 | 4:34 | +20s |
| 2026-09-30 | 30.0 | 5:26 | 56–73 | 5:07 | -19s | 39–72 | 5:13 | -13s |

Beneva 5k vs target pace: -6s, -7s, +51s (09-30); 10k: +1s, +18s, +57s. Toronto and Ottawa have no target, so there is no pace-vs-target for 12 of the 15 runs.

## Does "best segment in the final third and faster than average" read honestly?
**No.** Where it fires it is mostly right but it cannot distinguish the cases a runner cares about, and where it stays silent it hides what happened.

1. **Fade is hidden.** A fastest segment early (2026-02-15: best 5k at 0–17%, 10k at 0–33%; 2026-03-01; 2025-07-06) is consistent with going out hard and fading *and* with a steady run whose opening was a touch quicker. The table holds identical rows for both. The data cannot show the fade; "no late fast segment" reads as "no fast finish" when it may be "faded" or "even".
2. **A late fast segment is not a fast finish.** 2025-07-16 (5k at 59–77%, 3:47, 31s under average, but the best 10k is 4:20, +2s) is a fast 5k piece inside a run, not a lift to the end. 2025-09-28 has a 3:46 5k at 31–47% and a 10k at 4:14 ending at 100%: a workout in the middle, with the finish only equal to average. Nothing says whether the last km was fast or dead.
3. **The last km is invisible.** For 2026-05-10 (5k 73–89%, 3:38) the segment ends 11% (about 3.3 km) before the finish. Whether the run closed at that pace or fell off is unknowable. A late fast segment says nothing about the final stretch, which is the thing the roadmap asks about.
4. **Clock mismatch.** 2025-08-30 shows a 10k "+37s slower than average" because the run had a 2,242 s stopped gap (moving 8,269 s vs elapsed 10,511 s) and the segment uses timer time. Comparing it with a moving-time average is not a like-for-like difference. The same applies to every run with stops (e.g. 2025-09-13: 12,797 s elapsed vs 8,842 s moving).
5. **Workouts and long runs are the same row.** Three runs show a clear fast piece (2026-05-03 and 2026-05-10 are labelled progressive/long; 2025-07-16, 2025-09-28 look like embedded tempo). The data does not mark which were intended finishes.
6. **Coverage.** Beneva has 3 of 5 runs with segments, and its race itself is not usable: the linked activity (id 1024, 2026-10-11) is a 14.02 km, 3,059 s recording, so the planned race's `result_time_s` of 3,059 does not describe a marathon. That is a data question for the runner and says nothing about R11.6, but it means the newest block cannot be compared with its own race.

The rule fires on 5 of 15 runs (best 5k ending at or past the final third, faster than average): 2025-07-16, 2026-03-15, 2026-05-03, 2026-05-10, 2026-09-30. Reading all five as "fast finish" would be wrong for at least 2025-07-16 and 2026-09-30 (a 5:26 average run that was 51s off target pace even in its best 5k).

## Verdict
**Does not read honestly.** The question "do I hold or lift pace late" needs the per-km (or per-lap) profile of each long run; one fastest segment cannot show a fade or a last-km collapse, and its offset reveals only where the quickest piece was.

**This is the named question that reopens R5.4.3 (splits).** Move R5.4.3 out of Parked & gated and scope it from this finding; do not ship an approximation under `fast_finish`.

## What splits data is needed
- Per activity, per-km split times (distance and timer or moving time per km, plus the last partial km), for runs of at least 20 km at minimum. Per-km is enough; laps and HR can come later.
- Stored derived data in the same family as best efforts (B19-style exception: the FIT/GPX files are not in the DB), cascade-deleted with the run, rebuilt by re-scanning. The existing effort scan already reads the FIT/GPX record stream, so extracting per-km splits there is the natural place and costs no extra COROS download for runs already scanned. Strava-archive runs depend on the export's FIT files being available.
- A consistent clock: moving time for both the run average and the splits.
- Then the honest rules become simple to state: pace of the last 10 km minus pace of the first 10 km (a "negative split" figure), and the final km against the run average, each shown beside the run with no pass/fail threshold.

## Left for the runner to decide
1. Reopen R5.4.3 now (recommended by this spike) or park R11.6 until after R11.7.
2. Beneva race record: activity 1024 (14 km) is linked to the marathon; either the race was cut short (should it be DNF?) or the link is wrong.
3. Two Beneva long runs are not scanned (one failed, one never); rescanning would not change the verdict.
