# Skill S05 — add-retailer

## Purpose
Bring a new retailer into the scrape pipeline, from platform identification to a verified deal.

## When to use
Adding a store; also when an existing scraper breaks *structurally* (re-run the identification steps).

## Required context
- `docs/architecture.md` §10 (scraper architecture) — including the **Retailer Status table**
  (relocated there from the changelog, 2026-07-06).
- Exemplars by platform: `scrapers/forerunners.py` (Shopify) · `scrapers/altitude_sports.py`
  (Algolia) · `scrapers/enroute_run.py` (bespoke headless-Astro).
- `docs/design_decisions.md` D1–D3 — especially D3: **no paid bot-bypass, ever**.

## Workflow
1. **Probe the platform**: `/products.json` responds → Shopify; search-XHR interception shows
   `*.algolia.net` → Algolia; neither → bespoke, or walk away (the Sporting Life precedent).
2. **Create via API/UI** so `platform_detection` runs and records `Retailer.platform`.
3. **Quirks?** Subclass in its own file + register in `scrapers/registry.py`
   (bespoke-by-name beats dynamic).
4. **Respect base-class inheritance** — the kids filter and politeness sleeps come free from
   `BaseScraper`; don't reimplement them.
5. **Verify**: `POST /shoes/test` dry-run on a known-on-sale model → full single-retailer
   scrape → confirm price records + at least one qualified deal end-to-end
   (qualification is `price < msrp` — B9-v2).
6. **Update the Retailer Status table** in `architecture.md` §10.

## Common mistakes
- Overriding `search_products` instead of `search_products_filtered` (loses the kids filter).
- Hardcoding Algolia credentials — self-rediscovery exists (D2); wire it, don't pin it.
- Removing politeness sleeps "to test faster" (D3).
- French-locale sites needing `/en` (Boutique Endurance / Le Coureur precedent).
- Fighting Cloudflare — the answer is documented: don't. Mark blocked like Sporting Life.

## Checklist
- [ ] Platform recorded on the Retailer row
- [ ] Dry-run finds the test shoe
- [ ] One real deal qualified end-to-end
- [ ] Retailer Status table updated (architecture.md §10)
- [ ] No new dependency, no bypass service
- [ ] Wrap up per S13
