# UI Review — Improvement Tasks

Follow-up to `STRAVA_IMPORT_REVIEW_TASKS.md` (all backend tasks verified
complete). These tasks come from a source review of `frontend/src` against the
Velocity design system (`frontend/ui_design/CLAUDE.md`) and standard UI
practice. Ordered by impact; U1–U3 exist because the Strava import changed the
data shape underneath the UI.

Conventions: one commit per task (`ui: U1 …`), keep the Velocity dark theme
and existing component patterns (shadcn/ui + Tailwind), no new heavy
dependencies. After each task, verify the affected page renders correctly at
mobile (~380px) and desktop widths.

---

## U1 — Run History: `strava` source badge + pagination (`pages/ShoeDetail.jsx`)

Post-backfill, some shoes carry 50–70 runs.

1. The source badge is a two-way ternary
   (`run.source === 'coros' ? 'default' : 'secondary'`) — backfilled
   `source='strava'` runs render like manual ones. Replace with a variant map
   `{ coros: 'default', strava: <distinct variant/color>, manual: 'secondary' }`
   (mirrors backend Task 8's `_SOURCE_BADGES`).
2. The table renders every run unbounded. Show the latest 15 with a
   "Show all (N)" toggle (client-side is fine — the data is already fetched).

## U2 — `MileageProgressBar` must respect per-shoe `mileage_limit`

`components/MileageProgressBar.jsx` hardcodes `LIMIT_KM = 800` even though
`owned_shoes.mileage_limit` exists in the model, API response, and edit form.

- Accept `limit` from the shoe (`shoe.mileage_limit ?? 800`) at every call
  site (`MyShoes.jsx` cards, `ShoeDetail.jsx` stats row).
- Derive color bands from the effective limit (green < 75%, warning
  75–100%, destructive > 100%) — already the formula, just per-shoe now.
- Non-compact mode should print the effective limit, not the constant.

## U3 — Surface the imported training history (new Dashboard card or page)

694 imported runs currently have zero UI presence. Minimum viable slice:

1. Backend: thin REST endpoint `GET /api/training/summary?period=monthly|weekly`
   wrapping `app.services.strava_stats.training_summary` (router-level adapter
   only — no new logic).
2. Frontend: a "Training volume" card (monthly km bar chart, last 12 months)
   using the same charting approach as `PriceChart.jsx`. Place on the
   Dashboard below the stat cards, or as a new `Training` page + nav item if
   the Dashboard gets crowded — implementer's call, favor the simpler one.
3. Include run count per bucket in the tooltip.

## U4 — Keyboard focus states (global)

Custom `<button>`/`<Link>` elements define `hover:` styles only — shoe-card
footer actions, nav links, "Reset filters", note/run delete icons, "View all
activity". Tailwind preflight strips default outlines, so keyboard users get
nothing.

- Add a shared focus treatment:
  `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring
  focus-visible:ring-offset-2 focus-visible:ring-offset-background`
  (the `--ring` token already exists and is unused for this).
- Prefer adding it once via a `@layer components` utility (e.g.
  `.focus-ring`) or the shared `Button` component, then sweep the custom
  buttons in `MyShoes.jsx`, `ShoeDetail.jsx`, `Dashboard.jsx`, `Layout.jsx`.
- Verify by tabbing through each page — every interactive element must show a
  visible focus indicator.

## U5 — Run-history table on mobile (`pages/ShoeDetail.jsx`)

Seven columns overflow a ~380px viewport with no horizontal scroll.
Minimum: wrap the `<Table>` in `<div className="overflow-x-auto">`.
Better: below `sm:`, collapse to stacked run cards (date + distance on one
line; pace/HR/source on a second; notes expandable). Choose based on effort —
the wrapper alone is acceptable.

## U6 — Demote destructive actions on shoe cards (`pages/MyShoes.jsx`)

"Remove" currently has equal visual weight with "Details" in the 2×2 card
footer, and deleting a shoe now cascades away its backfilled Strava run
history. Restructure the footer:

- Primary pair: **Details** and **Log run**.
- Move **Edit** and **Remove** into a `⋯` overflow menu (shadcn
  `DropdownMenu`), with Remove styled destructive and still gated by the
  existing confirmation dialog.
- The confirmation dialog copy should mention the run count it will delete
  (available as `total_runs` on the shoe payload).

## U7 — Deal tiles should deep-link to the actual deal (`pages/Dashboard.jsx`)

`HighestDealTile` and `RecentDealRow` navigate to `/deals` generically,
dropping the clicked deal. Support `/deals?deal=<id>`: `Deals.jsx` reads the
param on mount and opens `DealDetailModal` for that deal (and clears the param
on close). Update both Dashboard components to link with the id.

## U8 — Tokenize stray hex colors

Raw hex values bypass the Velocity token system:

- The placeholder stripe `repeating-linear-gradient(#202327/#26292E)` is
  duplicated in ~5 files (`Dashboard.jsx` ×2, `MyShoes.jsx`, `ShoeDetail.jsx`
  ×2). Extract to a single utility class (e.g. `.bg-placeholder-stripes` in
  `index.css` under `@layer components`).
- Promote `#101215` (sidebar/topbar), `#1A1D22` (row divider), `#2E3239`
  (dashed add-card border), `#3A3E44` (inactive nav diamond) to CSS variables
  alongside `--surface`/`--faint`, and reference them via the Tailwind theme.
- No visual change intended — this is a pure refactor; screenshot-compare
  before/after.

## U9 — Named type scale instead of arbitrary sizes

`text-[11px]/[13px]/[15px]/[17px]/[23px]` recur across pages. Add named steps
to `tailwind.config` `fontSize` (e.g. `2xs: 11px`, `sm-plus: 13px`, `md-plus:
15px`, `lg-plus: 17px`, `stat: 23px` — pick clearer names) and sweep the
usages. Rendered output identical; the ramp becomes maintainable.

## U10 — Tabular numerals for data-dense text

Add `tabular-nums` (font-variant-numeric) to: `StatCard` values, run-history
table cells, deal prices in tiles/rows, and mileage figures. Prevents layout
shimmer as digits change and aligns columns properly.

## U11 — Small polish (batch into one commit)

- Replacement-deals horizontal scroller: add `snap-x snap-mandatory` +
  `snap-start` on cards, and an edge fade (right-side gradient) so overflow is
  discoverable.
- Retired section: default `retiredCollapsed` to `true`.
- "Adjust mileage" dialog: add one hint line noting that mileage is normally
  derived from logged runs (+ starting offset) and a manual override creates a
  discrepancy the next reconciliation will surface.
- `RecentDealRow` mixes `border-[#1A1D22]` with `border-border` elsewhere —
  resolved by U8, but verify the divider still reads correctly after
  tokenizing.

---

## Definition of done

- Tab-through pass on every page shows focus rings (U4).
- Mobile pass (~380px) on Dashboard, My Shoes, Shoe Detail — no horizontal
  page scroll, tables handled (U5).
- A shoe with `mileage_limit` set shows a bar scaled to that limit (U2).
- A backfilled Strava run is visually distinct in Run History (U1).
- Screenshot diff confirms U8/U9 changed nothing visually.
