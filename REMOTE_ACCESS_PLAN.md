# Anton — Remote Access & Deployment Plan (RA)

**Written:** 2026-07-09. **Status:** Plan — this document gates RA1 execution, the same role `SECURITY_PASS_PLAN.md` played for R2.1 and `TRAINING_DEPTH_PLAN.md` for R2.7.
**Roadmap position:** RA sits between R2 (complete) and R3/R4 (**parked 2026-07-09** — see roadmap + changelog). It pulls **R5.2 (remote access story)** forward and executes it.
**Open items before code:** the D0 hosting decision (§4) and spikes S1–S3 (§5). Everything in §6 is sequenced to start only after those close.

---

## 1. Goal & Non-Goals

**RA1 goal (backend first):** the runner can perform the `sync_coros_runs` flow — and any other Anton MCP interaction — **from Claude mobile, anywhere**: no laptop awake, no home WiFi. Concretely: Anton's backend (SQLite + FastAPI + the `/mcp` mount) is reachable, authenticated, monitored, and safe on the public internet, running on an always-on host.

**RA1 non-goals (deliberate):**
- Remote web UI. The SPA stays a local/dev surface; its baked-in `VITE_ANTON_SECRET` (E7, accepted under the LAN model) is *not* acceptable in a publicly served bundle. Remote UI is RA2.
- Native mobile app (R5.1) — RA2 then R5.1.
- Any automation (R4 stays parked). C9's confirmation gates are unchanged: sync is still propose-then-confirm, just from a phone.
- Multi-user anything. Single tenant, forever, per A1's spirit.

**RA2 sketch (later, §8):** remote SPA behind real session auth → PWA as the interim mobile UI → R5.1 native client.

---

## 2. The Two Facts That Shape the Whole Design

1. **Claude mobile/web connectors are called from Anthropic's cloud, not from the phone.** A custom connector added on claude.ai is invoked by Anthropic's servers over the public internet. Consequence: a private overlay (Tailscale into the home LAN) does **not** satisfy the goal — the MCP endpoint must be publicly resolvable over HTTPS with an auth mechanism the connector UI supports. (Tailscale *Funnel* and Cloudflare *Tunnel* do qualify — they publish a public HTTPS hostname — but as *transport*, not as the security boundary.) Verify current connector behavior in S1; this assumption is the plan's keystone.
2. **The laptop sleeps.** Any laptop-hosted variant fails "wherever I am" the moment the lid closes. RA1 therefore moves the *serving* substrate off the laptop — a cloud VM or an always-on home box. This amends **A1 (local-first)**: local-first survives as the *development* posture; *serving* becomes a hosted single-tenant substrate. A new design_decisions entry records this (§10).

---

## 3. Threat Model Shift

R2.1/E7 defends against *an untrusted process/person on the trusted LAN*, with one shared cleartext bearer token. Internet exposure changes every parameter:

| Parameter | LAN model (E7, today) | Internet model (RA1) |
|---|---|---|
| Adversary | Curious device/person on home WiFi | The entire internet: scanners, credential-stuffing bots, vuln probes — constant, automated |
| Transport | Cleartext HTTP accepted | TLS mandatory; token never travels cleartext |
| Credential | One static shared secret, baked into the SPA bundle | Per-client, individually revocable tokens; nothing secret in any bundle that could leave trusted machines |
| Surface | Everything behind the token; bind is the real control | Minimum public surface: `/mcp`, `/api`, health. Everything else (docs, admin) token-gated as today, but now audited |
| Failure visibility | None needed | Auth-failure logging, rate-limited failures, uptime monitoring — you must be able to *see* an attack |
| Availability | Laptop-is-on | Always-on host; the runner is sometimes 5,000 km from the power button |

**What does not change:** single tenant; C9 confirmation gates on all AI writes; one sanctioned write path (B7); one writer *process* (D4/E8 in-process assumptions — §6 RA1.2 pins this).

---

## 4. D0 — The Hosting Decision (the gate)

Three candidates; C is rejected outright, A is recommended, B is the fallback if RA1.5's scrape validation fails.

**Option A — small cloud VM or PaaS (recommended).** e.g. Hetzner CX22-class VM, Fly.io machine, or similar: ~$5–8 CAD/mo, 2 GB+ RAM (Playwright needs headroom), local disk volume for `~/anton-data`.
- *For:* genuinely always-on; independent of home power/ISP; platform or Caddy TLS is trivial; deploy = `git push`/`docker push`; snapshots at the provider layer are a bonus recovery path.
- *Against:* the running/purchase data leaves the house (mitigations: single tenant, disk encryption where offered, encrypted off-site backups you control — §6 RA1.4); monthly cost; **scraping now originates from a datacenter IP** — some retailers may treat DC IPs more suspiciously than a residential one. This is the one real unknown; RA1.5 measures it with R2.5's `scrape_runs` before/after comparison, and Option B is the escape hatch.

