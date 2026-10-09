# Spike — best efforts inside longer runs (R8.2 S1)

**Run:** 2026-10-09 · script `scripts/spikes/best_efforts.py` (throwaway; `fitdecode` + `gpxpy` in a scratch venv, nothing added to `requirements.txt`) · data: the Strava bulk export (`~/Workspace/export_33354574/activities/`) and one live COROS FIT URL. No product code, no DB writes.
**Verdict: GO.** The per-second data exists for the whole archive and for new COROS runs, parses cleanly on the image's Python, and gives sensible efforts. There are four decisions for the runner before building; see the last section.

## The three questions

| # | Question | Answer |
|---|---|---|
| 1 | Can the backend get FIT files for COROS runs? | **Yes.** The COROS MCP server's `queryActivityFitFileDownloadUrls` with `labelId` + `sportType` returns a plain URL (`https://s3.coros.com/fit/<userId>/<labelId>.fit`). A `HEAD` returned `200`, `application/octet-stream`, 134 KB, with **no signature, auth or expiry** — plain `requests.get` works. `PendingCorosRun.label_id` (and `Activity.coros_activity_id`) already hold the id. Wiring: one more `_call_tool` in `coros_mcp_client` plus an anchored URL regex with a fixture (the C11 contract style). Caveats: each URL counts against a **daily FIT limit** of unknown size; a date-range query (no `labelId`) came back with a garbled error once, while the `labelId` form worked. **Verified end to end** (runner-approved download of one file to scratch, deleted after): the Oct 6 run parsed to 3,161 one-second samples, 12.53 km, 52:40 elapsed (COROS lists it at 52:39). |
| 2 | Does the Strava export cover the archive? | **Yes, fully.** All 929 `source='strava'` activities have `fit_filename`, and every file exists: 896 `.fit.gz` + 33 `.gpx`. Of the 710 `Run` activities, 694 have a file and all 694 yield a stream with **1-second samples** (median gap 1 s). The 6 files with no distance stream are non-runs. |
| 3 | Parser inside the A7 pins / Docker image? | **Yes.** `fitdecode` 0.11 (MIT) and `gpxpy` 1.6 (Apache-2.0) are pure Python with **zero dependencies**, so the FastAPI/Starlette/mcp pin triangle is untouched; the image is `python:3.11-slim-bookworm`. `fitdecode` emits harmless "invalid field size" warnings on some files; silence them. |

## Measurements (all 929 files, laptop)

- **Speed:** 525 s total, about 0.6 s per file (a marathon about 2.5 s). Backfilling the 694 runs takes roughly 6–7 minutes, once.
- **Reliability:** 0 parse errors.
- **Distance agreement:** 24 of 694 runs differ by more than 3% between the stream and the stored distance.
  - FIT records the watch's own cumulative distance, so it matches the stored distance by construction.
  - GPX has no distance field; summing GPS points runs long (one 8.53 km run summed to 11.29 km).
- **Plausibility:** with no filtering, 29 files produce an effort faster than 2:40/km. 28 of those are **rides/hikes** in the export, which records never read (they filter `activity_type = 'Run'`). Among runs, **1** is bad: a GPX file with a 150 s gap and a GPS jump that gives a "1k in 0:02".

**Validation against known results** (segment best vs the stored whole-activity time):

| Run | Stored (elapsed) | Segment best efforts found |
|---|---|---|
| Ottawa Marathon 2026-05-24 (42.66 km) | 2:43:38 | full **2:41:40** · half 1:19:16 · 10k 37:22 · 5k 18:37 |
| 21k de Montreal 2026-04-19 (21.35 km) | 1:17:11 | half **1:16:16** · 10k 35:40 · 5k 17:42 |
| Taper Week Longueuil 10K 2026-05-17 (10.09 km) | 34:55 | 10k **34:28** · 5k 16:58 · 1k 3:19 |

The watch measures courses a little long (42.66 vs 42.195), so the segment best is the honest time for the standard distance, as Strava's "best efforts" show.

**Archive-wide top efforts (runs only, the bad GPX dropped):**

| Distance | Best | From |
|---|---|---|
| 5k | 15:39 | 5K Time Trial 2025-09-26 (whole-activity record: 15:47) |
| 10k | 34:28 | inside Taper Week Longueuil 10K |
| Half | 1:16:16 | inside 21k de Montreal |
| Full | 2:41:40 | inside Ottawa Marathon |
| 1k | 2:52 | an untagged track session (a rep) |

## What the build should look like (refines roadmap §R8.2)

- **Pure function in `app/utils/`:** the two-pointer sliding window over `(elapsed_s, distance_m)`, interpolating the end point to the exact target distance. Test it with hand-built streams plus one known race (Longueuil: 10k 34:28, 5k 16:58).
- **GPS sanity before the window:**
  - drop samples whose step speed exceeds ~8 m/s (2:05/km), which kills jumps like the bad GPX;
  - prefer FIT device distance; use GPX only when there is no FIT;
  - keep an "exclude from records" escape hatch for anything that slips through.
- **Storage:** the additive `activity_best_efforts` table from §R8.2, one row per (activity, distance), `source = fit|gpx`. Derived data, rebuildable by re-running the backfill.
- **Backfill runs where the files are.** The export lives on the laptop and the DB on Hetzner. Options:
  - copy the 72 MB `activities/` folder to the server and run the script there (simplest); or
  - compute locally and import a JSON of efforts keyed by `strava_activity_id`.
- **New COROS runs:** after a confirm lands (the poller stays a non-writer, INV-1/INV-8), fetch the FIT by `label_id` and compute the efforts. A failure only means "no efforts yet" and never blocks the confirm. One backfill pass covers the ~16 COROS runs already in the DB.

## Decisions for the runner

1. **Do interval/track sessions count for segment best efforts?** R8.1 excludes them from *whole-activity* records because rests used to hide inside the time. A segment is continuous running on the elapsed clock, so a 1k rep *is* a real 1k effort, and Strava counts them. Recommendation: count them for segments; keep them out of Race PBs (already the case).
2. **Which distances?** Today: 5k / 10k / half / full. Strava also shows 400 m, 1k, mile and 2 mile. Recommendation: add **1k and mile**, since the track data is there.
3. **Where segments show:** the Best efforts list switches to segments, with the parent run named ("5k inside Taper Week Longueuil 10K"); Race PBs stay whole race results. Recommended, and it matches roadmap §R8.2.
4. **The COROS FIT URL is public.** Anyone with the URL can download that run, GPS track included. The backend should fetch and parse each file, keep only the numbers, and never store or log the URL.

## Runner's decisions (2026-10-09)

1. **Intervals/Track count** for segment best efforts. They stay out of Race PBs.
2. **Distances:** 1k, mile, 5k, 10k, half, full.
3. **Segments replace the Best efforts list**, naming the parent run. Race PBs stay whole race results.
4. **COROS FIT verified** (see question 1). The URL is handled as recommended: parse in memory, keep only the numbers, never store or log it.
