# REDESIGN_PLAN.md — RunDeals → **Anton**

The app has outgrown its origin: with 694 imported activities, live COROS
sync, a shoe rotation lifecycle, and an embedded assistant, it is no longer a
deals tool with extras — it is a personal running OS. This plan restructures
the product around that reality.

**Rebrand:** the application becomes **Anton**. "Son of Anton" remains the
name of the embedded AI assistant — the smart brains inside Anton.

**North star:** everything Musa needs about his running at his fingertips,
without opening Strava, the COROS app, or retailer sites.

Related docs: `strava-historical-import-plan.md`, `STRAVA_IMPORT_REVIEW_TASKS.md`,
`UI_REVIEW_TASKS.md` (all complete). Design system: Velocity
(`frontend/ui_design/CLAUDE.md`) — unchanged, this is an IA/product
restructure, not a re-theme.

---

## 1. Information architecture

Three domains plus a control room:

| Domain | Question it answers | Tab |
|---|---|---|
| **Train** | What am I doing? | Training |
| **Gear** | What do I run in? | Shoes |
| **Buy** | What should I acquire? | Deals |
| — | What needs my attention? | Home |
| — | Assistant across all domains | Son of Anton |
| — | Plumbing | ⚙ Settings (pinned bottom, not a primary tab) |

### Final navigation

    Home · Training · Shoes · Deals · Son of Anton        [⚙ Settings]

Replaces the current six items (Dashboard, Deals, Tracked Shoes, Retailers,
My Shoes, Son of Anton). Tracked Shoes + Retailers dissolve into Settings and
the Deals watchlist (§4).

### Routes

| Old | New |
|---|---|
| `/` (Dashboard) | `/` (Home, rebuilt in Phase 4) |
| `/deals` | `/deals` (restructured as watchlist) |
| `/shoes` (Tracked Shoes) | management → `/settings/tracking`; visibility → `/deals` watchlist |
| `/retailers` | `/settings/retailers` |
| `/my-shoes`, `/my-shoes/:id` | `/shoes`, `/shoes/:id` (301-style `<Navigate>` redirects from old paths) |
| — | `/training` (new) |
| `/assistant` | `/assistant` (unchanged) |

---

## 2. Mobile-first design constraints (future native/mobile app)

A mobile app will be built from this later. Every phase must respect:

1. **API-first**: every piece of data the UI shows comes from a clean JSON
   endpoint — no logic that exists only in React. The future mobile client
   consumes the exact same API. If a page computes something non-trivially
   client-side (e.g. filtering/grouping), ask whether it belongs in the API.
2. **Bottom-nav-ready IA**: 5 primary destinations is the iOS/Android tab-bar
   maximum — the new nav fits exactly (Settings lives behind a gear icon /
   profile, standard mobile pattern). Do not add a 6th primary tab.
3. **Touch targets**: all interactive elements ≥44×44px effective hit area.
   The shoe-card footer buttons and icon-only deletes must comply.
4. **Responsive as a first-class deliverable**: every phase's definition of
   done includes a ~380px pass. Prefer stacked/card layouts over wide tables;
   any table gets a mobile collapse or horizontal scroll strategy.
5. **Component portability**: keep components presentational with data via
   props/hooks; no window-width branching inside business logic. Charts must
   render legibly at 340px width (fewer ticks, no fixed pixel widths).
6. **Deep-linkable state**: modals/details reachable by URL (`?deal=id`
   pattern from U7) — mobile navigation is URL/route-driven.

---

## 3. Backend: activities data unification

### Phase-3a (ships with Training tab): union endpoint

Two run stores exist today: `strava_activities` (frozen at the Jul 2026
export) and `shoe_runs` (live, COROS/manual/backfill). New runs land only in
`shoe_runs`, so any Training view reading `strava_activities` alone goes stale
immediately.

New service `app/services/activities.py`:

    unified_activities(db, *, year=None, month=None, shoe_id=None,
                       limit=None, offset=0) -> list[UnifiedActivity]

Union semantics:
- Start from `strava_activities` (runs only) LEFT-joined to `shoe_runs` via
  `shoe_runs.strava_activity_id` (gives shoe attribution where linked).
- Add `shoe_runs` rows with `strava_activity_id IS NULL` (post-export COROS/
  manual runs, and any unlinked history).
- Fields: `date, distance_km, moving_time_s?, avg_pace, avg_hr, elevation_m?,
  name?, source, shoe {id, brand, model, nickname}?, strava_activity_id?,
  shoe_run_id?`.