**Option B — always-on home box (Mac mini / Raspberry Pi 5) + Cloudflare Tunnel or Tailscale Funnel.**
- *For:* data stays home; residential IP keeps scraping exactly as it behaves today; no monthly fee if the hardware exists.
- *Against:* hardware cost if it doesn't; availability = home power + ISP (fails exactly when travelling, which is the use case); the tunnel adds a third party in the request path anyway; still needs all of §6's hardening — a tunnel is transport, not auth.

**Option C — laptop + tunnel. Rejected.** Availability is tied to the lid. It fails the stated goal by construction.

**Recommendation:** **A**, containerized so the same image runs on B if the scrape validation forces a retreat. The rest of this plan is host-agnostic.

**Decision record:** Chosen: **A (cloud VM)** · Date: 2026-07-09 · Why: genuinely always-on (laptop sleeps); platform TLS trivial; Option B is the documented escape hatch if RA1.5 scrape validation shows DC-IP degradation. Containerized image is host-agnostic so retreat to B costs one repoint, not a rebuild.

---

## 5. Discovery Spikes (before any code)

**S1 — How claude.ai / Claude mobile custom connectors authenticate.** What does the connector configuration actually accept today: OAuth 2.1 (the MCP-spec path)? A bearer/custom header field? URL only? And confirm custom connectors (tools *and* prompts) are usable from the mobile app UI, not just web. **Outcome decides RA1.1's mechanism** (§6). Method: Anthropic docs + a throwaway test connector.

> **S1 Findings (2026-07-09):** The claude.ai custom connector UI (Settings → Connectors → Add Custom Connector) accepts only two fields: **Remote MCP Server URL** and, under Advanced settings, an optional **OAuth Client ID + Secret**. There is no bearer-token or static-header field. GitHub issues #112 and #411 (both closed "not planned", June 2026) confirm this is by design — the connector *requires* OAuth 2.0/2.1 as the only auth mechanism. Static bearer tokens work in Claude Desktop (`mcp-remote --header`) but **not** in the claude.ai web/mobile connector UI. Important distinction: the *Messages API MCP connector* (beta `mcp-client-2025-11-20`) does accept an `authorization_token` bearer field and sends it as `Authorization: Bearer <token>` to the server — this works fine with our existing R2.1 ASGI middleware — but it is for *programmatic/API use only*, not the conversational mobile app. **Consequence for RA1.1:** three paths, in plan-defined preference order: (1) OAuth 2.1 server-side (High complexity — see §6 RA1.1); (2) capability-URL stopgap (`/mcp/<long-random-token>` in the URL — no auth fields needed, the URL *is* the credential — simple to deploy, explicitly interim per the plan); (3) defer mobile connector and use Claude Desktop only (achieves nothing new).

**S2 — The `sync_coros_runs` flow from mobile.** The COROS MCP connector is account-level, so it should be available on mobile; verify. Then verify Anton's MCP *prompt* is invocable from mobile — if prompts aren't surfaced there, the fallback is cheap: the protocol is versioned prose (C6) and already lives in the assistant's working memory; it can be re-issued as pasteable instructions or a saved project instruction. Tools work regardless.

> **S2 Findings (2026-07-09):** Custom connectors configured on claude.ai web sync automatically to mobile — no mobile-specific config needed. The COROS MCP connector is account-level so it is available on mobile. Whether MCP *prompts* (as opposed to tools) are surfaced in the claude.ai mobile/web conversation UI is ambiguous from documentation alone: the Messages API connector explicitly says "only tool calls are currently supported," but a third-party DEV Community post claims the UI connector exposes "tools, prompts, and resources." **Verdict: uncertain — needs a live test.** Practically: if prompts aren't surfaced, the C6 fallback applies — `sync_coros_runs` is versioned prose that can live as a Project instruction or pasteable block. Tools (`confirm_coros_run`, etc.) are accessible regardless and cover the functional requirement.

**S3 — `mcp[cli]` 1.28 server-side auth support.** Does FastMCP expose OAuth 2.1 resource-server verification (or bearer-token hooks) that we can adopt **without breaking the pinned dependency triangle (A7)**? If auth support requires upgrading `mcp`, that upgrade is its own contained task with the pin-triangle re-verified. Outcome feeds RA1.1's build-vs-stopgap choice.

