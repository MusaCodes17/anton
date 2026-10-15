# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One user: a competitive runner in Montreal. On the phone, Anton runs as an installed PWA, often opened right after a run to confirm a synced run, see which shoe it went on and check the week. On desktop at home it is for longer sessions: watching shoe deals, managing the shoe rotation and reading training analytics before a race block.

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

- Routes: Home, Training (plus activity detail), Shoes (owned rotation, shoe detail, retirement pipeline), Deals and watchlist, Retailers, New Runs (COROS inbox), Son of Anton chat, Settings and Sync.
- Frontend: React 18 + Vite + Tailwind + React Query, JSX only. Charts stay on recharts. No new heavy dependencies.
- Every UI change must work on desktop and at about 380 px on a phone.
- Derived numbers come from the server. The UI never recomputes them.
- Terminology: `Shoe` is a watchlist entry, `OwnedShoe` is a physical pair. Paces are shown as M:SS/km. Run dates are America/Toronto local dates.

## Brand Commitments

- Name: Anton. The assistant is "Son of Anton."
- The visual source of truth for the 2026-10 redesign is `frontend/template/redesign-template.html`. The user pinned its design language: deep ink ground, a cool signal-blue accent, light grotesque display type, mono data, glowing panels, and a lit primary button.
- Signal blue is the action and brand accent. Green, amber and red mean only good, warning and alert states.

## Evidence on Hand

All content is the runner's own live data: runs, shoes, deals and retailers. The UI must never fabricate numbers, testimonials or claims.

## Product Principles

1. Correct numbers, once: show what the server computed.
2. The human is the tiebreaker: proposals and confirmations, never silent writes.
3. Glanceable on the phone, deep on the desktop.
4. Personal scale is a feature: honest and simple over elaborate.