- Sorted date desc; stable pagination via limit/offset.

REST adapters (thin routers over the service):
- `GET /api/activities?year=&month=&shoe_id=&limit=&offset=`
- `GET /api/training/summary?period=weekly|monthly` (wraps
  `strava_stats.training_summary` but computed over the UNION, not
  `strava_activities` alone — extend `strava_stats` accordingly)
- `GET /api/training/records` (wraps `personal_bests`, same union treatment)

MCP: point the existing `get_training_summary` / `get_personal_bests` tools at
the union so Son of Anton and the web UI agree.

Tests: union dedup (a linked run appears once), post-export run appears,
shoe attribution present when linked, summary includes both stores.

### Phase-5 (later, backend-only): canonical `activities` table

The proper v2: promote to a single `activities` table (superset of
`strava_activities` columns + `source`), migrate both stores into it,
`shoe_runs` becomes an attribution row referencing `activities.id`, and
`confirm_coros_run` / `log_run` write activities first. **Explicitly out of
scope for this redesign** — the union endpoint isolates the UI from this
change, so it can happen any time without touching the frontend.

---

## 4. Phases

Ship each phase independently; the app must be fully usable between phases.

---

### PHASE 1 — Rebrand + nav restructure + Settings consolidation

No new features. Pure reshuffle that makes the app coherent.