> **S3 Findings (2026-07-09):** `mcp[cli]==1.28.0` (the Anthropic MCP Python SDK) includes OAuth 2.1 data models and auth flow infrastructure. For **resource-server mode** (validating incoming bearer tokens from clients): our existing R2.1 pure-ASGI middleware already does this — it intercepts `Authorization: Bearer <token>` before the request reaches the MCP layer; no SDK auth changes needed. For **full OAuth authorization-server mode** (the mode required for the connector UI — implementing authorization endpoint, token endpoint, PKCE): the SDK has supporting models, but building a minimal single-user OAuth 2.1 server is a meaningful implementation (authorization code flow, PKCE S256, token issuance + refresh). Whether 1.28 exposes high-level helpers for this (vs just data models) needs a targeted code read during RA1.1. **No upgrade required for the capability-URL or bearer-token paths** — only the full OAuth server path might require bumping `mcp` (which is a contained task per the plan, with A7 triangle re-verification).

---

## 6. RA1 Work Items (sequenced)

### RA1.0 — D0 decision + spikes S1–S3 ✅ Done (2026-07-09)
Close §4 and §5; record outcomes in this file (decision record + a short findings note per spike). **Acceptance:** hosting chosen ✓; connector auth mechanism known ✓; mobile prompt story known (uncertain — C6 fallback documented) ✓; MCP-SDK auth capability known ✓. *Complexity: Low (research).* **Spike outcomes recorded in §4 (D0) and §5 (S1/S2/S3 findings blocks). Next: RA1.1 ∥ RA1.2.**

### RA1.1 — Auth v2: per-client tokens + capability-URL for connector

**Chosen mechanism (S1 + D0 decision, 2026-07-09):** capability-URL stopgap for the claude.ai connector, named per-client bearer tokens for all other surfaces. OAuth 2.1 deferred (explicitly interim, recorded here).

**What changes:**

1. **Named per-client bearer tokens** replacing the single shared `ANTON_SECRET`. Env-var registry: `ANTON_TOKENS="desktop:xxx,spa:yyy,loopback:zzz"` (one entry per named consumer). The existing pure-ASGI middleware is updated to: (a) load the token map at startup, (b) constant-time compare the Authorization header against the map, (c) log the *client name* on success and source IP + path on every 401.

2. **Capability-URL for the claude.ai connector.** Add `ANTON_CONNECTOR_TOKEN=<long-random-32+-char-hex>` to `.env`. Mount (or redirect) the MCP server at `/mcp/<CONNECTOR_TOKEN>` in addition to `/mcp`. The ASGI middleware exempts paths matching `/mcp/<CONNECTOR_TOKEN>/*` from bearer-header auth — the URL token IS the credential. **Implementation note:** the cleanest approach is path-rewriting in the ASGI middleware: strip the token prefix and forward as `/mcp/...`, keeping the FastMCP mount at a single point. Alternatively, `app.mount(f"/mcp/{CONNECTOR_TOKEN}", mcp_app)` alongside `app.mount("/mcp", mcp_app)` — test for FastMCP lifespan idempotency before choosing. The connector URL is `https://<host>/mcp/<CONNECTOR_TOKEN>` — entered as-is in Settings → Connectors; no auth credentials needed in the UI.

3. **Rotate `ANTON_SECRET` unconditionally.** The old shared secret is baked into every SPA bundle ever built; it dies with RA1.1. The SPA gets its own named token (`spa:...`).

**Acceptance:** every consumer authenticates with its own token; revoking one client (`del ANTON_TOKENS["desktop"]`) doesn't touch the others; the claude.ai connector URL authenticates successfully over HTTPS; the old shared secret is gone from `.env`. Tests extend `test_auth.py`. Capability-URL is documented as interim in `design_decisions.md`. *Complexity: Low–Medium (capability-URL path).*

### RA1.2 — Deployment substrate
- **Containerize:** one Dockerfile — Python 3.11, Playwright + browser deps, `requirements.txt` pins intact (A7). The image is host-agnostic (Option A or B).
- **Data:** `~/anton-data` equivalent on a **local-disk volume** (never a network filesystem under SQLite). `DATABASE_URL` already supports the path.
- **One worker, pinned and documented.** D4's scrape lock and E8's rate limiter are in-process; the deployment config hard-pins a single Uvicorn worker and the constraint is promoted to a checkable invariant (**INV-9 candidate** in `CLAUDE.md` §14).
- **TLS:** platform-provided (Fly) or Caddy with Let's Encrypt (VM) or the tunnel's cert (Option B). The proxy must pass **streaming unbuffered** — chat SSE, scrape SSE, and `/mcp` Streamable HTTP all break behind a buffering proxy. HTTP→HTTPS redirect; HSTS.
- **Boot:** startup already runs `alembic upgrade head` (R2.2) — deploy therefore *is* migrate; keep it, and keep E4's pre-migration named backup as a deploy-runbook step for structural migrations.
- **Env:** secrets via the host's secret store / `.env` outside the image; `TZ` explicit (run-date logic already passes `America/Toronto` explicitly — verify nothing implicitly reads server-local time).
**Acceptance:** the container runs the full suite locally; deployed instance serves `/health` over HTTPS; SSE + MCP streaming verified through the proxy; exactly one worker. *Complexity: Medium.*

