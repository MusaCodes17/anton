# Skill S12 — debugging

## Purpose
Where truth lives when something is wrong — the diagnostic map. Consult before changing code.

## When to use
Any "why is this number/behavior wrong" moment.

## Required context
- `docs/dependency_graph.md` §8 (hidden dependencies — most bugs live here).
- `CLAUDE.md` §6 (known traps) and §14 (invariants — which identity may have broken).
- `TROUBLESHOOTING.md` for env-level issues (note: predates the redesign; verify against
  `docs/` if it disagrees — documentation_review §3.4).

## Decision map (not steps)
- **Wrong number on screen** → every number is computed server-side exactly once; find the
  owning service (`architecture.md` §7 table). The frontend is almost never the bug.
- **Two surfaces disagree** → one of them isn't going through the shared computation — that
  *is* the bug, and a parity violation to log.
- **Run/mileage anomalies** → check the ledger identity (CLAUDE.md §14 INV-1;
  domain_model §4.5) and whether a write bypassed `rotation.log_run`; the E4 migration's
  reconciliation queries are reusable.
- **A filter mysteriously matches nothing** → you filtered on a `ShoeRun` proxy; query
  `Activity` columns instead (CLAUDE.md §6).
- **Chat has no tools** → the loopback: is `MCP_SERVER_URL` reaching *this* process?
  (dependency_graph §8.1).
- **Scraper silent** → `last_scraped_at` + per-retailer logs; Algolia 401/403 should
  self-rediscover (D2) — if not, that path broke. Check the Retailer Status table
  (architecture.md §10) for known-blocked.
- **Dates off by one** → UTC vs America/Toronto (the 145-run precedent; CLAUDE.md §6).
- **Import/startup weirdness** → dual schema tracks (A6): did a model change ship without
  a migration?

## Common mistakes
- Fixing the symptom surface (a frontend patch for a service bug).
- Adding a second computation to "correct" the first.
- Debugging the scraper against Cloudflare-blocked sites.

## Checklist
- [ ] Root cause named in the owning layer
- [ ] Fix in exactly one place
- [ ] Regression test if an invariant was involved (S09)
- [ ] New class of surprise? Add a trap line to CLAUDE.md §6 · wrap up per S13
