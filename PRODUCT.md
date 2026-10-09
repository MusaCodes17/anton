# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One person: a competitive marathon runner in Montreal, and the builder of the app. Single user, permanently; the product is never designed for multi-user or public exposure.

Situations of use, all confirmed:
- **Phone, post-run:** confirm freshly synced COROS runs, check shoe mileage and retirement status.
- **Desktop, deliberate:** review training, manage the shoe rotation, work the deal watchlist.
- **Daily glance at Home:** a launch-screen briefing (alerts, shoe wear, next race, best deals).
- **Chat with Son of Anton:** ask the embedded assistant questions or have it propose actions for confirmation.

## Product Purpose

Anton is a personal running platform that joins three things: deal watching across 8 Canadian retailers for shoe models the runner wants; a canonical history of every run (Strava archive, COROS sync, manual) attributed to owned shoes with a wear/retirement lifecycle and training analytics; and AI surfaces (an MCP server at `/mcp` for Claude Desktop, plus the in-app assistant Son of Anton). Success is correct numbers, once, with the runner as final decision-maker.

## Positioning

Shoe lifecycle and deal hunting live in one private, local-first tool that owns the runner's 8-year history (~933 activities, ~8,000 km), ties it to each pair's wear, and watches prices for the next pair. Its AI copilot proposes but never writes without the runner's confirmation. Strava, Runna, or a deal-tracker site cannot truthfully claim both halves, nor the confirmation-gated, private AI.

## Operating Context

FastAPI + SQLite backend, React/Vite/Tailwind SPA, one process on the runner's own machine, reachable remotely as an installable PWA. Run dates are America/Toronto local dates. Scraping a full retailer sweep takes 20-30+ minutes by design. Home is the aggregate launch screen (`/api/home`).

## Capabilities and Constraints

- Single user; no auth by explicit deferral; single Uvicorn worker.
- The deals domain (`shoes`, wanting) and the training domain (`owned_shoes`, owning) are deliberately independent.
- A deal is any price at least a minimum discount below MSRP.
- Every derived number is computed server-side once and served to all clients.
- Automation and AI propose; the runner confirms. No synced or AI-initiated run is logged without explicit confirmation.
- Terminology: "Shoe" = watchlist entry; "OwnedShoe" = physical pair.
- Frontend is JSX (no TypeScript), React Query, Tailwind with design tokens, recharts only for charts.
- Bilingual/French UI: not requested.

## Product Principles

1. Correct numbers, once: two surfaces must never disagree about a value.
2. The human is the tiebreaker: propose, wait, then write.
3. Personal scale is a feature: simple and honest over speculative infrastructure.
4. History is sacred in training, disposable in deals.
5. Mobile and desktop are equal citizens: the post-run phone check and the deliberate desktop session both must work.

## Accessibility & Inclusion

No formal standard required. Apply standard good practice: contrast, keyboard operability, reduced motion. Every UI change must work at desktop and ~380 px mobile.
