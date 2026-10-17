# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One user: a competitive runner in Montreal. On the phone, Anton runs as an installed PWA, often opened right after a run to confirm a synced run, see which shoe it went on and check the week. On desktop at home it is for longer sessions: watching shoe deals, managing the shoe rotation and reading training analytics before a race block.

A second, read-only audience: the runner's run club, who open the public "Musa's picks" page at `/deals` (logged out) to see the current shoe deals the runner would actually buy.

## Product Purpose

A personal running platform with two deliberately independent domains:

- **Deals:** watch shoe models across eight Canadian retailers. Anton scrapes them, qualifies real discounts (at least 5% below MSRP) and surfaces the genuine opportunities.
- **Rotation and training:** a canonical history of every run (Strava archive, COROS sync, manual entries), attribution of runs to owned shoes, wear and retirement tracking, training analytics, and planned races.

An embedded assistant, Son of Anton, works over the same data through Anton's MCP server.

Success means every number is correct and identical on every surface, and the runner always confirms before anything is written.

## Positioning

Built for one runner's real data, not a generic tracker. Every shoe's mileage is a maintained ledger, every deal is measured against MSRP, and every AI or synced write waits for a human yes.

## Operating Context

- Phone use: short, glanceable sessions with one hand, outdoors or just after a run. The confirm-and-attribute flow and the Home summary are the most frequent tasks.
- Desktop use: deal hunting, price history, rotation planning, training trends and race-block context.
- Single process, local-first, deployed on one host. No multi-user features.

## Capabilities and Constraints

- Routes: Home, Training (plus activity detail), Shoes (owned rotation, shoe detail, retirement pipeline), Deals and watchlist, Retailers, New Runs (COROS inbox), Son of Anton chat, Settings and Sync. Logged out, only `/deals` renders, as the public "Musa's picks" page (read-only, no watchlist or private data); everything else shows the login.
- Frontend: React 18 + Vite + Tailwind + React Query, JSX only. Charts stay on recharts. No new heavy dependencies.
- Every UI change must work on desktop and at about 380 px on a phone.
- Derived numbers come from the server. The UI never recomputes them.
- Terminology: `Shoe` is a watchlist entry, `OwnedShoe` is a physical pair. Paces are shown as M:SS/km. Run dates are America/Toronto local dates.

## Brand Commitments

- Name: Anton. The assistant is "Son of Anton."
- The visual source of truth is `frontend/template/redesign-template.html` (re-pinned 2026-10-17 for the "Horizon" reskin, replacing the earlier "Signal" look). The user pinned its design language: a warm black ground, one amber accent, warm glass panels, bold uppercase display type and mono labels. Treat the template as visual language only, never as a replacement for the app's architecture.
- Amber is the single action and brand accent. Green, yellow and red mean only good, warning and alert states.
- Dark is the default and should not read as pitch black: the runner asked for the ground one step lighter than the template's near-black. A per-device light theme exists for daylight.

## Evidence on Hand

All content is the runner's own live data: runs, shoes, deals and retailers. The UI must never fabricate numbers, testimonials or claims.

## Product Principles

1. Correct numbers, once: show what the server computed.
2. The human is the tiebreaker: proposals and confirmations, never silent writes.
3. Glanceable on the phone, deep on the desktop.
4. Personal scale is a feature: honest and simple over elaborate.
