# Spike R11.7 — Finish-time range + evidence grade (backtest first)

*2026-10-20. Analysis only; no product code. Script: `backend/scripts/spikes/r11_7_backtest.py --db <copy of shoe_deals.db at head>` (read-only: SQLite `mode=ro`, `races_svc.race_entries` + `strava_stats.personal_bests` only).*

## Question
Could Anton show an honest finish-time range for the next race? Each estimator below uses only runs dated on or before the day before the race, built the way `race_readiness` builds its recent window (8 weeks = `RECENT_EFFORT_WEEKS`; 12 weeks as a check).

## The sample (n = 6)
- **Scored: 6** — 2 marathons (TCS Toronto 2025-10-19, Ottawa 2026-05-24) and 4 halves (a 2024-08-20 "random Tuesday" half, Two Oceans 2025-04-06, a Practice HM 2025-05-25, Spring Half 2026-04-19).
- **Excluded, not scored:**
  - Beneva Marathon 2026-10-11: linked run is 14.02 km, result 0:50:59 — not a marathon time (the R11.6 finding stands; also not a DNF in the data).
  - Four Race-tagged 17–18 km rows, in the half class by distance but not half distances: Osaka 2025-09-17 (17.0 km), HCMC 2025-09-01 (18.1), 2025-08-13 (18.0), Comrades pacing 2025-06-08 (17.5).
  - **DNF races:** none carry status `dnf` in this copy (Beneva is still `completed` here, pending the R10.3 mark); the script would exclude any.
  - Six Race-tagged runs under 15 km (10k-class and shorter) are out of scope.
- Flag: the 2024 "random Tuesday" half has a 4% elapsed-vs-moving gap and a casual title, so it may not be a full effort. Kept; the summary shows it with and without.
- Caveats: tags, edits and effort scans are read as they are today (not as they were then), so a re-tag since is invisible. With n = 6, and n = 2 marathons, nothing below is a calibration. It is a check on whether the idea is plausible at all.