**P1.1 Rebrand to Anton**
- `Layout.jsx` `Brand`: name → "Anton". Keep the diamond mark for now (a
  proper mark can come later; don't bikeshed it in this phase).
- `index.html` title, any "RunDeals" strings, README/PROJECT_SUMMARY
  references. `grep -ri rundeals` must come back empty (code + docs).

**P1.2 New navigation**
- Sidebar (desktop) and mobile menu: Home, Training (placeholder route with
  an honest "coming in Phase 3" empty state), Shoes, Deals, Son of Anton.
- Settings entry pinned at sidebar bottom (gear icon + "Settings"), above the
  last-scraped status line. In the mobile top-bar menu it's the last item.
- Route renames + redirects per §1 table. All internal `<Link>`s updated —
  redirects are for bookmarks, not an excuse.

**P1.3 Settings section (`/settings/*`)**
- Shell page with sub-nav (tabs or side-list): **Tracking** (the current
  Tracked Shoes page: add/remove/edit tracked shoes, target prices),
  **Retailers** (current Retailers page verbatim), **Sync & Scraping**
  (ScrapeButton + scrape status, COROS sync status/config hint, Strava import
  status: activity count + export date from a tiny `GET /api/strava/status`).
- This is a *move*, not a rewrite — reuse the existing page components,
  re-homed. Resist improving them in this phase.

DoD: nav shows 5 + settings; old URLs redirect; zero "RunDeals" strings;
mobile menu mirrors desktop; ~380px pass.

---

### PHASE 2 — Deals as a watchlist

The page answers "what am I watching and what's actionable" instead of
showing only the on-sale subset.

**P2.1 API**: `GET /api/watchlist` — every tracked shoe with: current best
active deal (if any), best-ever price + date (from `price_records`),
last-seen price per retailer, msrp, target price. One endpoint, one page load.

**P2.2 Page structure**
- **On sale now** (top): existing deal grid, sorted by savings %, using the
  existing card components + `?deal=id` modal deep-link.
- **Watching** (below, collapsed by default): header "Watching · N shoes not
  on sale". Expanded: compact rows — shoe, MSRP, target, best-ever
  (price + when), last-seen per retailer. Row affordance: edit target price
  inline or link to `/settings/tracking`.
- Keeps existing filters (brand/retailer) applied across both sections.

**P2.3 Price history sparkline** (stretch, cut first if the phase drags):
tiny sparkline per watchlist row from `price_records`; reuse `PriceChart`
internals at ~120×28px.

DoD: a tracked shoe with no deal is findable on `/deals` in ≤2 interactions;
best-ever price visible; ~380px pass (watchlist rows stack cleanly).

---

### PHASE 3 — Training tab (the flagship)

Depends on §3 Phase-3a endpoints. Three stacked layers on `/training`
(sections with anchor links, not sub-tabs — simpler and mobile-friendlier):

**P3.1 Trends (top)**
- Volume chart: weekly km bars for trailing 8 weeks, monthly toggle trailing the last 12 months.
  Tooltip: km + run count. Legible at 340px (≤12 ticks, abbreviated labels).
- Stat strip: this week km, this month km, 12-month total, run count.

**P3.2 Records**
- PB cards at distance bands (5k/10k/half/full) from `/api/training/records`:
  pace, date, linked shoe when attributable. Label honestly as
  "fastest average pace" (whole-activity, not segment PBs).

**P3.3 Activities list**
- Paginated list from `/api/activities` (7/page, "load more").
- Row: date, name (when present), distance, pace, HR, source badge
  (coros/strava/manual — same variant map as U1), shoe chip linking to
  `/shoes/:id`.
- Filters: year, shoe, min distance. Mobile: rows are stacked cards.

**P3.4 Planned races card**
- New table `planned_races` (one small Alembic migration):
  `id, name, race_date (Date), distance_km (Float, nullable),
  target_time_s (Integer, nullable), location (String, nullable),
  planned_shoe_id (FK owned_shoes, nullable), notes (Text, nullable),
  status (String: 'planned' | 'completed' | 'skipped', default 'planned'),
  result_time_s (Integer, nullable, set on completion), created_at`.
- API: `GET/POST /api/races`, `PATCH/DELETE /api/races/{id}`. GET returns
  computed fields per race: `days_remaining`, `weeks_remaining`
  (days // 7), and `target_pace` derived from target_time_s / distance_km
  (formatted "M:SS/km") — computed server-side (API-first, §2.1).
- Card on `/training`, placed ABOVE Trends (the next race is the most
  time-sensitive thing on the page): upcoming races sorted by date, each
  showing name, date, distance, countdown ("9 weeks · 63 days"), target
  time + derived target pace, planned shoe chip when set. Within 14 days,
  the countdown switches to days only and gets warning-tone emphasis.
- Add/edit via a small dialog on the card (name, date, distance, target
  time, planned shoe, location, notes). Past-date races auto-display under
  a collapsed "Past races" row; marking complete captures result_time_s
  and shows delta vs target.
- Empty state: "No races planned" + add button — keep it one quiet line.
- MCP: register a `get_planned_races` tool (same shape as the API) so Son
  of Anton can answer "how many weeks to my next race" and reason about
  training blocks relative to race dates.
- Tests: countdown math (incl. race today = 0 days), target_pace derivation,
  nullable distance/target handling, past-race filtering.

DoD: a run synced from COROS yesterday appears without any Strava
involvement; totals match `get_training_summary` MCP output; ~380px pass.

---

### PHASE 4 — Home (rebuilt last, deliberately)

Home is an attention surface: four questions, four modules, every module a
teaser deep-linking into its domain tab. Build it last because Phases 1–3
define what's worth teasing.

- **Training pulse** → `/training`: this week vs last week km, last run
  (date, distance, pace, shoe).
- **Shoe alerts** → `/shoes`: shoes past 75% of `mileage_limit`, worst first
  ("DNE3 · 612 km / 800 · 3 replacement deals"). Empty state: "Rotation
  healthy" — an empty module is a *good* outcome, show it proudly and small.
- **Top deals** → `/deals`: best 2–3 active deals only, biggest-savings first.
- **Activity strip** → last COROS sync, last scrape, newest deal detected
  (absorbs the current "Recently detected" section's job in one line each).

API: single `GET /api/home` aggregating the above (one round trip — this is
also the future mobile app's launch screen, make it fast).

Remove: old Dashboard stat cards and sections not reused. `/` renders Home.

DoD: Home answers all four questions with zero scrolling at desktop, one
screenful at ~380px; every module deep-links; `GET /api/home` < 200ms locally.

---

### PHASE 5 (backlog, no UI impact)

- Canonical `activities` table migration (§3).
- `/shoes` lifecycle reframe: group active rotation by shoe type + explicit
  "retirement pipeline" section (75%+ of limit) with replacement-deal hints —
  deliberately deferred; current My Shoes page is good enough to re-home as-is
  in Phase 1.
- True app mark/logo for Anton.
- Deal Alert Agent / Weekly Rotation Summary Agent (existing backlog) now
  have natural surfaces: Home modules and Training tab.

---

## 5. Working conventions

- One phase per Claude Code session; within a phase, one commit per numbered
  task (`p2: P2.2 watchlist page structure`).
- Backend endpoints land with tests before the consuming UI task starts.
- Every phase ends with: full pytest suite green, desktop + ~380px visual
  pass, and the DoD checklist in this doc checked off.
- No new heavy frontend dependencies; charting stays on the existing library.
- Velocity design tokens only — anything new goes through `index.css`
  variables / Tailwind theme (per U8/U9 discipline).