### RA1.3 — Surface & abuse hardening
- Auth-failure handling: log every 401 with source IP + path; add a cheap in-process failure-rate limiter or rely on the proxy/host firewall (fail2ban-style) — the goal is that a credential-stuffing bot is *slow and visible*, not that we build a WAF.
- Structured access log (one line per request: method, path, client-name-or-anon, status, duration).
- Uptime monitoring: an external pinger on `/health` (free tier of any uptime service) so "Anton is down" is a notification, not a discovery mid-sync in an airport.
- Review the public surface: `/docs`/`/openapi.json` stay token-gated (already, E7); admin endpoints (scrape-lock force-release) stay token-gated and are candidates for an admin-scoped token later — noted, not built.
**Acceptance:** a wrong-token request appears in the log and repeated failures are throttled; uptime alerts fire on a test outage. *Complexity: Low–Medium.*

### RA1.4 — Backups off-laptop
The recovery story today is "file copies on the laptop." Once the live DB lives elsewhere, that must be automated:
- **Continuous or nightly replication** to object storage the runner controls: Litestream (continuous WAL replication to S3/B2) *or* a nightly `sqlite3 .backup` + upload, retained ~14 days. Litestream preferred (point-in-time restore ≈ E4-grade safety for free); nightly snapshot acceptable if Litestream fights the container setup.
- **Pre-migration named backups continue on the host** (`shoe_deals.db.<date>-<label>.bak` convention, E2/A6) — the runbook step, unchanged in spirit.
- **A periodic snapshot pulled down to the laptop** (`~/anton-data-mirror/`) doubles as the dev-DB seed (§7 dev/prod split).
- **Restore drill:** documented, executed once against a scratch instance before cutover is called done. A backup that has never been restored is a hope, not a backup.
**Acceptance:** replication runs unattended; a restore drill has actually been performed; the laptop holds a recent snapshot. *Complexity: Low–Medium.*

### RA1.5 — Cutover & validation (runbook in §7)
Execute §7. Two validations are the exit criteria:
1. **End-to-end mobile sync:** from Claude mobile, away from home WiFi (cellular), run the sync flow — COROS MCP fetch → dedup → suggestion → confirm → `confirm_coros_run` against the remote Anton → run appears with rich fields (R2.7.1 F1) and mileage updates.
2. **Scrape validation from the new host (the DC-IP checkpoint, Option A only):** trigger a full scrape; compare per-retailer product counts in `scrape_runs` (R2.5) against the home baseline. Material degradation on multiple retailers ⇒ invoke the Option B escape hatch (same container, home box) — the deals domain must not silently rot as the price of remote training sync.
**Acceptance:** both validations pass (or B-fallback decision recorded); Claude Desktop re-pointed at the remote URL; laptop backend demoted to dev. *Complexity: Medium.*

### RA1.6 — Docs reconciliation
- `architecture.md` §11 rewritten for the internet trust model (+ §1/§2 deployment reality, §13 new host dependency).
- `design_decisions.md`: new entry for the hosting substrate (amending **A1** — local-first for dev, hosted single-tenant for serving); **E7 extended/superseded** by per-client tokens (E9 or E7-v2); the D0 decision recorded with its rejected alternatives.
- Roadmap: **R5.2 closed as pulled-forward-and-executed**; RA rows moved to project_state §3.
- `CLAUDE.md` §14: INV-9 (single worker) if adopted; deploy runbook referenced.
- `CLAUDE_DESKTOP_SETUP.md`: remote URL + new token.
**Acceptance:** a fresh session reading `docs/` describes the deployed reality, not the laptop. *Complexity: Low.*

**Sequencing:** RA1.0 → RA1.1 + RA1.2 (parallelizable once spikes close) → RA1.3 + RA1.4 → RA1.5 → RA1.6. **Auth v2 and TLS land together or not at all** — a public bind with the current single shared cleartext token is not an intermediate state; it's a regression.