## Estimators (k = 1.06 unless stated)
- **(a) Riegel** `T2 = T1 × (D2/D1)^1.06`, T1/D1 from a race PB or best effort in the window; D2 = nominal 42.195 / 21.0975 km. **(a')** k = 1.08.
  - **"Best available" (the pre-stated rule):** the longest band (5k/10k/half/full, a source up to the race's own distance), fastest equivalent within the band.
  - Per-source: 5k, 10k, half.
  - **(a-fast), added after the fact:** the fastest equivalent among the 10k and half sources. See "What went wrong".
- **(b) Key effort:** best effort at half the race (marathon → half, half → 10k) pace × race distance.
- **(c) Durability:** not computable. R11.6 found the data holds no per-km splits, and one fastest segment can't show a fade, so estimator (c) is out.

## Per race — error = predicted − actual, window 8 weeks
| Race | Actual | (a) longest | (a') k 1.08 | 5k | 10k | (a-fast) | (b) key effort |
|---|---|---|---|---|---|---|---|
| Half, 2024-08-20 | 1:43:15 | 1:54:19 **+10.7%** | +10.7% | 1:31:10 -11.7% | 1:35:52 -7.1% | 1:35:52 -7.1% | 1:31:40 -11.2% |
| Two Oceans 2025-04-06 | 1:21:06 | 1:43:43 **+27.9%** | +27.9% | 1:22:53 +2.2% | 1:19:39 -1.8% | 1:19:39 -1.8% | 1:16:10 -6.1% |
| Practice HM 2025-05-25 | 1:21:18 | 1:20:41 -0.8% | -0.8% | 1:20:53 -0.5% | 1:21:56 +0.8% | 1:20:41 -0.8% | 1:18:21 -3.6% |
| TCS Toronto 2025-10-19 | 2:48:12 | 3:10:18 **+13.1%** | 3:12:57 +14.7% | 2:30:06 -10.8% | 3:02:24 +8.4% | 3:02:24 +8.4% | 3:02:33 +8.5% |
| Spring Half 2026-04-19 | 1:17:11 | 1:26:51 **+12.5%** | +12.5% | 1:18:49 +2.1% | 1:25:08 +10.3% | 1:25:08 +10.3% | 1:21:24 +5.5% |
| Ottawa 2026-05-24 | 2:43:38 | 2:38:59 -2.8% | 2:41:13 -1.5% | 2:42:44 -0.6% | 2:38:33 -3.1% | 2:38:33 -3.1% | 2:32:31 -6.8% |

Evidence behind each "longest" row (all best-effort *segments* inside a longer run): 24 km run 10 d before; 25.2 km run 34 d; the Two Oceans race itself 48 d (a genuine half effort); 23.3 km run 25 d; 30 km run 55 d; the 21k de Montreal 34 d. Full per-source evidence is printed by the script.

## Summary (n = 6; 8-week window)
| Estimator | Bias | Mean abs % error | Worst miss | Within ±5% |
|---|---|---|---|---|
| (a) best available, k 1.06 | +10.1% (+10:02) | **11.3%** | +27.9% (Two Oceans) | 2/6 |
| (a') k 1.08 | +10.6% | 11.3% | +27.9% | 2/6 |
| 5k only | -3.2% | 4.6% | -11.7% | 4/6 |
| 10k only | +1.2% | 5.3% | +10.3% (Spring Half) | 3/6 |
| half only | +10.1% | 11.3% | +27.9% | 2/6 |
| (a-fast) fastest of 10k/half | +1.0% | 5.3% | +10.3% | 3/6 |
| (b) key-effort pace | -2.3% | 7.0% | -11.2% | 1/6 |

- Without the informal 2024 half (n = 5): (a) 11.4%; 5k 3.2% (worst -10.8%, Toronto); 10k 4.9%; (a-fast) 4.9%; (b) 6.1%.
- Marathons only (n = 2): (a) +13.1% and -2.8%; (a-fast) +8.4% and -3.1%; 5k -10.8% and -0.6%; (b) +8.5% and -6.8%. Opposite signs, so no consistent bias to correct.
- 12-week window: essentially identical ((a) 11.3%, (a-fast) 5.5%, (b) 7.4%); no benefit from the longer window.
- Within ±3 min: (a) 1/6, (a-fast) 2/6, 5k 4/6 (halves, where 3 min is 3.7%), (b) 0–1/6.

## What went wrong (the finding that matters)
1. **"Longest distance wins" picks the wrong evidence.** `best_efforts` counts every run, so the half or 10k "best effort" is often a stretch of an easy long run (1:43:44 inside a 25 km run, a month before a 1:21:06 race). It only understates fitness, so it reads slow. That is the +28%, +13% and +12.5% misses. The pre-stated rule is bad *because of how the data is defined*, not because of Riegel.
2. **Taking the fastest equivalent (a-fast) fixes most of it**, to about 5% — but I chose that after seeing the misses. It is untested out of sample.
3. **Short sources are optimistic and long ones pessimistic.** 5k → marathon ran -10.8% (Toronto); 10k → marathon +8.4%. Riegel's exponent and the effort's intensity are confounded, and n = 2 can't separate them.
4. **A single estimator at best reaches about 5%.** For a 3:00 marathon, 5% is 9 minutes.

## What a range would look like
Leave-one-out: each race's band is its estimate ± the largest absolute % error among the *other* races.
- **(a):** ±27.9% for five of the six. That is 2:17–4:03 for Toronto and 1:55–3:23 for Ottawa. Useless; the actual landed inside 5/6.
- **(a-fast):** ±8–10% (±7 to 10 min on a half, ±16 to 19 min on a marathon): Toronto 2:43:37–3:21:11 (actual 2:48 inside), Ottawa 2:22–2:55 (inside), Spring Half 1:18–1:32 (**actual 1:17:11 outside** by 46 s). Inside 5/6.
- For a **3:00 target** the (a-fast) band is roughly 2:42–3:18 — the target sits in it whatever the training looked like. A range that wide doesn't answer "how likely is my target?"

## Evidence grade — proposed rules and what each past race would have got
Rules (on what evidence exists; no outcome used except where noted):
- **none:** no 5 km+ effort or race in the window → no range, name what's missing.
- **thin:** only sub-10 km evidence; or the best 10 km+ source is more than 56 days old; or per-source equivalents disagree by more than 10%.
- **moderate:** a 10 km+ source within 56 days.
- **strong:** a source of at least 45% of race distance within 42 days, at least two bands, and equivalents within 4% of each other.

| Race | Grade | Why | Error of (a) |
|---|---|---|---|
| Half 2024 | thin | sources disagree by 25% | +10.7% |
| Two Oceans | thin | disagree 30% | +27.9% |
| Practice HM | moderate | half source 48 d, spread 1.5% | -0.8% |
| Toronto | thin | disagree 27% | +13.1% |
| Spring Half | thin | disagree 10.2% | +12.5% |
| Ottawa | strong | half 34 d, 3 bands, spread 2.6% | -2.8% |

The grade separates the good from the bad cases cleanly here: the two non-thin races were within 3%, the four thin ones were 11–28% off. **But I set the 10% disagreement line after seeing these errors, and Spring Half sits at 10.2%** — so this is a description of six races, not a validation. Source disagreement is the signal worth keeping if anything is built.

## Next race (informational)
No race is planned after 2026-10-20 (both planned races are completed; Beneva was the last). For a hypothetical marathon from today's 8-week evidence (10k race 33:44 on 2026-09-13; best half segment 1:27:11 on 2026-09-20):
- (a) 3:01:45 (k 1.06), 3:04:17 (k 1.08); from the half segment, a 30-day-old segment inside a run.
- Per source: 5k 2:38:25, 10k 2:34:25, half 3:01:45. (b) key effort 2:54:21.
- **Grade: thin** — the sources disagree by 17.7%, which is the same signature as the four bad past races.
- COROS `race_predictions`: marathon 2:28:28, half 1:12:50 (snapshot 2026-10-11). This is a labelled, separate source. **It can't be backtested:** the first snapshot is 2026-07-09 (history exists, earlier than the roadmap's 2026-10-09 note), and every scored race predates it; the only later marathon, Beneva, is excluded. It has no scored outcomes at all.

## Recommendation
**Don't build the range now.** On this sample, the best estimator's typical error is about 5% (9 min at a 3:00 marathon, 4 min at a 1:20 half) and the worst is 10–13%; "useful" for a 3:00 target would be about ±3 min (1.7%), and no estimator was within 2% on more than 2 of 6 races (on the 2 marathons: the 5k and k 1.08 each hit one, the rest none). The 5k-only estimate was within 3 min on 4 of 6, but three of those were halves (3 min = 3.7%) and it missed Toronto by 10.8%. The pre-stated "longest source" rule failed badly (11% mean, 28% worst) because the data counts easy-run segments as efforts.

The caveat is that n is tiny (2 marathons) and the more promising rule was found after the fact, so this says "not shown to work", not "can't work". If the runner wants something small: show the per-source equivalents beside the target as labelled arithmetic ("your 10k of 33:44 equates to about 2:34 at k 1.06"), plus the source-disagreement spread, with no range, no grade and no "prediction" wording. That needs no estimator and no design-decision entry for a prediction. Revisit a real range only once there are 4+ marathons *and* effort evidence that excludes easy-run segments (for example Race/Workout-tagged runs only, untested here).

**Left for the runner:** (1) accept "don't build" and record it in the roadmap, or ask for the equivalents-only item; (2) Beneva's race record (14 km linked to a marathon; DNF or wrong link); (3) whether the 2024 half and the 17–18 km Race-tagged rows are real races.
