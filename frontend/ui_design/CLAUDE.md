# RunDeals

Desktop web app UI for **RunDeals** — a running-shoe price/deal tracker (scrapes retailers, surfaces deals). Built as Design Components (`.dc.html`) with inline styles only.

## Files (project root)
| File | Screen |
|---|---|
| `RunDeals Velocity.dc.html` | Dashboard (main / home; "Dashboard" in nav) |
| `RunDeals Deals.dc.html` | Deals list |
| `RunDeals Shoes.dc.html` | Shoes catalog |
| `RunDeals Shoe Detail.dc.html` | Single shoe detail (price history, colorways, retailer prices) |
| `RunDeals Retailers.dc.html` | Retailers list |
| `RunDeals Concepts.dc.html` | Early exploration — 3 directions side by side: **A Velocity** (dark sporty — the chosen one), **B Paper** (light minimal), **C Splits** (techy/cool) |
| `support.js` | DC runtime — auto-generated, never edit |

Screens link to each other via the sidebar `<a href>`. Velocity = the "Dashboard" nav item.

## Design system — "Velocity" (dark sporty, the chosen direction)
- **Backgrounds:** `#0E0F11` (page), `#101215` (sidebar), `#13151A` / `#23262B` (cards & borders)
- **Text:** `#F2F2F0` primary, `#8A8F96` muted, `#6A6F76` faint
- **Borders:** `#1E2126`, `#23262B`, `#2A2E34`
- **Accent (green):** `oklch(0.74 0.17 153)` — tints use alpha, e.g. `/ 0.13`
- **Fonts (Google):** `Archivo` (800/900 — logo + headings), `Hanken Grotesk` (body), `JetBrains Mono` (labels / data / placeholders)
- **Motifs:** small rotated-square (diamond) glyphs as logo + nav bullets; rounded cards (12–16px radius); image placeholders are light `#F4F4F2` boxes with mono "product shot" text; sidebar footer shows live "Last scraped 8 min ago" status
- **Layout:** 236px fixed sidebar + scrolling content area

## Conventions
- Pure inline styles (DC requirement); fonts loaded in `<helmet>`
- Image placeholders, not real product photos (no real shoe imagery yet)
- Reference screenshots live in `screenshots/`; user uploads in `uploads/`