---

## 7. Cutover Runbook (draft — finalize during RA1.5)

1. Freeze writes: last home sync done; note reconciliation counts from the live DB (activities, runs, total km, attributions — the E4 pattern; as of 2026-07-08: 933 activities · 698 runs · 8,028 km · 667 attributed — re-read fresh at cutover).
2. Named backup on the laptop (`shoe_deals.db.<date>-pre-remote.bak`) — the permanent "life before hosting" restore point.
3. Provision host; deploy container with **new** per-client tokens (RA1.1); volume mounted; replication (RA1.4) armed.
4. Copy the DB file up (single file — A2's payoff). `alembic upgrade head` on boot is a no-op if heads match; verify head = current.
5. **Reconcile:** re-run the counts remotely; must match step 1 exactly.
6. Re-point Claude Desktop (`mcp-remote --header` → remote URL + its token); add the claude.ai custom connector (mobile); update SPA `VITE_API_URL` + its token for local dev use.
7. Run RA1.5 validation #1 (mobile sync E2E, on cellular) and #2 (scrape comparison).
8. Demote the laptop backend to dev: local dev DB = latest pulled snapshot; laptop never writes to production data again except via the API like any other client.
9. Update docs (RA1.6); changelog entry; project_state snapshot.

**Dev/prod split after cutover:** production = the host (one worker, auto-migrating on deploy, replicated backups). Development = laptop against a snapshot DB. Structural migrations follow E4 on the *host* (named backup step in the deploy runbook). "The live DB is the only DB" (A1/E4) remains true — it just no longer lives on the machine you develop on, which is strictly safer.

---

## 8. RA2 — Remote Clients (sketch only; do not execute in RA1)

1. **SPA served remotely behind real session auth** — a login page + httpOnly session cookie (or per-device token issued at login) replaces the baked bundle secret entirely; serve the built SPA from the same host (FastAPI static or Caddy).
2. **PWA pass** — manifest + installable icon + mobile-polish sweep (the ~380 px discipline already exists) = a "mobile app" for the cost of a session, buying time before R5.1.
3. **R5.1 native client** then consumes the same API from anywhere, TLS + token story already solved; the OpenAPI contract-generation spike (A5's named trigger) fires here.

RA2 slots after RA1 and before/with R5.1; R3 agents can proceed before it (they need RA1 only if they should be reachable remotely).

---

## 9. Risks & Open Questions

| Risk | Exposure | Mitigation |
|---|---|---|
| Connector auth doesn't support headers | Blocks RA1.1 option 1 | S1 first; OAuth path (S3) or capability-URL stopgap, explicitly interim |
| MCP prompts not invocable from mobile | Sync UX degrades | S2; protocol-as-instructions fallback (C6 — it's versioned prose) |
| Datacenter IP degrades scraping | Deal feed quietly rots | RA1.5 validation #2 with `scrape_runs` comparison; Option B escape hatch; **no** paid-bypass escalation (D3 stands) |
| Buffering proxy breaks SSE / Streamable HTTP | Chat, scrape progress, MCP all break | RA1.2 acceptance explicitly tests streaming through the proxy |
| SQLite on network storage | Corruption | Local-disk volume only; stated in RA1.2 |
| `mcp` upgrade needed for auth | Pin triangle (A7) breaks | Contained upgrade task; re-verify the triangle; suite green before merging |
| Host clock/timezone drift | run_date off-by-one | TZ explicit; conversions already pass `America/Toronto` explicitly; add a boot log line asserting the zone |
| Single worker forgotten in some future deploy tweak | D4/E8 silently broken | INV-9 + config comment + (optional) boot-time assert on worker count |

---

## 10. Invariants That Must Survive RA1 (checklist for the executing sessions)

- INV-1 mileage ledger and B7's single write path — the host move touches *where* code runs, never *how* runs are written.
- C9 confirmation gates — remote sync is still propose-then-confirm.
- E4 migration discipline — now executed on the host, with the named-backup step in the deploy runbook.
- D4/E8 single-process assumptions — pinned as one worker (INV-9 candidate).
- A7 dependency pins — any `mcp` upgrade re-verifies the triangle.
- D3 politeness — no bot-evasion escalation even if the DC IP hurts; Option B is the honest fallback.

---

*Maintenance note: fill the §4 decision record and §5 spike findings as they close; finalize the §7 runbook during RA1.5; when RA1 ships, move its rows to `project_state.md` §3, record the decisions in `design_decisions.md` (§10 list), and mark roadmap R5.2 as executed-by-RA1.*
