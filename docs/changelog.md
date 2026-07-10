# Anton — Session Changelog

**Last Updated:** 2026-07-09
**Status / current focus:** see `docs/project_state.md` (the perishable snapshot). This file is the append-only session log — the authoritative record of *what happened*; the `docs/` suite is the reference material.

---

## Provider agentic-loop consolidation (tech_debt P1-8) — 2026-07-10

**[CHANGED] Collapsed the 3× near-identical agentic loop in `chat_service.py` into a shared `BaseLLMProvider.run()` implementation. Each provider now implements five focused abstract methods instead of duplicating ~80 lines of outer-loop logic.**

- `_ToolCall` dataclass normalises tool calls across providers (Anthropic/OpenAI populate `id`; Gemini uses `""` — no per-call IDs in that API).
- `BaseLLMProvider.run()` owns: turn counting, `call_mcp_tool` invocation, `tool_result` events, done/error signals, `MAX_AGENTIC_TURNS` exhaustion.
- Each provider implements: `_tool_schema`, `_check_configured` (API key guard), `_prepare_messages` (initialises provider-specific mutable state), `_stream_turn` (one LLM turn, pushes text/tool_call events, returns tool calls or None on error), `_append_tool_results` (appends results to state).
- Gemini's stateful `ChatSession` is encapsulated in a `{"chat": ..., "current": ...}` dict passed as opaque state — no structural change to Gemini's behaviour.
- `from __future__ import annotations` added; `Any` imported from typing.
- **Verified:** suite 231 stable. Module imports cleanly. No schema changes. No UI changes.
- **Human step:** backend restart needed to pick up the change (backend is user-managed).
- Closes tech_debt P1-8, roadmap §11 item 3. One `r2:` commit.

---

## 💾 RA1.4 — Backups off-laptop (Litestream + restore scripts) — 2026-07-09

**[ADDED] Continuous SQLite replication via Litestream; restore drill procedure; laptop snapshot-pull script. No schema changes. No UI changes. Suite stable at 231 passing. One `ra1:` commit.**

- **[ADDED] `backend/litestream.yml`** — Litestream replication config. Points at `/data/shoe_deals.db` (the Docker volume path). Replica target: S3-compatible object storage (Backblaze B2 preferred — privacy-respecting, generous free tier). All credentials injected via env vars at runtime (`LITESTREAM_BUCKET`, `LITESTREAM_ENDPOINT`, `LITESTREAM_ACCESS_KEY_ID`, `LITESTREAM_SECRET_ACCESS_KEY`) — nothing secret is baked into the image. Retention: 336 h (14 days of WAL segments). Snapshot interval: 24 h (daily full snapshot so restores don't replay months of WAL).

- **[ADDED] `backend/entrypoint.sh`** — Container startup script replacing the Dockerfile CMD. Behaviour when `LITESTREAM_BUCKET` is set: (1) if `/data/shoe_deals.db` is absent, attempts `litestream restore -if-replica-exists` (no-op if no replica exists yet — alembic creates a fresh DB instead); (2) execs `litestream replicate -exec "uvicorn ... --workers 1"` so Litestream is the foreground process and forwards signals cleanly. Without `LITESTREAM_BUCKET`: runs uvicorn directly — dev/no-backup mode, behaviour identical to before RA1.4. INV-9 (`--workers 1`) is preserved in both paths.

- **[CHANGED] `backend/Dockerfile`** — Three changes: (1) adds `sqlite3` to the apt install list (used by `pull-snapshot.sh` to verify restored DB row counts); (2) installs Litestream binary from GitHub releases (`LITESTREAM_VERSION=v0.3.13`, pinned; `dpkg --print-architecture` selects the right arch so the same Dockerfile works on amd64 cloud VMs and arm64 home boxes); (3) switches CMD from `uvicorn ...` to `/app/entrypoint.sh`.

- **[ADDED] `deploy/restore.sh`** — Standalone restore script for the **restore drill** and disaster recovery. Run from the laptop with Litestream and credentials exported. Documents the drill procedure in comments: export vars → restore to `/tmp/drill-restore.db` → verify counts match live (`SELECT COUNT(*) FROM activities` → 933+) → record drill in changelog. Supports point-in-time restore via `RESTORE_TIMESTAMP` env var. Guards against overwriting an existing file (must be intentional).

- **[ADDED] `deploy/pull-snapshot.sh`** — Pulls the latest Litestream replica snapshot to `~/anton-data-mirror/shoe_deals.db`. Intended for periodic laptop use: keeps a local dev-DB seed in sync with production without ever writing to the live DB. Prints activity count for quick sanity check; keeps the previous snapshot as `.prev` until the new one is confirmed.

- **[CHANGED] `docker-compose.yml`** — Documents the four `LITESTREAM_*` env var passthroughs in the `environment` block (all default to empty string — dev compose is unchanged; non-empty `LITESTREAM_BUCKET` activates replication).

- **[CHANGED] `deploy/.env.production.example`** — Adds a Litestream credentials section with B2 setup instructions (create private bucket → create App Key → fill in the four vars). Notes that empty `LITESTREAM_ENDPOINT` falls back to AWS S3.

- **[NOTED — human steps before RA1.4 is fully done]:**
  1. **Provision the B2 bucket** (or equivalent S3-compatible store) and fill in the four `LITESTREAM_*` vars in the production `.env`.
  2. **Run the restore drill** (`deploy/restore.sh`) against a scratch path before RA1.5 cutover. A backup that has never been restored is a hope. Record the drill result in the next changelog entry.
  3. **Pull a laptop snapshot** (`deploy/pull-snapshot.sh`) to seed the dev DB in `~/anton-data-mirror/` for local sessions after the live DB moves to the host in RA1.5.

**[VERIFIED] Suite 231 passing** (`backend/venv/bin/pytest tests/ -q`). No UI changes (`vite build` not required). No schema changes (Litestream is a replication layer, not a schema layer). **RA1.4 code → ✅; restore drill = human step before RA1.5.**

---

## 🛡️ RA1.3 — Surface & abuse hardening — 2026-07-09

**[ADDED/CHANGED] Auth-failure logging, per-IP rate limiting, structured access log, OAuth login rate limit, Caddyfile comment update. No schema changes. No UI changes. Suite 208 → 231 (+23 tests). Two `ra1:` commits.**

- **[ADDED] `backend/app/middleware/access_log.py` — `AccessLogMiddleware`:** Pure-ASGI (non-buffering) middleware that emits one structured log line per request: `{METHOD} {path} [{client}] → {status} {duration_ms:.0f}ms`. Client name comes from `scope["anton_client"]` set by `BearerAuthMiddleware` on successful named-token auth (falls back to `"anon"` for public paths and OAuth flows). Credential redaction: query-string params with keys `code`, `state`, `access_token`, `token`, `refresh_token` are replaced with `***` before logging — no Authorization headers are ever included (we log no request headers at all). Registered as the outermost middleware in `main.py` so it captures the final status code (including 401s from auth) and total end-to-end latency.

- **[CHANGED] `backend/app/middleware/auth.py`:**
  - Every 401 now logged at WARNING: `"auth 401: {METHOD} {path} from {ip}"`.
  - **Auth-failure rate limiter:** after the per-IP burst is exhausted (`AUTH_FAILURE_BURST`, default 10), the response becomes `429 Too Many Requests` with `Retry-After` instead of `401` — visible throttle on credential-stuffing bots. The goal is *slow and visible*, not a WAF. Default 10 failures/minute per IP (`AUTH_FAILURE_LIMIT_PER_MINUTE`).
  - **`_client_ip(scope)`** extracted as a module-level helper: checks `X-Forwarded-For` first (set by Caddy's `header_up X-Forwarded-For {remote_host}`), falls back to the ASGI `scope["client"]` tuple for direct connections.
  - **`scope["anton_client"]`** set to the matched token's name on successful named-bearer auth (e.g. `"desktop"`, `"spa"`, `"loopback"`), or `"oauth"` for OAuth 2.1 access tokens — consumed by `AccessLogMiddleware`.

- **[ADDED] `backend/app/services/rate_limit.py` — two new limiters:**
  - `auth_failure_limiter` — the per-IP bucket consumed by `BearerAuthMiddleware`. Env-tunable via `AUTH_FAILURE_LIMIT_PER_MINUTE` / `AUTH_FAILURE_BURST` (both default to 10). Reuses the existing `KeyedRateLimiter` primitive.
  - `login_failure_limiter` — the per-IP bucket consumed by `POST /oauth/login`. Env-tunable via `LOGIN_FAILURE_LIMIT_PER_MINUTE` / `LOGIN_FAILURE_BURST` (both default to 5). Docstring updated to describe all three limiters and their adversary models.

- **[CHANGED] `backend/app/routers/oauth.py` — login rate limiting:**
  - `login_post` gains `request: Request` parameter; checks `_login_failure_limiter.take(ip)` before the password comparison — every POST (success or failure) consumes a token, preventing timing-oracle attacks (a real user needs ≤1–2 attempts; the 5-token default burst gives ample room before throttling). Returns `429 + Retry-After` when the bucket is exhausted.
  - Failed password attempts are logged at WARNING with the client IP.
  - Module-level `_login_failure_limiter` reference enables monkeypatching in tests.
  - RA1.3 TODO comment removed from docstring (it's done).

- **[CHANGED] `deploy/Caddyfile` — credential-redaction comment updated:** reflects that the capability-URL path no longer exists (removed in RA1.1b); URI field deletion is now described as conservative OAuth hygiene rather than capability-URL protection.

- **[ADDED] `backend/app/main.py`:** `AccessLogMiddleware` imported and registered via `app.add_middleware(AccessLogMiddleware)` (added last = outermost). Middleware stack comment added explaining the three-layer order and why each sits where it does.

- **[ADDED] Tests (+23):**
  - **`test_auth.py` +5:** `test_401_is_logged_with_method_and_path` (caplog); `test_401_log_contains_source_ip`; `test_client_name_stored_in_scope_on_success`; `test_repeated_auth_failures_trigger_429` (direct middleware test with injected tight limiter, follows `test_rate_limit.py` pattern).
  - **`test_access_log.py` (new, +15):** `_redact_query` unit tests for all five sensitive param names (code, state, access_token, token, refresh_token), mixed params, empty query string, empty value; middleware integration tests for: one log line per request, method/path/status included, client name from scope, "anon" default, credential param redaction, no Authorization header in log output, non-200 status captured, non-http scope skipped.
  - **`test_oauth.py` +3:** `test_login_rate_limit_triggers_429` (monkeypatched tight limiter, 3 POSTs: 401·401·429); `test_login_every_attempt_counts_against_limiter` (success + 2 failures + rate-limited = 302·401·401·429); `test_token_path_is_public` (pre-existing; total count includes this).

- **[NOTED — human step] Uptime monitoring:** an external pinger on `/health` (free tier, e.g. Better Uptime / UptimeRobot) so "Anton is down" is a notification, not discovered mid-sync. Execute during RA1.5 cutover — the endpoint is already public and always returns `{"status": "healthy"}`.

**[VERIFIED] Suite 231 passing** (`backend/venv/bin/pytest tests/ -q`). No UI changes (`vite build` not required). No schema changes. **[GREP CHECK]** `Authorization` header never appears in any access-log-line path (the log middleware records only method, path, client, status, duration — no request headers). Credential-material redaction in the access log is tested by `test_access_log.py::test_access_log_does_not_log_authorization_header` and the `_redact_query` unit tests. The Caddyfile log filter (deletes `uri`/`Authorization`/`Cookie`) covers the proxy layer. **RA1.3 → ✅**

---

## 🔐 RA1.1b — OAuth 2.1 connector auth (Path 1: build the server) — 2026-07-09

**[ADDED/CHANGED] OAuth 2.1 authorization-server for the claude.ai connector; capability-URL deleted. Suite 194 → 210 (+18 OAuth tests, −4 capability-URL tests). Migration `0b1c2d3e4f5a` added. 5 source files new, 5 files updated. All changes in one RA1.1b batch commit.**

**Decision gate (RA1.1b):** `mcp[cli]` 1.28 exposes `OAuthAuthorizationServerProvider` Protocol + `create_auth_routes()` (4 pre-built Starlette routes: `/.well-known/oauth-authorization-server`, `/authorize`, `/token`, `/revoke`). Building the provider was a contained task — Path 1 executed; capability-URL deleted (never went public).

- **[ADDED] `backend/alembic/versions/0b1c2d3e4f5a_oauth_tables.py`** — `oauth_auth_codes` (code\_hash SHA-256, client\_id, code\_challenge, redirect\_uri, scopes, expires\_at Float, used Boolean) + `oauth_tokens` (token\_hash SHA-256, token\_type access|refresh, client\_id, scopes, expires\_at, pair\_id). Purely additive; reversible `downgrade`; no E4 backup needed (empty tables).
- **[ADDED] `OAuthAuthCode` + `OAuthToken`** ORM models in `backend/app/models/models.py`.
- **[ADDED] `backend/app/services/oauth.py`** — `AntonOAuthProvider` (9 async methods satisfying the SDK Protocol); `verify_access_token_sync` (sync DB check for ASGI middleware); `create_auth_code` (called by login page on successful auth). Token security: `token_hex(32)` (256-bit random); stored as SHA-256 hex; raw value returned once. Access token TTL: 1 h. Refresh token TTL: 30 days; rotated on use (`pair_id` links both so revoking one deletes both). Auth codes: 60 s TTL, single-use (marked `used=True` before issuing tokens, replay raises `TokenError`).
- **[ADDED] `backend/app/routers/oauth.py`** — `GET /oauth/login`: renders minimal dark-themed HTML form (no JS, mobile-safe); all OAuth params forwarded as hidden inputs (stateless — code\_challenge is not secret under TLS). `POST /oauth/login`: `secrets.compare_digest` on `ANTON_LOGIN_PASSWORD`; wrong password → 401 + form re-render with error; correct → `create_auth_code()` + `302 redirect_uri?code=...&state=...`.
- **[CHANGED] `backend/app/main.py`** — `require_auth_config()` now checks only `ANTON_TOKENS` (capability-URL removed); `create_auth_routes()` wired conditionally on `ANTON_HOST_URL`; oauth router included unconditionally.
- **[CHANGED] `backend/app/middleware/auth.py`** — Capability-URL block (`/mcp/<CONNECTOR_TOKEN>/...`) deleted. `PUBLIC_PATHS` expanded: `/.well-known/oauth-authorization-server`, `/authorize`, `/token`, `/revoke`, `/oauth/login`. OAuth fallback in `_authorized()`: when named-bearer check fails and `ANTON_HOST_URL` is set, calls `verify_access_token_sync` (SQLite sync lookup, sub-ms under INV-9). `WWW-Authenticate: Bearer realm="Anton"` added to 401 responses (RFC 6750 compliance).
- **[CHANGED] `backend/.env.example` + `deploy/.env.production.example`** — `ANTON_CONNECTOR_TOKEN` removed; OAuth vars added: `ANTON_HOST_URL`, `ANTON_LOGIN_PASSWORD`, `ANTON_OAUTH_CLIENT_ID`, `ANTON_OAUTH_CLIENT_SECRET`, `ANTON_OAUTH_REDIRECT_URI`.
- **[ADDED] `backend/tests/test_oauth.py`** — 18 tests: login GET (renders form, is public); POST wrong password → 401 + form re-render; POST correct password → 302 + code in DB; code replay → `TokenError`; used/expired code → `None`; expired/unknown access token → `False`; valid token → `True`; `get_client` registry; all OAuth protocol paths return non-401; `/.well-known` returns 200.
- **[CHANGED] `backend/tests/test_auth.py`** — `ANTON_CONNECTOR_TOKEN` env setup removed; 4 capability-URL tests removed (`test_capability_url_*`, `test_wrong_capability_url_rejected`, `test_mcp_root_without_capability_token_still_needs_bearer`).
- **[CHANGED] `docs/design_decisions.md` E9** — updated in-place to document RA1.1b Path 1 outcome; capability-URL added to Superseded table.
- **[CHANGED] `REMOTE_ACCESS_PLAN.md` §6 RA1.1** — marked Done with Path 1 outcome.

**[VERIFIED] Suite 210 passing** (`venv/bin/pytest -q`). No UI changes (`vite build` not required). Migration `0b1c2d3e4f5a` is Alembic head — verified with `alembic heads`. **RA1.1b → ✅**

---

## 🐳 RA1.2 — Deployment substrate (Dockerfile + Caddy + docker-compose + INV-9) — 2026-07-09

**[ADDED] Containerization + reverse-proxy config + invariant documentation. Suite stable at 194 passing (no code changes — "196" in previous entry was a 2-count doc drift). No schema changes. One `ra1:` commit.**

- **[ADDED] `backend/Dockerfile`** — Python 3.11-slim base; `playwright install --with-deps chromium` installs the Chromium browser and all OS-level shared libs in one step; requirements.txt pins intact (A7); `TZ=America/Toronto` set at OS level (run-date logic already passes the timezone explicitly, this ensures nothing can silently read UTC from the host clock); CMD is `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`. One worker is not a default — it is INV-9 (see below).
- **[ADDED] `backend/.dockerignore`** — excludes venv, tests/, dev scripts (view_db.py, seed_data.py, test_scraper.py), `.env`, and all `*.db` / `*.bak*` files. Secrets injected at runtime; DB lives on the mounted data volume.
- **[ADDED] `docker-compose.yml`** (repo root) — for local dev / integration testing. Port bound to `127.0.0.1:8000` only (never `0.0.0.0`); `${ANTON_DATA_DIR:-${HOME}/anton-data}:/data` volume mount; `DATABASE_URL=sqlite:////data/shoe_deals.db` + `TZ=America/Toronto` injected; `env_file: ./backend/.env` for secrets; `restart: unless-stopped`; healthcheck on `GET /health` (30 s interval, 15 s start).
- **[ADDED] `deploy/Caddyfile`** — Caddy 2 reverse-proxy config for the cloud-VM host. Key properties: (1) `flush_interval -1` on the `reverse_proxy` block — flushes immediately, required for all three unbuffered transports (chat SSE `POST /api/chat/message`, scrape-progress SSE `GET /api/scrape/stream`, MCP Streamable HTTP `/mcp/*`); buffered proxy breaks all three. (2) Credential-redacting log filter: deletes `uri`, `request>uri`, `Authorization`, and `Cookie` fields before writing — mandatory if the capability-URL connector token is in play (the token appears as a URI path segment on every request; RA1.3 names this a hard precondition). (3) HSTS header (activate after TLS is confirmed). (4) Auto Let's Encrypt TLS on the named domain block (replace `YOUR_DOMAIN` with the actual hostname before deploy).
- **[ADDED] `deploy/.env.production.example`** — production env template covering `DATABASE_URL`, `ANTON_TOKENS`, `ANTON_CONNECTOR_TOKEN`, `CHAT_RATE_LIMIT_*`, `ANTHROPIC_API_KEY`, `MCP_SERVER_URL`, `TZ`, and scraping settings. Every required field has `REPLACE_ME`; notes cite the design decision that owns each setting.
- **[CHANGED] `CLAUDE.md §14` — INV-9 added:** *"exactly one Uvicorn worker must be running — D4's in-process scrape lock and E8's in-process rate limiter each assume a single process; multiple workers give each its own lock state and rate-limit bucket, silently breaking both invariants. Owned by deployment config (`--workers 1` in Dockerfile CMD). Verify in `docker ps` / uvicorn logs on any restart."* Enforcement is config-level, not code-level; if multiple workers are needed, redesign D4/E8 first.
- **[NOTED] Remaining RA1.2 acceptance criteria are human steps** (cannot be verified without a provisioned host): deployed instance serves `/health` over HTTPS; chat SSE + scrape SSE + MCP streaming verified through the live Caddy proxy; exactly one worker confirmed in process list. These execute during RA1.5 cutover.

**[VERIFIED] Suite 194 passing** (`venv/bin/python -m pytest`; no code changes — all new files are deployment artifacts and documentation). Note: project_state previously recorded "196" after RA1.1; the actual count is 194 (a 2-test count drift in the docs, likely from the `test_auth.py` rewrite replacing 2 tests net). No `vite build` needed (no UI work). No migration (no schema changes). **RA1.2 → ✅** (roadmap + `REMOTE_ACCESS_PLAN.md §6`).

---

## 🔐 RA1.0 + RA1.1 — Hosting decision, auth v2 (per-client tokens + capability-URL) — 2026-07-09

**[CHANGED/ADDED] RA1.0 research spikes (S1–S3) answered; hosting decision D0 made; RA1.1 auth v2 shipped. Also: R2.7.2 — activity-tagged past races auto-surface in the Races card + View-all dialogs. Suite 188 → 196 (+8 auth: named-token map, capability-URL; +2 races). One `ra1:` commit + one `r2:` commit.**

- **[RESEARCH] RA1.0 — Three discovery spikes closed the unknowns gating RA1.1/RA1.2:**
  - **S1 (connector auth mechanism):** claude.ai custom connector UI accepts only OAuth 2.0 — bearer-header tokens are not supported (GitHub issues #112 and #411 both closed "not planned"). Decision: use the **capability-URL** approach as an interim connector auth mechanism: mount MCP at `/mcp` and accept requests on `/mcp/<CONNECTOR_TOKEN>/...` with ASGI middleware path-rewriting. No OAuth complexity; acceptable under TLS + rate limiting + failure logging (RA1.3).
  - **S2 (mobile prompt invocability):** Whether MCP prompts are invocable from claude.ai mobile is unconfirmed from docs. Decision: design for the C6 fallback (Claude Desktop agent path remains canonical for `sync_coros_runs`); treat mobile prompts as a bonus once RA1.2 proves the substrate. Recorded as a C6 reference, not a blocker.
  - **S3 (`mcp[cli]` 1.28 server-side auth):** The existing pure-ASGI bearer middleware already handles resource-server token validation correctly; no `mcp[cli]` SDK changes are needed for the bearer paths or the capability-URL approach (the ASGI layer rewrites the path before FastMCP sees it). Full OAuth flows remain deferred.
  - **D0 (hosting):** **Option A — cloud VM** (Hetzner CX22 / Fly.io Shared-CPU-1x, ~$5–8 CAD/mo). Laptop rejected (sleeps). Always-on home box is the documented escape hatch if DC-IP scrape degradation occurs at RA1.5 — no paid bypass will be engaged (D3 stands). Findings and rejected alternatives recorded in `REMOTE_ACCESS_PLAN.md` §4–§5.

- **[CHANGED] RA1.1 — Auth v2: replace single `ANTON_SECRET` with named per-client tokens (`backend/app/middleware/auth.py` — complete rewrite):**
  - `ANTON_TOKENS="name:token,..."` map (e.g. `desktop:...,loopback:...,spa:...`) replaces the single shared secret. Each client is independently revocable. `_parse_token_map()` splits on commas then `partition(":")` so tokens containing `:` are supported; `get_named_token(name)` reads the map on each call (not cached) for use by `chat_service`.
  - Constant-time multi-token comparison without short-circuiting: `result |= secrets.compare_digest(presented, token)` over every entry — no timing oracle even across N tokens.
  - **Capability-URL bypass:** if `path == /mcp/<CONNECTOR_TOKEN>` or starts with `/mcp/<CONNECTOR_TOKEN>/`, the middleware rewrites `scope["path"]` to `/mcp<rest>` and passes it through without a bearer check. Wrong token in the capability path → clean 401 (middleware blocks before rewriting).
  - `main.py`: `require_auth_config()` replaces `require_anton_secret()` — passes if `ANTON_TOKENS` OR `ANTON_CONNECTOR_TOKEN` is set; fails fast if neither is.
  - `chat_service.py` loopback: reads `get_named_token("loopback")` instead of `ANTON_SECRET`.
  - **`backend/.env`:** `ANTON_SECRET` + `VITE_ANTON_SECRET` removed; `ANTON_TOKENS=desktop:...,loopback:...,spa:...` and `ANTON_CONNECTOR_TOKEN=...` added (old secret rotated unconditionally — it was baked into every prior SPA bundle).
  - **`frontend/.env`:** `VITE_ANTON_SECRET` updated to the `spa` token value.
  - **`CLAUDE_DESKTOP_SETUP.md`:** rewritten for the named `desktop` token; added remote URL section (RA1.2) and capability-URL info for the connector.
  - **`.env.example` (backend + frontend):** updated to document the new variable shapes.

- **[ADDED] RA1.1 tests — `backend/tests/test_auth.py` rewritten (+8 net new tests):**
  - `test_first_named_token_accepted` + `test_second_named_token_accepted` — any token in the map passes.
  - `test_unregistered_token_rejected` — a token not in the map gets 401 even if it looks plausible.
  - `test_capability_url_reaches_mcp` + `test_capability_url_path_without_trailing_slash` — correct connector token in the URL clears auth.
  - `test_wrong_capability_url_rejected` — wrong token in the URL → 401.
  - `test_mcp_root_without_capability_token_still_needs_bearer` — `/mcp` directly still requires a bearer.
  - **Key implementation note (lazy middleware):** Starlette builds the middleware stack on the first HTTP request, not at import time. `test_http_smoke.py` was updated to set the identical `ANTON_TOKENS` map before any test fires — so whichever module runs first, both token maps agree and `test_second_named_token_accepted` doesn't fail spuriously.

- **[ADDED] R2.7.2 — Activity-tagged races auto-surface + Races card View-all dialogs (`r2:` commit):**
  - `list_races()` now queries for past activities tagged `Race` or `Parkrun` that aren't already back-linked to a `PlannedRace` row and returns them as `SimpleNamespace` synthetic entries with `from_activity=True`. Negative IDs (`-(activity.id)`) ensure no collision with real rows. `PlannedRace` rows gain `from_activity=False` via `attach_derived`.
  - `PlannedRaceResponse` schema: `from_activity: bool = False` added (no migration — response-shape only; the field is populated at service level, never stored).
  - `PlannedRacesCard`: replaced the "Past races ▾" accordion toggle with inline `VISIBLE_LIMIT=2` previews + "View all · N" dialog buttons for both upcoming and past sections — consistent fixed-height card matching `RecordsCard`/`FitnessCard`. `from_activity=True` items are read-only (no Edit/Done/Delete buttons).
  - Tests: +2 (`test_activity_tagged_race_appears_in_list`, `test_already_linked_activity_not_duplicated`).

- **[VERIFIED] Suite 188 → 196 passing** (`venv/bin/python -m pytest`). No schema migration (RA1.1 is pure `.env`/middleware/config; R2.7.2 schema change is response-shape only). No `vite build` needed (no UI change in RA1.1; R2.7.2 UI change noted — browser pass not yet done this session). **E7 → superseded by E9** (design_decisions); **D0** recorded; **RA1.0 + RA1.1 → ✅** (roadmap). `REMOTE_ACCESS_PLAN.md` §4/§5 updated with spike findings.

---

## 🧭 Roadmap reprioritization — RA (Remote Access & Deployment) added ahead of R3/R4 — 2026-07-09

**[PLANNING — no code] R3 and R4 are parked; a new milestone RA now follows R2, pulling R5.2 (remote access story) forward and executing it. Plan doc written: `REMOTE_ACCESS_PLAN.md` (repo root, sibling of `SECURITY_PASS_PLAN.md`). Goal: sync COROS runs from Claude mobile anywhere — backend (SQLite + `/mcp`) first (RA1); remote/mobile clients later (RA2 → R5.1).**

- **[WHY] Priority call by the runner (2026-07-09):** remote reachability of the platform beats proactive agents right now. R3 agents built after RA1 also inherit the remote substrate (digests readable from a phone anywhere), and R4.1's scheduling is better designed once the process has an always-on home — parking loses little and the resume order (RA1 → R3 → R4) is recorded on the parked sections.
- **[DECISIVE FACTS in the plan (§2):** Claude mobile/web custom connectors are called from *Anthropic's cloud*, so Anton's MCP must be publicly resolvable over HTTPS — a Tailscale-into-the-LAN overlay cannot deliver the mobile-sync goal (Funnel/Tunnel qualify as transport only); and the laptop sleeps, so serving must move to an always-on host. A1 (local-first) is amended, not abandoned: dev stays local, serving becomes hosted single-tenant.]
- **[STRUCTURE] RA1 = RA1.0 hosting decision D0 + spikes S1–S3 (connector auth mechanism · mobile prompt invocability · `mcp[cli]` server-side auth vs the A7 pin triangle) → RA1.1 auth v2 (per-client revocable tokens; `ANTON_SECRET` rotated — it's baked into every SPA bundle) ∥ RA1.2 substrate (container + TLS with unbuffered streaming + one-worker pin, INV-9 candidate) → RA1.3 hardening + RA1.4 off-laptop backups (Litestream + restore drill) → RA1.5 cutover (E4-style count reconciliation; two exit criteria: mobile sync E2E on cellular, and the DC-IP scrape checkpoint measured via R2.5 `scrape_runs` with the home-box escape hatch) → RA1.6 docs. Standing rule added to the spine: **nothing internet-exposed before auth v2 + TLS land together.**
- **[DOCS] `docs/roadmap.md`:** header updated; RA section inserted after §R2.7.1 (table indexes the plan doc); R3/R4 headers marked ⏸ parked with resume conditions; R5.2 marked pulled-forward/executed-by-RA1; dependency spine redrawn with the third rule. **`docs/project_state.md`:** §11 next-step pointer → RA1.0. No source files touched; suite unchanged at 188.

---

## 🔧 R2.7.1 — Training depth follow-ups — Phase 2 Session Q — 2026-07-08

**[ADDED/CHANGED] Four self-contained fixes that close the training milestone honestly before R3: rich COROS field wiring (F1), rolling-365-day volume tile (F2), fitness end-to-end with `sync_fitness` prompt + `running_level` (F3), and Training tab 2×2 card grid (F4). Suite 185 → 188 (+3: +1 F1, +2 F3). One E4-light migration (`f2a3b4c5d6e7`). Four `r2:` commits.**

- **[ADDED] F1 — Rich COROS fields now flow through the MCP write path.** `log_run_to_shoe` lacked the nine per-run fields (`name`, `elevation_gain_m`, `moving_time_s`, `elapsed_time_s`, `avg_cadence`, `calories`, `training_load`, `training_focus`, `activity_tag`) that `rotation.log_run` already accepted — they were supported at the service layer but unreachable via MCP. Added them all as Optional params with `activity_tag` vocabulary validation (matching the `confirm_coros_run` pattern). Root cause of the null landing: `sync_coros_runs` fetched only `querySportRecords` (basic fields only) and never called `getActivityDetail`. Updated prompt Step 6 to call `getActivityDetail(labelId, sportType)` per confirmed run before `confirm_coros_run`. New test: `test_log_run_persists_rich_fields` — all nine fields round-trip through `rotation.log_run`. Suite 185 → 186.

- **[CHANGED] F2 — "Last 12 mo" tile reconciled with the Volume header.** The stat tile computed over 12 calendar-month buckets (`Math.round`) while the header totalled a rolling-365-day range (`.toFixed(1)`) — disagreeing by window boundary and rounding. Fixed in `Training.jsx`: a stable `useMemo` trailing-365-day range drives a dedicated `useTrainingSummary('monthly', trailing365Range)` query so both figures share the same window and precision. No backend change. Suite unchanged.

- **[ADDED] F3 — Fitness metrics end-to-end: `running_level` + `sync_fitness` prompt.** The `athlete_metrics` table, `record_athlete_metrics` MCP tool, `GET /fitness` endpoint, and `FitnessCard` all existed since R2.7 T5, but nothing orchestrated the COROS fetch-confirm-record flow, so no snapshot was ever written and the card stayed hidden. Added: (a) nullable `running_level` Float column on `AthleteMetric` (migration `f2a3b4c5d6e7`, E4-light — pure additive schema, live DB backed up to `~/anton-data/shoe_deals.db.bak-running-level`, down/up round-trip verified); threaded through `services/fitness.record_snapshot`, `FitnessResponse`, and the `record_athlete_metrics` MCP tool return. (b) New `sync_fitness` MCP prompt (sibling of `sync_coros_runs`): calls COROS `queryFitnessAssessmentOverview`, presents VO2max / threshold / running-level / race predictions for runner confirmation (C9), then `record_athlete_metrics`. `FitnessCard` updated: removed race predictions (split into F4's `PredictionsCard`), added running-level tile, added actionable empty state pointing to `sync_fitness`. 2 new tests: `test_running_level_round_trips` + `test_running_level_absent_stays_none`. Suite 186 → 188. Alembic head: `f2a3b4c5d6e7`.

- **[CHANGED] F4 — Training tab 2×2 card grid.** Replaced the vertical full-width stack (conditional Fitness card, full-width Races, inline Records section without a card shell) with `grid grid-cols-1 gap-4 lg:grid-cols-2` — four consistent card-shell components above the Activities list: **Races · Records · Fitness · Predictions**. New `PredictionsCard` (extracted from `FitnessCard`; `PREDICTION_DISTANCES` lookup with loose key matching; empty state tied to `sync_fitness`). New `RecordsCard` (wraps the PBCard grid in the standard `rounded-2xl border border-border bg-card` shell; handles loading/error/empty). Mobile at 380 px stacks to single column. Suite unchanged.

- **[VERIFIED] Suite 188 passing** (`venv/bin/python -m pytest`). `vite build` clean (pre-existing chunk-size warning only). Desktop + ~380 px visual pass on the Training tab: 2×2 card grid renders at 1440 px, cards stack at 380 px, 0 console errors. **[DOCS]** this entry; project_state snapshot → Session Q, §2 suite count → 188, §11 (R2.7.1 done, R3.1 next); roadmap R2.7.1 closed.

---

## 👁️ R2.6 live browser visual pass — Phase 2 Session P — 2026-07-08

**[VERIFIED] The desktop + ~380 px live pass on R2.6 that Session M deferred (the dev backend on `:8000` was down then). Backend + frontend both up this session; no source change — verification only. project_state §11 item 0 → resolved.**

- **[VERIFIED · desktop] Server-persisted chat loads through the real app.** A fresh navigation to `/assistant` (1440 px) pulled the saved conversation *and* its messages from the backend via React Query (`useConversations` → `GET /api/chat/conversations`, messages via `qc.fetchQuery` on select) — the R2.6 core (localStorage → server) working end-to-end in the browser, not just in tests. 0 console errors (the 2 warnings are pre-existing React Router v7 future-flag notices, unrelated to R2.6).
- **[VERIFIED · mobile] The mobile chat surface (ChatDrawer) is clean at 380 px** — full-width, correct empty state with prompt suggestions, input pinned at the bottom. This is the surface a phone actually uses (the app nav collapses to a hamburger; the floating "Open Son of Anton" drawer is the entry point).
- **[VERIFIED · checkpoint substrate] `LogRunDialog` mounts and its R2.6 server read fires cleanly.** Opening Log run from a rotation card mounts `useCheckpointPrompts()` → `GET /api/checkpoint-prompts` returned **200 OK** (confirmed in the network panel), dialog rendered, 0 console errors. The "Checkpoint reached 🎯" prompt branch itself was **not** exercised live because triggering it requires logging a run that crosses a 100 km boundary — a write into the live/production DB, deliberately declined; that branch's logic is covered by `test_checkpoints.py` and the end-to-end ASGI checks (Session M).
- **[FINDING · pre-existing, not a regression] The full-page `/assistant` view does not collapse its `w-[280px]` conversation sidebar at 380 px** — the list takes the full width and the chat panel is squished off the right edge (one word per line). This fixed-width sidebar (`ChatPage.jsx:368`) predates R2.6, which only swapped the data source behind the same layout — so it is **not** an R2.6 defect. On mobile the drawer (verified above) is the intended surface, so this is low-priority responsive debt on a desktop-oriented route, noted for a future pass (project_state §11).
- **[VERIFIED] No source files touched; suite count unchanged at 185.** No `vite build` needed (no code change). Inspection screenshots were captured and discarded; the tree is clean apart from the pre-existing `docs/roadmap.md`/`settings.local.json` edits and the untracked `training-default.png`. **[DOCS]** this entry; project_state §11 item 0 → resolved + snapshot refresh.

---

## 🩹 H2 orphan-guard fix + H1 HTTP-layer smoke tests — Phase 2 Session O — 2026-07-08

**[FIXED/ADDED] Close the two deal-domain findings the Session N tests exposed: fix the B10/H2 partial-failure gap (a routine detail-fetch timeout could orphan a live deal), and add the HTTP-layer smoke slice that completes refactor.md H1. One source-behaviour change (orphan retirement) + one new test module. Suite 172 (+1 xfailed) → 185 passing (the former xfail is now a real pass; +12 smoke).**

- **[FIXED] H2 — orphan retirement no longer retires live deals on a partial detail-fetch failure** (`scrapers/orchestrator.py`). `scrape_retailer_for_shoe` now tracks two URL sets: `searched_urls` (every URL the search returned) and `fetched_urls` (products whose `get_product_details` succeeded), and orphan-retires against their **union**. Previously only successfully-fetched URLs were tracked, so a product still listed in search but whose detail call timed out (a routine 10 s `requests` timeout) had its live deal retired that scrape — under-reporting the feed/Home top-deals/replacement counts until the next successful scrape (days, with manual triggering) and eroding `detected_at` honesty. Fix (a) from refactor.md H2 (the safer of the two); the rename-cleanup behaviour B10 exists for is preserved (a URL that truly vanishes from search is in neither set). B10's "a transient scrape failure can never mass-extinguish deals" is now fully delivered. The Session N `xfail` placeholder became `test_partial_detail_failure_does_not_orphan_a_live_deal` (a real pass).
- **[ADDED] `tests/test_http_smoke.py` (+12) — the HTTP-layer slice of refactor.md H1.** One coherent domain graph (a watched shoe with a live deal + retailer + active promo, an owned shoe with an attributed run, a planned race) is seeded once into a StaticPool in-memory DB, then every router family is driven through the **real ASGI stack** (auth middleware + FastAPI routing + dependency injection + Pydantic `from_attributes` serialization): shoe-types, retailers (nested `active_promo_codes`), deals list (nested retailer), watchlist, owned-shoes list + `/runs` (the **ShoeRun→activity proxy** serialization path, exactly where the one recorded production 500 lived), activities feed + detail, training summary, races, home aggregate, dashboard stats. Assertions are shallow-but-nested (status 200 + a couple of serialized nested fields) — they catch serialization 500s, not schema contracts. Transport/env mirrors `test_auth.py` (shared `ANTON_SECRET` literal so the process-wide middleware secret matches regardless of import order; `httpx.ASGITransport`); an autouse fixture points `get_db` at the seeded engine and restores the prior override so there's no cross-module contamination with `test_auth`. Conftest docstring fixed in passing (it still said "Strava-import test suite").
- **[VERIFIED] Suite 185 passing, 0 xfailed** (`venv/bin/python -m pytest`). Full suite green including `test_auth` (no `get_db`-override contamination). No UI change. **[DOCS]** refactor.md H1 + H2 → ✅ RESOLVED; project_state §2 count + §11; this entry.

---

## 🧪 Deal-domain test gaps closed — Phase 2 Session N — 2026-07-08

**[ADDED] Close the deal-domain test gaps flagged by refactor.md H1/H2 and project_state §11 — the retirement/requalification round-trip, the orphan-retirement non-empty guard (B10), promo manual-beats-scraped (D6), and the MSRP qualification truth table — before R3 agents start leaning on the deal domain. Test-only session (no behaviour change); the known H2 partial-failure gap is captured as an `xfail` so it flips to a pass the day it's fixed. Suite 158 → 172 (+14, +1 xfailed).**

- **[ADDED] `tests/test_deal_store.py` (9 tests)** — the DealStore rules beyond the MSRP money math already in `test_deals.py`: `deactivate_deal` retires an active deal / is a silent no-op when there's nothing to retire (CLAUDE.md §7); requalification after deactivation creates a **fresh** active row while the retired one stays retired (upsert only ever refreshes an *active* deal — `detected_at` honesty preserved); the orphan guard **ignores empty `seen_urls`** (B10 — a transient empty response can't wipe the feed), retires a deal whose URL wasn't seen, keeps one whose URL was; promo upsert creates new / refreshes a re-observed scraped code / **never overwrites a `source='manual'` code's description or discount** (D6 — only `last_seen_at`/`is_active` bookkeeping is touched).
- **[ADDED] `tests/test_orchestrator.py` (5 pass + 1 xfail)** — the B9-v2 qualification truth table via an injected `StubScraper` (registry injection = no network/DOM fixtures): price **below MSRP → deal**, **at MSRP → no deal** (strictly-below boundary), **no MSRP → never a deal**; a price rising to/above MSRP on a re-scrape **deactivates** the stale deal; a deal is **orphan-retired when its URL disappears from search** (the rename case). The 6th test documents the **B10/H2 gap** (refactor.md H2): a partial detail-fetch failure (`get_product_details → None` for one still-searched product) currently orphan-retires that product's live deal, because `seen_urls` only tracks *successful* fetches. Marked `@pytest.mark.xfail(strict=False)` with the H2 reason — it asserts the *desired* behaviour (live deal survives), so it flips to a pass when H2's fix lands (orphan-retire against search-returned URLs) without locking in the bug.
- **[VERIFIED] Suite 158 → 172 passing, 1 xfailed** (`venv/bin/python -m pytest`). No source files touched — pure test addition; the fixed `conftest.py` `db` fixture (in-memory SQLite from ORM metadata) and injected stub scrapers keep it hermetic. No UI change (no `vite build` needed). **[DOCS]** this entry; project_state §11 item 1 resolved (H2 remains as documented debt, now with an xfail marker); refactor.md H1 largely satisfied (the `TestClient` HTTP-layer smoke slice remains the one open piece of H1).

---

## 💬 R2.6 — Server-side chat & memory persistence — Phase 2 Session M — 2026-07-08

**[ADDED/CHANGED] Move Son of Anton conversations *and* the 100 km checkpoint-prompt state off browser localStorage into the backend — memory is now device-independent and (for R3 agents) server-readable. The streaming endpoint stays stateless per request; persistence is a separate CRUD surface. This closes the *last* ⚠️ scheduled-to-change decision (C8 → C10); the design_decisions to-do list is now empty. Four `r2:` commits (§1 schema · §2 services+endpoints+tests · §3–§4 frontend). One additive migration (E4-light). Suite 149 → 158. Executing contract: `CHAT_PERSISTENCE_PLAN.md`.**

- **[ADDED] Two tables + migration `e1f2a3b4c5d6`.** `chat_conversations` (client-UUID PK — preserves the frontend's in-memory-first / persist-on-first-message flow; `title`, `model`, and both message arrays as **JSON columns**: `display_messages` = rich UI shape, `api_messages` = LLM shape) and `checkpoint_prompts` (`owned_shoe_id` FK + `checkpoint_km`, unique pair). **Design call:** JSON columns, not a normalized messages table — `display_messages` carries pure UI concerns (tool-call events, pill previews, dividers) that don't relationally model well, and at single-user scale (cap 50) normalizing is speculative infra (CLAUDE.md §2.5); labelled in the model docstrings. No `user_id` (single-user, no auth identity — deliberate). **E4-light:** live DB backed up (`~/anton-data/shoe_deals.db.bak-chat-persistence`); pure additive schema (no data moved, start-fresh); down→up round-trip verified clean.
- **[ADDED] Services + REST (thin adapters).** `services/chat_history.py` (list summaries / get-full / **upsert-by-id** create-or-replace with server-side cap-50 trim / idempotent delete) and `services/checkpoints.py` (list prompted set / idempotent mark). Routes: `GET/PUT/DELETE /api/chat/conversations[/{id}]` on the existing chat router; new `routers/checkpoints.py` → `GET/POST /api/checkpoint-prompts`. `LookupError → 404`; the client PUTs the full conversation on stream-end (whole-conversation replace, mirroring the old localStorage save).
- **[CHANGED] Frontend on the API (React Query).** `chatHistoryApi` + `checkpointsApi` in `api.js`; `useConversations`/`useUpsertConversation`/`useDeleteConversation` + `useCheckpointPrompts`/`useMarkCheckpointPrompted` in `useApi.js`. `ChatPage` now loads the conversation list from the server, fetches a conversation's messages on select (cached via `qc.fetchQuery`), and persists on stream-end via the upsert mutation — preserving the unsaved-empty / persist-on-first-message / delete-confirm semantics and the drawer-handoff path (now persisted immediately). `lib/conversations.js` reduced to pure helpers (`createConversation`, `generateTitle`); `LogRunDialog` checkpoint state moved to the API; **`lib/checkpoints.js` deleted**.
- **[DECISION] Start-fresh + MCP deferred.** Existing localStorage conversations are *not* migrated up (runner's call) — the server starts empty, old local data is simply no longer read. MCP exposure of chat history is deferred to R3 (the agent-facing read surface); R2.6's only consumer is the SPA. Recorded as **design_decisions C10** (✅ Keep; C8 → 🔁 Superseded).
- **[VERIFIED] Suite 149 → 158** (+6 `test_chat_history.py`: upsert round-trip, replace-not-duplicate, summary+message_count, cap-50 trims oldest keeps newest, 404 on missing, idempotent delete; +3 `test_checkpoints.py`: mark→list, idempotent mark on the unique pair, distinct checkpoints per shoe). **New endpoints exercised end-to-end** through the real ASGI stack (in-process `httpx.ASGITransport`, throwaway DB): list/upsert/get/404/delete + checkpoint mark/idempotency/list all green. `vite build` clean (pre-existing chunk-size warning only). **[NOT DONE] Live browser visual pass** — the local dev backend on `:8000` was unresponsive this session (holding the socket but timing out `/health`; connection refused), and the vite dev server proxies to it, so a live desktop/380 px pass could not run. Flagged for a follow-up once the dev backend is back; no code depends on it. **[DOCS]** design_decisions C8→Superseded + C10 added (⚠️ to-do list now empty), architecture §5 schema table (chat_conversations + checkpoint_prompts; also filled in the previously-missing `scrape_runs`/`athlete_metrics` rows, count → 16 models) + §16.7 marked done, roadmap R2.6 → project_state §3.

---

## 🔭 R2.5 — Scrape observability — Phase 2 Session L — 2026-07-08

**[ADDED] "Is Altitude quietly broken?" becomes a query instead of log archaeology. Persist one durable `scrape_runs` row per retailer per full-catalog scrape attempt (started/finished/status/counts/error), written only by the orchestrator; surface per-retailer health + trend in Settings → Sync & Scraping, with REST + MCP parity. The substrate R4.1 (scheduling) and R4.5 (watchdog) will write into. Suite 141 → 149. One additive migration (E4-light: pure schema add, no data moved).**

- **[ADDED] `ScrapeRun` model + migration `d0e1f2a3b4c5`.** New `scrape_runs` table (FK → `retailers`, cascade-deleted with its retailer — deals-domain telemetry is *disposable*, CLAUDE.md §2.6): `status` (`running`→`success`/`error`), `trigger` (`background`/`manual`; `scheduled` reserved for R4.1), `started_at`/`finished_at`, `shoes_scraped`/`products_found`/`prices_recorded`/`deals_found`, and a truncated human-readable `error` summary. Indexed on `retailer_id` + `started_at`. This is the *durable* trend history — distinct from the in-memory `scrape_state` SSE (current job only, dies on restart). **E4:** live DB backed up (`~/anton-data/shoe_deals.db.bak-scrape_runs`); pure schema add moves no data (nothing to reconcile); down/up round-trip verified clean on a throwaway DB.
- **[ADDED] Single sanctioned write path — `ScrapeOrchestrator.scrape_retailer(retailer, shoes, *, trigger)`.** The per-retailer, full-catalog unit that owns the `scrape_runs` lifecycle: stamps `running` and commits up front (an in-flight/crashed scrape is visible), loops shoes reusing the existing `scrape_retailer_for_shoe` primitive with skip-and-continue error isolation (CLAUDE.md §7), then finalizes to `success`/`error` with aggregate counts + `last_scraped_at`. Wired into both full-catalog flows: the background `POST /scrape/all` path (`_scrape_one_retailer`, `trigger="background"` — replaces its hand-rolled loop) and the synchronous `POST /scrape/retailer/{id}` (`trigger="manual"`; now also 404s on an unknown retailer). *Not yet* instrumented: the shoe-major synchronous `scrape_all_shoes` / single-shoe scrape (MCP `trigger_scrape` without a shoe_id) — its grain is shoe-major, so recording per-retailer runs there is a deliberate follow-on, noted in project_state §11.
- **[ADDED] Read service + endpoint + MCP tool (REST/MCP parity, CLAUDE.md §4.2).** `services/scrape_history.py` derives a per-retailer `health` verdict at read time (derived-never-stored, §7): `ok` / `warning` (finished clean but **zero products** — the quietly-broken signal no error status would show) / `error` / `unknown` (never scraped or currently running). `GET /api/scrape/history` returns per-retailer health + a flat newest-first `recent_runs` log in one round trip; the MCP `scrape_health` read tool serves the same payload over the same service.
- **[ADDED] Settings → Sync & Scraping "Retailer health" card.** A full-width card under the three sync cards: one status-dot row per retailer (success/warning/destructive/muted design tokens) with last product count + relative last-run time, and a header that counts retailers needing attention. `scrapeApi.history()` + `useScrapeHistory()`; the existing scrape-stream `completed` handler's `invalidateQueries()` refreshes it after a scan. Legible at ~380 px (rows wrap, no h-scroll).
- **[VERIFIED] Suite 141 → 149** (+8 in `test_scrape_history.py`, fake-scraper registry injected into the orchestrator: success/empty/error runs record the right status+counts, one run per retailer attempt regardless of shoe count, the four health verdicts incl. `running`→`unknown`, latest-run-wins + newest-first trend, recent-runs span all retailers). `vite build` clean (pre-existing chunk-size warning only). Live end-to-end on the running dev server: `GET /api/scrape/history` returned all 12 retailers `unknown` pre-scrape; a real synchronous JD Sports scrape was observed stamped `running` **mid-flight** (health `unknown`, `finished_at` null — the up-front commit working), then finalized to `success` (49 shoes, 32 products, 27 prices, 1 deal, `finished_at` set) with health flipping to `ok`. Route + MCP tool registration asserted. **[DOCS]** design_decisions gains the single-process-lock decision R2.5 forces (see below); roadmap R2.5 row → project_state §3; project_state §11 advances the active R2 thread to R2.6.

---

## 🏷️ R2.4 — Shoe-type controlled vocabulary — Phase 2 Session K — 2026-07-08

**[ADDED/CHANGED] Promote `shoe_type` from free strings to a backend-owned controlled vocabulary served to the frontend — the cross-domain join key is now validated, not silently typo-prone. Mirrors the R2.7 T1 `activity_tag` pattern. Three `r2:` commits (backend+migration, frontend). One live data migration (E4). Suite 133 → 141.**

- **[ADDED] Backend vocabulary + endpoint.** `app/utils/shoe_types.py` owns the ordered canonical list (`long_distance_racer`, `short_distance_racer`, `long_run`, `tempo`, `intervals`, `daily_trainer`, `trail`, `recovery`) + `is_valid_shoe_type` — pure, importable everywhere. `GET /api/shoe-types` serves it (dedicated router; the vocabulary is the cross-domain join key shared by both `Shoe` and `OwnedShoe`, owned by neither). This is the R2.7 T1 pattern (`app/utils/activity_tags.py` + `/api/activities/tags`) applied to shoe types.
- **[CHANGED] Write-schema validation.** A shared `validate_optional_shoe_type` on `ShoeCreate`/`ShoeUpdate` + `OwnedShoeCreate`/`OwnedShoeUpdate`: `None`/`""` clears; any other value must be in the vocabulary, else **422** with the valid list. Read schemas deliberately left unvalidated so legacy data never breaks a GET. Closes the "a typo fails silently at the replacement-deals join" gap (domain_model §4.3). Verified live: `POST /api/owned-shoes` with `shoe_type:"Race Shoe"` → 422, no row created.
- **[CHANGED] Data normalization (migration `c9d0e1f2a3b4`).** Nine legacy `owned_shoes` rows carried free-text types that predated the vocabulary and broke the join (`Daily Trainer` ×4, `Race Shoe` ×2, `Tempo shoe`/`Tempo Shoe`, `Recovery Shoe`). A **by-id remap guarded on the current value** (idempotent; no-op on a fresh DB) normalizes them; the two `Race Shoe` rows split per shoe (**confirmed with the runner**): Adidas Adios Pro 3 → `long_distance_racer` (marathon super-shoe), Nike Streakfly → `short_distance_racer` (5K/10K racer). **E4:** live DB backed up (`…-pre-r2.4-shoetype-normalize.bak`; originals also live in the R2.3 backup); reversible downgrade restores the exact originals by id (round-trip verified); counts reconciled (23 owned rows unchanged, 0 off-vocabulary remaining). *Note:* the running dev server auto-applied this on file-write (R2.2 startup runs `alembic upgrade head` on reload), so the pre-normalize restore point is the prior R2.3 backup rather than the same-session one.
- **[CHANGED/REMOVED] Frontend fetches the vocabulary; the copy is deleted.** `lib/shoeTypes.js`'s independent `SHOE_TYPES` + `SHOE_TYPE_LABELS` are gone; the file is now presentation-only — `SHOE_TYPE_BADGE_CLASSES` (design-token colours) + a shared `formatShoeType()` that title-cases the canonical value for display. New `shoeTypesApi.list()` + `useShoeTypes()` (staleTime Infinity). Both form dropdowns (`ShoeForm`, `OwnedShoeForm`), the `MyShoes` type filter + by-type grouping/labels, `ShoeTypeBadge`, and `ShoeDetail` all source the list/labels from the backend; `Deals.jsx`'s private `formatShoeType` duplicate was collapsed into the shared one.
- **[VERIFIED] Suite 133 → 141** (+8 in `test_shoe_types.py`: vocabulary membership, endpoint order, create/update accept-valid + clear-empty + reject-off-vocabulary, parametrized over all four write schemas). `vite build` clean (pre-existing chunk-size warning only). **Live visual pass** desktop + ~380 px, 0 console errors: MyShoes groups every type from the fetched vocabulary in order, and the normalized legacy shoes now group under their canonical types (screenshots taken, not committed). **[DOCS]** domain_model §4.3 (vocabulary now backend-owned + validated), ai_context §8 item 9, tech_debt P1-5, roadmap R2.4 → project_state §3. **Next active R2 item: R2.5 scrape observability.**

---

## 🛡️ R2 — Chat rate limiting (the R2.1-adjacent throttle) — Phase 2 Session J — 2026-07-08

**[ADDED] Closes the last R2.1-adjacent gap: R2.1 stopped *anonymous* LLM spend, this stops an *authenticated* client from looping and burning paid credits. One `r2:` commit. Suite 128 → 133. No migration, no UI change.**

- **[ADDED] Token-bucket rate limiter on `POST /api/chat/message`.** New `services/rate_limit.py`: a thread-safe `TokenBucket` (capacity + refill-per-second, injectable clock for deterministic tests) and a `KeyedRateLimiter` (one bucket per client IP, lazily created). A FastAPI dependency `enforce_chat_rate_limit` on the chat endpoint returns **429 + `Retry-After`** before the SSE stream starts when a client exceeds the rate. Default **20 req/min, burst 20**, tunable via `CHAT_RATE_LIMIT_PER_MINUTE` / `CHAT_RATE_LIMIT_BURST` (documented in `.env.example`). Generous for a human, a hard stop for a runaway loop.
- **[DESIGN] In-process by design, not a security boundary.** State lives in memory like the scrape lock and SSE state (single-process assumption — CLAUDE.md §4.6 / design_decisions D4/E5); a second worker would each keep its own bucket, labelled here (DB-level coordination deferred to R4.1, not solved silently). Auth (E7) remains *the* security boundary; this bounds accidental spend/loops under the single-user LAN threat model, where the realistic adversary is a bug, not a flood. Recorded as **design_decisions E8** (🕐 Keep for now).
- **[VERIFIED] Suite 128 → 133** (+5 in `test_rate_limit.py`: bucket allows-to-capacity-then-denies, time-based refill + capacity cap, per-client isolation, the 429 + `Retry-After` dependency contract, null-client key fallback). No frontend change — the 429 is a backend guardrail; a client-side "slow down" surface is a possible follow-up but out of scope. No schema change → no migration. **[DOCS]** SECURITY_PASS_PLAN §6's deferred item is now done; design_decisions gains E8; roadmap/project_state updated (this was project_state §11 item 1). **[FOLLOW-UP]** optional: surface the 429 as a chat toast; consider whether `POST /api/chat/resource/read` (the arbitrary-URI proxy) wants the same throttle (it doesn't spend LLM credits, so lower priority).

---

## ⚡ R2.3 — Indexed reads + watchlist service extraction — Phase 2 Session I — 2026-07-08

**[CHANGED/ADDED] The first non-R2.7 R2 item. Two independent seam-preserving refactors: the `unified_activities` read path moves from a whole-table Python pass to a single indexed SQL query, and the watchlist reduction is extracted out of its fat router into a service. Two `r2:` commits. Suite 127 → 128. One live migration (index-only) — E4 reconciled.**

- **[CHANGED] Part A — indexed SQL read path for `unified_activities`.** The seam used to load *every* activity + *every* `shoe_run` + *every* `owned_shoe` and filter/sort/paginate in Python. It now issues one query — `Activity` LEFT JOIN `shoe_runs` → `owned_shoes` — with all filters (year/month via `strftime`, date range, shoe, min-distance), the newest-first ORDER BY, and LIMIT/OFFSET pushed into the DB. The `UnifiedActivity` dataclass and the `unified_activities(...)` signature are byte-identical, so `home`, `strava_stats`, the `/api/activities` router, and every test are untouched callers (the seam guarantee — proven green by `test_activities_union.py`). The ORDER BY coalesces the two nullable id columns to 0 to reproduce the old `_sort_key` tiebreak exactly; `month=6` still matches June across all years. **New composite index `ix_activities_type_run_date` (activity_type, run_date)** — migration `b8c9d0e1f2a3`, additive/reversible — serves the base filter + order (verified query plan: `SEARCH activities USING INDEX ix_activities_type_run_date`, no temp b-tree sort). **E4:** live DB backed up (`~/anton-data/backups/shoe_deals.db.bak-r2.3-type-run-date-index`); index-only change moves no data (counts trivially unchanged); down/up round-trip clean; auto-applies on the dev server's next reload (R2.2 startup runs `alembic upgrade head` — already applied manually to the live DB this session). +1 test (`test_filter_composes_with_pagination_newest_first` — locks filter + ORDER BY + LIMIT/OFFSET composed in one SQL query).
- **[ADDED] Part B — `services/watchlist.py` extracted from the fat router.** The whole watchlist reduction (active-deal grouping, best-ever + latest-per-retailer single pass, image fallback, on-sale-first ordering) moves out of `routers/watchlist.py` into `build_watchlist(db) -> list[WatchlistEntry]`, returning value-object dataclasses (`WatchlistEntry`/`WatchlistBestDeal`/`WatchlistLastSeen`). The router is now a thin adapter (CLAUDE.md §4.1): its Pydantic response models gained `from_attributes` and read the dataclasses field-for-field. **This unblocks MCP watchlist parity (R3.4)** — a future tool/resource calls the same `build_watchlist` instead of re-deriving it. Behaviour unchanged: the pre-existing `test_watchlist.py` (which calls `get_watchlist` directly) passes as-is because the dataclass field names match its assertions; nested Pydantic `from_attributes` serialization verified separately. The labelled O(N) whole-table pass is preserved deliberately (personal scale — CLAUDE.md §12).
- **[VERIFIED] Suite 127 → 128** (+1 Part-A boundary test; Part B reuses the existing 4 watchlist tests unchanged). No `vite build` needed — no frontend change. No new design_decisions entry: R2.3 is planned execution, not a decision reversal. **[DOCS]** roadmap R2.3 row → project_state §3; project_state §11 advances the active R2 thread to rate-limiting / R2.4.

---

## 🔧 R2.7 Session 3 — Training-tab polish (range/records UX) — Phase 2 Session H — 2026-07-08

**[CHANGED/ADDED] Three user-reported Training-tab fixes after the T7/T8 landing, all verified live (0 console errors). Two `r2:` commits. Suite 126 → 127.**

- **[CHANGED] Date range now drives the *weekly* chart too.** The volume chart was hard-capped at 12 bars (`chartData.slice(0, 12)`), so widening the date range only visibly changed the *monthly* view (12 months = a year) while weekly stayed ~12 weeks regardless — the reported "range makes no difference until you switch to monthly". Dropped the cap: both views now span the full selected range (a 1y range → ~52 weekly bars, confirmed live). `VolumeChart` hides the hollow history markers past 16 points so a year of weeks stays legible; the accent last dot always renders. Month axis labels (T4a) carry the density.
- **[ADDED] Range totals on Trends.** The Volume card header shows `· {km} km · {runs} runs` for the selected range, summed from the ranged summary buckets (each run lands in exactly one bucket, so the total is range-consistent across weekly/monthly). Live example: 1y → "4635.3 km · 410 runs".
- **[ADDED] Records deep-link to the activity editor.** Personal-best records now carry the canonical `activity_id` (the `PersonalBest` dataclass + `/api/training/records` response + the `get_personal_bests` MCP tool), and the PB card's date links to `/activities/:id`. This closes the workflow the runner asked for: a false record — verified live on a "Track Session · 5x1K w/ 1mn rest" currently holding the 5K PB at 15:22 — can be opened and retagged Track/Intervals to exclude it (T3 eligibility). +1 test pins `activity_id` on the record. **Past races already deep-link** (T7) when promoted-from-activity; races completed manually via the dialog have no linked Activity and stay unlinked (no speculative date/distance matching).
- **[VERIFIED] Suite 126 → 127** (+1 `test_pb_carries_canonical_activity_id`). `vite build` clean; live desktop pass on `/training` (weekly 1y span, range totals, PB link → activity editor) with 0 console errors.

---

## 🏁 R2.7 Session 3 — race↔activity link + COROS-name tag inference (T7–T8) — Phase 2 Session H — 2026-07-08

**[ADDED/CHANGED] The final R2.7 session — closes the milestone (all eight sub-items T1–T8 shipped). T7 back-links a completed race to the canonical run it was; T8 suggests an activity tag from the COROS activity name at sync time. Two `r2:` commits. Suite 106 → 126. One live migration (T7) — E4 reconciled.**

- **[ADDED] T7 — `planned_races.activity_id` link.** Reversible additive migration `a7b8c9d0e1f2` adds a nullable `activity_id` FK from `planned_races` to `activities`. `PlannedRace` gains the column + an `activity` relationship (no `back_populates` — activities needn't know). `races.create_completed_from_activity` (the T6 promote-to-race flow) now sets it, so a promoted race deep-links to its run; `PlannedRaceResponse` and `race_to_dict` surface `activity_id`. Frontend: the Races card's **past-race rows become tappable links** to `/activities/:id` when linked (null-guarded — planned/manually-completed races without a link render as before). **E4:** live DB backed up (`shoe_deals.db.2026-07-08-pre-r2.7-t7.bak`) and reconciled — 936 activities / 3 planned_races unchanged, additive column present. The migration was auto-applied to the live DB by the running dev server's reload (R2.2 startup runs `alembic upgrade head`). Fresh up/down round-trips clean. +2 tests.
- **[ADDED] T8 — COROS-name tag inference (suggestion only).** New pure helper `activity_tags.suggest_tag_from_name(name)` beside the vocabulary: ordered case-insensitive keyword rules (`parkrun`→Parkrun · `interval`/`repeat`→Intervals · `track`→Track · `tempo`/`threshold`→Tempo · `long run`/`long`→Long Run · `trail`→Trail · `race`/`marathon`→Race · `recovery`/`easy`/`jog`→Easy · else None), first-match precedence so specificity wins (parkrun before race; long run before easy). The `sync_coros_runs` MCP prompt now spells out the same rules so the agent surfaces the suggested tag in the confirmation table — **never auto-applied** (C9); the runner confirms or overrides. No new endpoint (the tag reaches the DB through the existing T2 `confirm_coros_run` path). +18 test cases (each keyword mapping, case-insensitivity, precedence, no-match/empty/None, and that every suggestion is valid vocabulary).
- **[VERIFIED] Suite 106 → 126** (+2 T7 in `test_races.py`, +18 T8 cases in `test_activity_tags.py`). `vite build` clean (T7's Races-card change; chunk-size warning pre-existing). **T7 UI visual pass:** the change is additive and null-guarded (a link wrapper on completed-race rows that carry a link); build-verified. Recommend an eyeball after promoting an activity to a race — the three pre-existing planned_races rows have no `activity_id`, so the link only appears for newly-promoted races. **[DOCS]** No new design_decisions entry — the tag vocabulary (B15) already covers T8's inference as a schema-grade list; T7 is a plain additive FK. Roadmap §R2.7 marked complete; project_state refreshed. **R2.7 (Training & Activity Depth) is done end-to-end.**

---

## 🏃 R2.7 Session 2 — Training display + fitness + activity edit (T4–T6) — Phase 2 Session G — 2026-07-08

**[ADDED/CHANGED] Second execution session of R2.7. Built the display improvements, the athlete-fitness surface, and the activity edit/reassign workflow: month-labelled volume axis, a shared date-range picker, a COROS fitness card, and a full `/activities/:id` detail page with shoe reassignment (through the mileage ledger) and race promotion. Four `r2:` commits (T4a, T4b, T5, T6). Suite 97 → 106. Two live migrations (T5) — E4 reconciled.**

- **[CHANGED] T4a — month axis on the weekly volume chart.** The weekly view labelled its x-axis by ISO week number (W18…); it now labels by month (May/Jun/Jul), one tick at each month's first week (month derived from the week's ISO-Thursday). Data stays weekly; display-only. `VolumeChart` gained optional `xTicks`/`xTickFormatter`. Verified on the running app.
- **[ADDED/CHANGED] T4b — date-range filtering.** Backend: `unified_activities` and `training_summary` (and `/api/activities`, `/api/training/summary`) take inclusive `date_from`/`date_to` — a superset of the existing year/month filters (the roadmap's claim that `/api/activities` already had these was wrong; corrected). UI: a shared date-range picker in the Trends header (default last 90 days, React state only, 90d/6mo/1y presets) drives the volume chart (via a ranged summary query) and the activities list; the four stat tiles keep their fixed windows on unranged data. The Activities section's **Year select was removed** — the range is now the single time control (avoids a year-vs-range conflict). +1 backend test; desktop + ~380 px verified.
- **[ADDED] T5 — athlete fitness metrics.** New append-only `athlete_metrics` table (migration `f6a7b8c9d0e1`): `vo2max`, `threshold_pace_s_per_km`, `race_predictions` (JSON), server-stamped `captured_at`. `services/fitness.py` (`record_snapshot`/`latest`), `GET /api/training/fitness` (latest, or `has_data=false` — absence isn't an error), and a `record_athlete_metrics` MCP tool. **D1 resolved:** server-side COROS is dormant (C6), so the snapshot is recorded by the Claude-Desktop sync agent — the tool docstring points it at COROS `queryFitnessAssessmentOverview` and requires runner confirmation (C9). A Training-tab Fitness card (VO₂ max, threshold pace, 5K/10K/Half/Full predictions) renders only when a snapshot exists. Verified on the running app with a temporary snapshot (since removed). +2 tests.
- **[ADDED] T6 — activity detail/edit + reassignment + race promotion.** New `rotation.reassign_attribution(activity_id, new_shoe_id)` moves a run's attribution and its distance between both shoes **through the INV-1 ledger** (never a raw ORM write); creates the attribution if the run was unattributed; no-op when already that shoe; leaves the Activity row itself intact (contrast `delete_run`); INV-3 (unique attribution) preserved. `activities.get_activity_detail`/`update_activity` (partial tag/name/description via an `_UNSET` sentinel); `races.create_completed_from_activity` (promote-to-race, prefilling date/distance/result/`status=completed`). Endpoints: `GET /activities/{id}`, `PATCH /activities/{id}` (tag validated), `POST /activities/{id}/reassign-shoe`, `POST /activities/{id}/promote-to-race`. Frontend: a routed `/activities/:id` detail page (view all fields, edit tag/name/notes, shoe-picker reassignment, "Add to races" when tagged Race); activity rows link to it and show the tag. Mutations invalidate activities/owned-shoes/training/home/races. +6 tests; detail page verified desktop + ~380 px, 0 console errors.
- **[VERIFIED] Suite 97 → 106** (+1 T4b, +2 T5, +6 T6, +existing kept green). `vite build` clean; desktop + ~380 px passes for T4a/T4b/T5/T6 with 0 console errors (verified live via the running app). **E4:** the T5 migration was applied to the live DB after a named backup (`…-pre-r2.7-t5.bak`) with count reconciliation (936 activities unchanged; new table only). **[DOCS]** CLAUDE.md §14 INV-1 now lists `rotation.reassign_attribution` as a ledger-mutating path; roadmap §R2.7 Session-2 tasks marked; project_state refreshed. **Remaining R2.7: Session 3 — T7 (race↔activity FK link) + T8 (COROS-name tag inference).**

---

## 🏃 R2.7 Session 1 — Training depth foundation (T1–T3) — Phase 2 Session F — 2026-07-07

**[ADDED/CHANGED] First execution session of R2.7 (Training & Activity Depth), after committing `TRAINING_DEPTH_PLAN.md` (the §-numbered T1–T8 milestone contract). Landed the schema foundation and the PB correctness fix: activity tagging + richer COROS capture + an eligibility filter that stops interval sessions faking distance records. Four `r2:` commits (plan + T1 + T2 + T3). Suite 88 → 97.**

- **[ADDED] Plan — `TRAINING_DEPTH_PLAN.md`.** Grounds the eight roadmap sub-items in the actual code (corrected two roadmap claims: `Activity` already carries name/elapsed/elevation/cadence/calories so T1 adds only 4 columns; `/api/activities` takes `year/month`, **not** `date_from/date_to` as the roadmap stated — T4b now includes adding them). Sequences T1→T2→T3, then T4/T5/T6, then T7/T8 across ~3 sessions; records discovery steps (COROS field coverage) and open questions with recommended defaults.
- **[ADDED] T1 — activity tags + fitness columns.** Reversible migration `e5f6a7b8c9d0` adds four nullable columns to `activities`: `training_load`, `training_focus`, `activity_tag` (indexed — the PB query filters on it), `best_km_pace_s`. The backend-owned tag vocabulary lives in a pure module (`app/utils/activity_tags.py`, `ACTIVITY_TAGS` — Easy · Long Run · Recovery · Tempo · Intervals · Track · Workout · Trail · Parkrun · Race) served at `GET /api/activities/tags` so the frontend keeps no independent copy — the pattern R2.4 will mirror for `shoe_type`. The `UnifiedActivity` seam gains `activity_tag`, `elapsed_time_s`, `activity_id` (needed by T3/T6). **E4:** live DB backed up (`shoe_deals.db.2026-07-07-pre-r2.7-t1.bak`), reconciled — 936 activities / 701 runs / 9091.79 km / 670 attributed unchanged; fresh up/down round-trips clean. +3 tests.
- **[CHANGED] T2 — COROS field population.** The sanctioned write path now stores the per-run fields the sync used to discard: `name`, `elevation_gain_m`, `moving_time_s`, `elapsed_time_s`, `avg_cadence`, `calories`, `training_load`, `training_focus`, plus a confirmed `activity_tag`. Widened `rotation.log_run` (the single run writer — INV-2, no parallel path), `coros.confirm_run`, and the `confirm_coros_run` MCP tool with matching keyword-only optional params; all nullable so manual/Strava callers omit them. **C9:** the tool validates `activity_tag` against the vocabulary (rejects unknown), and the `sync_coros_runs` prompt now tells the agent to surface an unmapped-tag guess for the runner to confirm/override, never apply silently. Idempotent re-confirm unchanged (INV-5). +2 tests.
- **[CHANGED] T3 — PB eligibility fix.** The bug: a stop-heavy interval session could match a race distance at rep pace and register a false "5k record". `strava_stats.personal_bests()` now filters — Intervals/Track always excluded, Race/Parkrun always included, other run tags included, untagged excluded only when stop-heavy (`elapsed_time_s > 1.5 × moving_time_s`, the fallback for the untagged archive). The classifier (`activity_tags.pb_exclusion_reason`) sits beside the vocabulary. The response gained transparency fields: `personal_bests` returns a `PersonalBestsResult` (records + `excluded_count` + `excluded_reason`); `/api/training/records` wraps it (`PersonalBestsResponse` — an object now, not a bare array), the `get_personal_bests` MCP tool surfaces the counts, and the Training Records card shows "N excluded (…) — tag to reconsider". +4 tests (interval exclusion, race-always-in, elapsed guard, its exact 1.5× boundary).
- **[VERIFIED] Suite 88 → 97** (+3 T1, +2 T2, +4 T3, and the existing `test_records_attribute_shoe` updated for the new PB shape). `vite build` clean (T3's Records-card change; chunk-size warning is pre-existing). **Visual pass deferred** — the user's running dev server predates these changes and the R2.2-moved DB; the UI change is additive and null-guarded (recommend an eyeball on the Records card after the pending restart). **T3 changed the `/api/training/records` contract** from an array to `{records, excluded_count, excluded_reason}`; the frontend was updated in the same commit, but any other consumer must adapt. **[DOCS]** design_decisions gains B15 (activity-tag vocabulary) and B16 (PB eligibility rule); roadmap §R2.7 T1–T3 marked done; TRAINING_DEPTH_PLAN Session-1 tasks complete.

---

## 🗄️ R2.2 — Alembic is the sole schema authority — Phase 2 Session E — 2026-07-07

**[CHANGED/REMOVED] The schema now has exactly one authority. Startup stopped calling `Base.metadata.create_all` and instead runs `alembic upgrade head`; `create_all` survives only in the test fixtures. This closes the dual-authority trap (design_decisions A6, CLAUDE.md §9): a model edit without a migration can no longer be silently papered over on a live DB. The nine pre-Alembic `legacy_migrations/` scripts are deleted, and the live DB + all backups moved out of the repo tree to `~/anton-data/`. Three `r2:` commits, one per task. Suite 88 → 88 (unchanged — no behavior change, all-green throughout).** *(design_decisions A6 → 🔁 Superseded.)*

- **[CHANGED] Task 1 — Alembic sole authority.** New `database.run_migrations()` (programmatic `alembic upgrade head`) replaces the `init_db()`/`create_all` boot path in `main.py`'s lifespan; `seed_data.py` and the export-generated seed script call it too. The formerly-**empty** baseline revision (`cf1eccba0a79`) was the reason fresh setups still needed `create_all` — it stamped an already-populated DB and created nothing. It now recreates the exact pre-Alembic schema, captured provably: take the current models, `create_all` them, `alembic downgrade` every later migration back to baseline, dump the resulting schema. **Verified:** a fresh `upgrade head` builds a DB matching the models *table-for-table* (owned_shoes.mileage_limit, activities, planned_races all present via the later migrations); the baseline round-trips (`upgrade head` → `downgrade base` → 0 tables); the live DB (already stamped at head) treats `run_migrations()` as a no-op. `create_all` now lives only in `tests/conftest.py` + `tests/test_auth.py`.
- **[REMOVED] Task 2 — `legacy_migrations/` deleted.** The nine ad-hoc `migrate_add_*.py` scripts (marked "do not run") predated Alembic and had no remaining role once the baseline recreates their schema. Removed from the tree; git history is the archive. No code referenced them (grep-verified — only docs, updated here).
- **[CHANGED] Task 3 — live DB + backups relocated to `~/anton-data/`.** The 15 MB live SQLite file moved via atomic same-filesystem rename (the running dev server's open fd follows the inode — no data-loss window) to `~/anton-data/shoe_deals.db`; the seven historical `.bak` files + a fresh dated pre-relocate backup moved to `~/anton-data/backups/`. `DATABASE_URL` now an absolute path (`.env`); `.env.example` documents the convention and a dated-backup naming scheme (`shoe_deals.db.<YYYY-MM-DD>-<label>.bak`). Untracked the three `.bak` files that had been committed before the ignore rule existed (`git rm --cached`) and added `*.db.bak*` to `backend/.gitignore`. **Verified:** the app boots and reads the relocated live DB (936 activities). **Go-live is a human step:** the running dev server still uses the old path via its open fd — restart it to pick up the new `DATABASE_URL` (this pairs naturally with the R2.1 `ANTON_SECRET` restart still pending from Session D).
- **[VERIFIED] Full suite green at 88** (unchanged — this session changed schema *management*, not schema or behavior). No `vite build` needed (no frontend change). No new migration (the baseline was *populated*, not added — it only ever runs on fresh DBs, never on the live one). **[DOCS]** design_decisions A6 → 🔁 Superseded (entry + table row); architecture.md §5/§16.2 references updated; roadmap R2.2 row moved to project_state §3.

---

## 🔐 R2.1 — the security pass: bearer-token auth on every surface — Phase 2 Session D — 2026-07-07

**[ADDED/CHANGED] Anton's trust model moves from a *network* property ("only things that can reach port 8000 can mutate") to an *application* property ("only requests carrying the shared secret can mutate"). One shared bearer token (`ANTON_SECRET`) now gates `/api/*` and `/mcp`; the default bind is loopback; all three consumers (SPA, Claude Desktop, the Son-of-Anton loopback) send the token. This is the standing gate in front of every exposure-increasing R3–R5 feature. Executed `SECURITY_PASS_PLAN.md` §4 in order, one `r2:` commit per task. Suite 75 → 88.** *(design_decisions E1 → Superseded by new E7.)*

- **[ADDED] §7 pre-work — resolved the plan's three open questions** (`SECURITY_PASS_PLAN.md` §8 addendum, verified first-hand): **Q1** browser token = build-time `VITE_ANTON_SECRET` (rejected the `/api/config` pre-auth endpoint — complexity with no gain under the LAN threat model); **Q2** `mcp-remote --header` **confirmed supported** in the installed/latest `0.1.38` (read `parseCommandLineArgs` in the resolved package — no upgrade needed; noted the orthogonal local Node v19.4.0 `mcp-remote` crash as a non-blocker); **Q3** no hot-rotation — documented the 3-step `.env`-edit + restart procedure. Resolved **Q4** (middleware-vs-mount ordering) during implementation and asserted it in tests.
- **[ADDED] §4.1 — `ANTON_SECRET`/`VITE_ANTON_SECRET` in `.env.example` + startup fail-fast.** `main.require_anton_secret()` runs at lifespan startup and aborts the boot with a clear message if the secret is unset/empty — auth is *not* an optional feature (contrast CLAUDE.md §4.6 graceful degradation), so absence is fatal. Placed in the lifespan (not module import) so scripts/tests that don't serve requests are unaffected.
- **[ADDED] §4.2 — the auth middleware** (`app/middleware/auth.py`). A **pure ASGI** middleware (not `BaseHTTPMiddleware`) so SSE + the `/mcp` Streamable-HTTP transport stream through untouched; constant-time compare (`secrets.compare_digest`); an empty configured secret denies everything; **401 with an empty body** (no reason string, no `WWW-Authenticate`). Exempts `/`, `/health`, `/api/health` (new liveness alias) and all `OPTIONS` (CORS preflight). Registered **before** `CORSMiddleware` so CORS stays the outer wrapper and 401s still carry CORS headers. **One middleware covers the mounted `/mcp` sub-app** — asserted, not assumed (test below).
- **[CHANGED] §4.3 — default bind `0.0.0.0` → `127.0.0.1`** (`run.py`). Loopback-only is now an app property; `API_HOST=0.0.0.0` remains the explicit, now-safe LAN opt-in (documented in `.env.example`).
- **[CHANGED] §4.4 — the SPA sends the token on every request path.** `api.js` reads `VITE_ANTON_SECRET`, an axios request interceptor injects `Authorization` on all axios calls, and an exported `authHeaders()` single-sources the header for the paths that bypass axios: the chat `fetch()` calls (`/chat/message`, `/chat/resources`, `/chat/resource/read`, `/chat/providers`). **The scrape SSE was converted from a native `EventSource` (which can't send an `Authorization` header) to a `fetch()` ReadableStream reader** (frame parsing mirrors `useChatStream`; behavior preserved — retailer-done cache patch, completed→invalidate, drop→connectionLost, reattach-via-replay; `AbortController` replaces `es.close()`). Missing token → one console warning, not a hard failure (dev without `.env`). `vite build` clean.
- **[CHANGED] §4.5 — loopback client sends the token** (`chat_service.py`). Son of Anton is an MCP client of this same process's `/mcp` (the loopback, dependency_graph §8.1); once `/mcp` requires the token this client must send it or the assistant *silently* loses all tools. Added an `auth_loopback` flag on the `MCP_SERVERS` entry and a `_server_headers()` helper that attaches the token **at connect time** (chat_service is imported before `main`'s `load_dotenv`, so import-time `getenv` could capture an empty value) and **only** for the loopback entry (never leak the secret to a future external MCP server). Both `ClientSessionGroup` connect sites use it.
- **[ADDED] §4.6 — `CLAUDE_DESKTOP_SETUP.md`** (QUICKSTART.md is stale from the review): the before/after `mcp-remote` config adding `--header "Authorization: Bearer <ANTON_SECRET>"`, the literal-token-vs-`${ENV}` rationale, the Node-crash caveat, the breaking-change rollout order (**Desktop config before server restart**), and the rotation procedure.
- **[CHANGED] §4.7 — admin force-release endpoint gated.** `POST /api/admin/scrape-lock/release` (M3, Session C) is now behind the token via the middleware; removed its "intentionally unauthenticated for now (E1)" docstring note.
- **[ADDED] §4.8 — `tests/test_auth.py`, the suite's first HTTP-layer tests** (13). Driven via `httpx.ASGITransport` + `asyncio.run` in sync tests — the installed **httpx 0.28 dropped Starlette `TestClient`'s `app=` shortcut**, and the FastAPI/Starlette/sse-starlette pin triple (A7) is untouchable, so this is the robust path (no new dep; `StaticPool` in-memory DB so the threadpool-run route sees the tables). Covers: unauth `/api/owned-shoes`, `/api/chat/message`, `DELETE`, `/api/admin/scrape-lock/release`, and **`/mcp`** all 401; wrong token 401; 401 body empty; `/health`, `/api/health`, `/` open without token; authed `/api/owned-shoes` reaches the route (200, not 401); OPTIONS preflight not blocked.
- **[VERIFIED] Suite 88 passing** (75 → 88; +13 `test_auth.py`). `vite build` clean. Middleware behavior verified end-to-end via `ASGITransport` against the real app (health open, `/api` + `/mcp` 401 unauth, authed passes, OPTIONS open); loopback header injection verified at the `_server_headers()` seam. **Live go-live is a human step** — set `ANTON_SECRET`/`VITE_ANTON_SECRET`, update the Desktop `--header`, then restart the server (fail-fast). The end-to-end live smoke (real Claude Desktop sync, a real chat message spending LLM credits) is **not** run here: the user's dev servers run older code, the secret isn't set yet, and restarting mid-session would break Desktop before its config is updated — the runbook in `CLAUDE_DESKTOP_SETUP.md` §"Rollout order" is the ordered checklist. **Rate limiting on `/api/chat/message` remains a separate R2 item** (plan §6).
- **[DOCS]** design_decisions **E1 → 🔁 Superseded by E7** (new entry: the bearer-token decision, its threat model, and rejected alternatives), Superseded table row added.

---

## 🔒 Safety fixes (C1 + M3) + SECURITY_PASS_PLAN — Phase 2 Session C — 2026-07-07

**[CHANGED/ADDED] The bridge session between R1 (closed) and R2. Two same-day safety fixes from the code review — the writable mileage ledger (C1) and the scrape-lock wedge (M3) — plus the plan doc that gates R2.1, the security pass. No auth code this session (the plan comes first, by design). Three `r2:` commits, one per task. Suite 67 → 75.**

- **[CHANGED] Task 1 — C1: mileage ledger no longer writable via `PUT /owned-shoes/{id}`.** `OwnedShoeUpdate` exposed `current_mileage` (and `starting_mileage`) as writable fields applied through a blind `setattr` loop, so any client could set the counter to an arbitrary value — bypassing `rotation.log_run` and breaking INV-1 (`current_mileage = starting_mileage + Σ attributed distances`). The frontend used this deliberately (the ShoeDetail "Adjust mileage" dialog + an editable field on the edit form), making it an *undocumented invariant exception*. Fix: removed both fields from `OwnedShoeUpdate` (`starting_mileage` is now immutable post-create — the edit form already disabled it); added the sanctioned `rotation.adjust_mileage()` behind **`POST /owned-shoes/{id}/adjust-mileage`**, which records the override as a journal note (`triggered_by="mileage_adjustment"`) so a later COROS/Strava reconciliation can explain the drift — the third blessed exception to the single-write-path rule. Repointed the ShoeDetail adjust dialog to the new endpoint (`useAdjustMileage`); removed the redundant current-mileage field from `OwnedShoeForm` (mileage edits now go through the one dialog). **Verified:** 4 new tests in `tests/test_owned_shoes.py` (PUT drops `current_mileage`/`starting_mileage`; `adjust_mileage` sets the value + writes the note; missing-shoe raises). Updated `CLAUDE.md` §14 INV-1; struck C1 in `refactor.md` and P0-1 in `tech_debt.md`. *(refactor.md C1; domain_model §4.5/§4.6.)*
- **[CHANGED/ADDED] Task 2 — M3: scrape-lock wedge protection.** `scrape_runner.run_scrape_job` ran its setup block (shoe/retailer queries, promo detection) **before** the `try/finally` that releases the process-wide scrape lock, so a transient setup failure exited with the lock held — wedging every subsequent scrape (REST, MCP, background) at 409 until a process restart, with no UI explanation. Fix: the whole body now runs under the lock-releasing `finally`; `release_scrape_lock()` is tolerant of an unheld lock (no more `RuntimeError` on double-release). Added the operational escape hatch **`force_release_scrape_lock()`** behind **`POST /api/admin/scrape-lock/release`** (`{"was_held": bool}`) and a synchronous **`GET /api/scrape/status`** (`{"scrape_running": bool}`) for MCP/admin checks. Docstring on `lock.py` states the in-memory single-process constraint and the R4.1/D4 replacement requirement. *(The other lock sites — the REST `scrape_guard()` paths and MCP `trigger_scrape` — were verified already correct.)* The admin endpoint is **intentionally unauthenticated for now** (E1), and R2.1 gates it. **Verified:** 4 new tests in `tests/test_scrape_lock.py` (force-release false when unheld, true + released when held, tolerant double-release, status reflects the lock). Struck M3 in `refactor.md` / `tech_debt.md`. *(refactor.md M3; design_decisions D4.)*
- **[ADDED] Task 3 — `SECURITY_PASS_PLAN.md` (repo root) gates R2.1.** The session's main output. Covers: scope + the explicit **LAN threat model** (untrusted processes on the same network, not the internet) and non-goals — no multi-tenancy/OAuth/HTTPS/rate-limiting (§1); the full unauthenticated-surface inventory, including the **loopback self-connection** (`chat_service → MCP_SERVER_URL → this same `/mcp`) whose client must also send the token or Son of Anton silently loses its tools — dependency_graph §8.1 (§2); the chosen **single shared bearer token** (`ANTON_SECRET`) with alternatives rejected (§3); an ordered, one-commit-per-task implementation list — auth middleware, `127.0.0.1` default via the existing `API_HOST` env, SPA axios interceptor, loopback header injection at the existing `headers=` seam, `mcp-remote --header`, admin-endpoint gating, and the first `TestClient` HTTP-layer tests (§4); the breaking-change **rollout sequence** for Claude Desktop (§5); explicit scope boundaries (§6); and open questions to resolve first — browser token delivery, `mcp-remote --header` support, middleware-vs-mount ordering for `/mcp` (§7). No R2.1 code written — that is the next session.

- **[VERIFIED] Full suite green at 75** (67 → 75; +4 `test_owned_shoes.py`, +4 `test_scrape_lock.py`). `vite build` clean; the only UI changes are the mileage-edit consolidation in Task 1 (redundant form field removed, adjust dialog repointed to the new endpoint — behavior preserved). Freshness note: `models.py` is now 19,246 bytes (was 18,858 at the `ai_context.md` snapshot) from R1.4's `ShoeRun` WARNING comment — a comment, not a schema change.

---

## 🧹 R1 debt sweep + replacement-deals sizes — Phase 2 Session B — 2026-07-07

**[CHANGED] First implementation session after the documentation program. Closed out all remaining R1 loose ends (R1.3–R1.6): proxy-trap guards, four debt-sweep moves, the APScheduler decision, and the last missing field on the replacement-deals card. Seven `r1:` commits, one per task. Suite 64 → 67.**

- **[CHANGED] R1.4 — ShoeRun proxy traps guarded.** Every run-list seam that reads the `ShoeRun` property proxies (`distance_km`, `run_date`, `source`, `avg_pace`, `avg_hr`, `notes`, `coros_activity_id`) already joined `Activity` but never populated the relationship, so proxy access still fired a per-row lazy load (N+1). Added `.options(contains_eager(ShoeRun.activity))` to all five seams — the four `mcp_server.py` queries (`get_shoe_runs` tool, `draft_shoe_review`, shoe-detail resource, run-history resource) and the `owned_shoes` `/runs` endpoint. Added a `WARNING` comment on the model documenting the lazy-load + `.filter()` hazards. Audited: no surviving `.filter()` on proxied attributes. *(refactor.md H4 step one; tech_debt 5.3 note.)*
- **[CHANGED] R1.5a — Task D done.** `_attach_computed_fields` (owned-shoe response shaping: image match, lifetime stats, cost/km) moved from `routers/owned_shoes.py` to public `rotation.attach_computed_fields` — the last router→router import (`coros_sync` → `owned_shoes`) is gone. Six call sites + `coros_sync` repointed; the dead `CHECKPOINT_INTERVAL_KM` re-export dropped (the constant already lives in `rotation`). *(tech_debt 6.3.)*
- **[REMOVED] R1.5b — `scraper_manager.py` shim deleted.** The pure re-export shim's five consumers (`routers/scraping`, `routers/shoes`, `mcp_server`, `scrape_runner`, `scrapers/__init__`) now import `ScrapeOrchestrator` / `lock` / `registry` directly; the misleading `ScraperManager` alias is retired so the real boundaries are visible. **D7 → Superseded** (design_decisions); tech_debt 5.4/6.5 struck.
- **[ADDED] R1.5c — pure `app/utils/pace.py`.** `seconds_to_pace` / `pace_to_seconds` were implemented three times (rotation, coros_client, and inline in the `ShoeRun.avg_pace` proxy — a layer violation). Now one implementation in a dependency-free module; `rotation` re-exports both names (callers unaffected), coros_client and the model proxy import directly. Unified on `round()` (coros previously truncated with `int()`; its input is already integer seconds/km so behavior is unchanged). *(tech_debt 5.5 struck.)*
- **[CHANGED] R1.5d — chat model catalog single-sourced.** `routers/chat.py` hard-coded the catalog while `chat_service` routed by name prefix (`gpt-*`/`gemini-*`/else). New `chat_service.MODELS` (id, label, description, provider) + `PROVIDERS` metadata + `get_models()` is the one source; `_get_provider` resolves provider by id lookup (no prefix matching, unknown → Anthropic); `/providers` groups `get_models()` and layers on key availability — response shape verified identical. *(tech_debt 5.7 struck.)*
- **[REMOVED] R1.6 — APScheduler dropped.** Declared in `requirements.txt`, imported nowhere; removed. A scheduling note in `scrapers/lock.py` records that scheduled scraping (roadmap R4.1) needs DB-level coordination replacing the in-memory lock before a scheduler returns. Verified: uninstalled from the venv, suite still green, app imports clean. **E5 → Superseded**; tech_debt 1.7 struck.
- **[ADDED] R1.3 — replacement-deals card: size availability.** R1.3's substance (replacing the June "Coming soon" placeholder with a live section) already shipped in PR #9; only the size field the spec calls for was missing. Added `sizes_available` to `GET /owned-shoes/{id}/replacement-deals` and rendered it on `ReplacementDealCard` (guarded — shows only for a non-empty size list). New `test_replacement_deals.py` (3 tests) pins the endpoint's list projection: worst-discount-first, same-model / other-type / inactive / out-of-stock exclusions, the sizes field, and the untyped-shoe empty response.
- **Verified:** backend suite **67 passing** (was 64; +3 replacement-deals tests). `vite build` clean. No schema change — `sizes_available` was already a `Deal` column, so no migration. **Visual-pass caveat:** the interactive desktop/~380 px console pass for R1.3 was *not* run live — ports 8000/5173 were held by the user's own dev servers and the running backend predates the new field and hangs on the endpoint; the frontend change is additive, null-guarded, and build-verified. Recommend an eyeball on a typed shoe with matching in-stock deals when convenient.

---

## 🏁 Documentation completion — R1.1 committed, invariants, skills library, vocab table — 2026-07-06

**[DOCS] The documentation program is committed and its review backlog (§8 steps 2–4) is closed. No application code changed.**

- **[ADDED] R1.1 shipped:** the entire suite (`docs/`, `refactoring/`, `CLAUDE.md`, `documentation_creation.md`, the `claude.md → docs/changelog.md` rename) committed as `docs: complete Phase 1 documentation program`. Verified first: `backend/.gitignore` (`*.db`) + root `.gitignore` (`*.db.bak*`) exclude the live DB and all seven backups — no `.gitignore` change needed.
- **[ADDED] `CLAUDE.md` §14 — Invariants:** the checkable list (INV-1…INV-8), one line each: what must hold → owning code path → covering test (or an explicit "no test / documentation-only" note). Test claims verified against the suite first-hand (e.g. `test_delete_run_keeps_strava_archive` covers INV-4; the ledger round-trip covers INV-1). `ai_context.md` §8 repointed: a lead-in cites §14 as canonical and the five invariant items carry surgical `INV-n` citations — the third "don't break these" list the review warned about (§4.3) now cannot form.
- **[ADDED] `.claude/skills/` implemented — all 13 skill files** per `docs/skills_library.md`, in its specified order (S13 → S01 → S03/S04 → S05/S06/S07 → the rest). Six-section structure, ≤ ~120 lines each, cite-don't-restate. Addendum A4 honored: S07 carries the `sync_coros_runs` step list + external-contract summary with a "the prompt source wins" disclaimer. S05 points at the Retailer Status table's new home (architecture §10). S11 makes "exactly one uvicorn worker" explicit (review §5). One-line index added to `CLAUDE.md` §3.
- **[ADDED] `shoe_type` vocabulary table** (review Addendum A2, completing the reconciliation session's inline enumeration): Value/Meaning table in `domain_model.md` §4.3, marked as-of 2026-07-06 / canonical until R2.4; §7.1 glossary row repointed at it; one sentence added to `design_decisions.md` B3 naming where the list lives.
- **[CHANGED] Bookkeeping:** review §8 steps 2–4 struck with pointers here; roadmap R1.1 row marked done and moved to project_state §3; project_state refreshed (snapshot note, §1/§2/§3/§10, §11 re-ordered — R1.4 now first); ai_context §9 item 1 and §12 skills line updated to reflect committed/implemented state.
- **Noted, not re-done:** session-prompt Tasks 4 (two CLAUDE.md §6 trap lines) and 5 (roadmap "watched shoe") were already executed by the same-day reconciliation session — verified present/clean first-hand.
- **Verified:** no application code touched; suite expected unchanged at **64** (run recorded by the runner at commit time). Committed as `docs: documentation completion — invariants, skills library, vocab table`.

---

## 📚 Documentation program complete — final review + docs reconciliation — 2026-07-06

**[DOCS] All prompts of `documentation_creation.md` are done. The final review (`docs/documentation_review.md` + same-day addendum) audited the suite; this session executed its §8.1 reconciliation backlog. No code changed.**
- **MSRP ripple fixed** across the suite (the 2026-07-06 MSRP change had landed after most docs were written): `domain_model.md` §4.1 rewritten to the B9-v2 rule (`price < msrp`, savings vs MSRP, no-MSRP → no deal) with the old rule kept as a historical note; §2.1/§4.11/§7.1 glossary updated (new **msrp** entry; **target price** demoted); `architecture.md` §5 (shoes/deals rows), §6 qualification invariant, and the §12 pipeline diagram updated; `CLAUDE.md` §9 and `design_decisions.md` B13 now say "qualifying-savings snapshot (MSRP-based since B9-v2)".
- **refactor.md / tech_debt.md re-stamped** to the current tree (`models.py` 18,858 B · suite 64 · `d4e5f6a7b8c9`): rotation-path findings (C1/C2/H2/H3/H4) stand; **H1/P1-4 narrowed** (`test_deals.py` pins the MSRP rules; retirement/orphan/promo + HTTP layer still open); **L2 and tech_debt §9.5 struck** — resolved differently by the MSRP change; **§9.7 flipped** Verify → Resolved.
- **Changelog cleaned up (roadmap R1.2)**: header retitled to "Anton — Session Changelog"; the stale pre-Phase-5 reference tail (old schema with data-bearing `shoe_runs`, target_price deal semantics, retired `/scrape/test/*` endpoints) **amputated** and replaced with a pointer into `docs/` — after first **relocating the Retailer Status table to `architecture.md` §10** (it is S05's required context); the Project Commands table corrected to reality (only `/project:migrate` exists).
- **`claude.md` ghost sweep**: every remaining reference to the deleted root file (architecture §3 tree/§3 note/§14.8/§16.8–.9, design_decisions header/E3/Superseded table, strava_backfill row) now points at `docs/changelog.md` or `CLAUDE.md` as appropriate.
- **Count-drift fixes + anti-drift rule**: 61→64 tests and 4→5 migrations corrected everywhere; henceforth **live counts are authoritative in exactly two places** (this file's newest entry + `project_state.md` §2) and the **authoritative migration list lives only in `architecture.md` §5** — other docs cite, don't count. Backup files are no longer counted in prose ("dated `.bak*` restore points").
- **project_state.md refreshed** to 2026-07-06 (doc program complete; MSRP decision recorded in §3/§9; §7 now defers to tech_debt as ranked authority; §11 re-ordered). **ai_context.md §11 staleness register cleared.**
- **Addendum findings applied**: `shoe_type` vocabulary enumerated in `domain_model.md` §7.1 (8 values, as-of-dated, pending R2.4); two new CLAUDE.md §6 traps (`_effective_moving_s` private import; hand-matched router↔`api.js`/SSE string contracts); stray "watched shoe" → "tracked shoe" in roadmap R3.2.
- **Roadmap**: R1.2 marked done; R1.1 narrowed to "commit the batch." **Next: commit `docs/` + `refactoring/` + `CLAUDE.md` + `documentation_creation.md` as one batch (R1.1)** — until then all of this is one `git clean` from gone. Then the review backlog: INVARIANTS section in CLAUDE.md → skills implementation (S13 + S01 first).

---

## 🆕 MSRP drives deals — replace target_price in all deal math — 2026-07-06

**[CHANGED] A deal is now any retailer price *below the shoe's MSRP*; savings % is measured against MSRP. `target_price` is demoted to an optional personal threshold that no longer affects qualification or savings.**
- **Qualification** (`orchestrator.scrape_retailer_for_shoe`): the old rule (retailer marking down from
  its own compare-at price AND price ≤ target_price) is replaced by a single test — `price < shoe.msrp`.
  The retailer's compare-at/original price is no longer consulted. A shoe with no MSRP can't produce
  deals (nothing to measure against). "On sale" now means "below list price."
- **Savings math** (`deal_store.upsert_deal`): `savings_amount = msrp - price`,
  `savings_percent = (msrp - price)/msrp*100`. Refresh-on-rescrape now triggers on a scraped-price move
  OR a recomputed-savings change (i.e. an MSRP edit "sticks"). Returns `False` (no deal) when msrp unset.
- **Schema / migration** `d4e5f6a7b8c9_msrp_drives_deals`: `shoes.target_price` and `deals.target_price`
  relaxed to nullable (batch mode, reversible). `Deal.target_price` kept as a reference snapshot only.
  Backup `shoe_deals.db.bak-msrp-drives-deals` taken first.
- **One-off data recompute** on the live DB (backed up): existing active deals re-scored against MSRP;
  deals at/above MSRP (or with no MSRP) deactivated. Net: 113 → 112 active deals (only Alphafly 3 @ $375
  = MSRP fell out). Reconciled: 0 active deals remain with `price ≥ msrp`. Prior one-off populated MSRP
  on all 45 remaining active shoes so none is now un-dealable.
- **API/MCP**: `add_shoe` reordered to `(brand, model, msrp=None, target_price=None)` with MSRP documented
  as the deal driver; deal dicts (`_deal_to_dict`, dashboard) now surface `msrp`. Schemas made
  `target_price` optional (`ShoeBase`, `DealBase`, `WatchlistItem`). `export.py` seed-gen emits msrp and
  skips a null target.
- **Frontend**: `ShoeForm` makes MSRP the required, deal-driving field (hint "a sale is any price below
  this") and target optional; `PriceChart` gains a dashed **MSRP (sale below)** reference line;
  target-price displays null-guarded in `DealDetailModal`, `WatchlistRow` ("Set" when unset), and
  `Shoes` price-history subtitle (MSRP shown first).
- **Verified**: pytest **64 passing** (+3 new `test_deals.py` pinning MSRP savings, MSRP-edit refresh,
  and no-MSRP→no-deal); `vite build` clean; live-DB smoke of `/api/watchlist`, `/api/deals`, `/api/home`,
  `/api/dashboard/best-deals` all 200 with MSRP-based savings (e.g. $95 vs $190 MSRP → 50%).

---

## 🆕 Anton redesign Phase 5 — canonical `activities` table (§3 v2) — 2026-07-04

**[CHANGED] The two run stores collapsed into one canonical `activities` table; `shoe_runs` is now a pure attribution row.**
- New `Activity` model (`models.py`) — superset of the old `strava_activities` columns + a `source`
  discriminator (`strava`|`coros`|`manual`) + `coros_activity_id`. Every physical run (Strava export,
  COROS sync, manual log) is one Activity row. `StravaActivity` model + table **removed**.
- `ShoeRun` rewritten to attribution only: `{id, activity_id (FK, unique), owned_shoe_id, created_at}`.
  Read-only proxy properties (`distance_km`, `run_date`, `source`, `avg_pace`, `avg_hr`, `notes`,
  `coros_activity_id`) pull from the joined activity so `ShoeRunResponse` and every reader keep the
  **identical response shape** — no frontend/MCP consumer changes.
- Migration `alembic/versions/c3d4e5f6a7b8_canonical_activities.py` (reversible): migrates
  `strava_activities` → `activities` (source='strava'); linked `shoe_runs` become attribution for the
  matching strava activity (stamping its `coros_activity_id`); unlinked post-export runs mint fresh
  activities; rebuilds `shoe_runs`; drops `strava_activities`. Downgrade reconstitutes both old tables.
  **`current_mileage` counters untouched** — storage restructured, totals unchanged.
- Write path (`rotation.log_run`) now creates an Activity then the attribution row; `delete_run`
  removes the attribution + decrements mileage, deleting the activity too **except** source='strava'
  (frozen archive preserved). `coros.confirm_run`/`is_already_logged` dedup on
  `activities.coros_activity_id`. `activities._build` (the union seam) simplifies to one join — no more
  dedup-by-link. `strava_import` upserts into `activities`; `strava /status` + MCP readers repoint.
- **[REMOVED]** `strava_backfill.py` + its CLI + test — the two-store reconciliation it performed is
  exactly what this migration makes permanent (Strava export is frozen; no new cross-store dups).
- Verified on the live DB: pre/post reconciliation exact (698 runs · 8028.02 km · 667 attributed ·
  0 per-shoe mileage drift; 933 activities), `downgrade -1` round-trips clean, full suite **61 passed**
  (new `tests/test_activities_model.py`), `/training` + `/shoes/:id` + `/` render identical numbers,
  0 console errors. Clean pre-migration backup kept at `backend/shoe_deals.db.bak-pre-activities`.

---

## 🆕 Anton redesign Phase 5 — true app mark for Anton — 2026-07-04

**[ADDED] A real logo mark: a forward-leaning "A" monogram, replacing the placeholder diamond.**
- New `frontend/src/components/layout/BrandMark.jsx` — an italic "A" (apex shifted right of its
  base so the letter leans into a stride) with the crossbar drawn as a motion line that overshoots
  the right leg into a trail. Strokes use `currentColor`, so callers pick the colour.
- Wired into `Layout.jsx` `Brand` (green `bg-primary` tile, `text-background` strokes — same
  negative-space treatment as before, real glyph now) for both the desktop sidebar and mobile top
  bar. Legible at 28px.
- `public/favicon.svg` replaced (was a pulse-line) with the matching mark: green rounded tile +
  dark "A". `index.html` already points at it.
- Nav active/inactive **diamond dots left as-is** — they're a functional indicator motif, not the
  logo. Verified desktop + ~380px, `vite build` clean, 0 console errors.

---

## 🆕 Anton redesign Phase 5 — `/shoes` lifecycle reframe — 2026-07-04

**[ADDED] Retirement pipeline + group-by-type on `/shoes`; shared server-side pipeline computation.**
- New `rotation.retirement_pipeline(db, threshold=0.75)` + `rotation.active_deal_counts_by_type(db)`
  in `app/services/rotation.py` — the single authoritative "which active shoes are ≥75% of their
  `mileage_limit`, worst-first, and how many replacement deals exist" computation. Replacement deals
  are the heuristic §4 bridge: active deals on a tracked `Shoe` of the same `shoe_type` (no FK).
- **[REFACTORED]** `home._shoe_alerts` is now a thin projection over `retirement_pipeline` (dropped
  its duplicated query + local `ALERT_THRESHOLD`), so the Home shoe-alerts module and the Shoes page
  can never disagree about thresholds/ordering/counts.
- New thin endpoint `GET /api/owned-shoes/rotation-overview` → `{threshold, pipeline[]}` where each
  entry is `{owned_shoe_id, pct, current_mileage, mileage_limit, replacement_deals}`. Deliberately
  id-keyed/lightweight — the page already has full shoe rows from `GET /owned-shoes` and groups them
  by type client-side (trivial); the endpoint supplies only the server-computed pieces (API-first §2.1).
- Frontend (`pages/MyShoes.jsx`): active rotation now renders **grouped by shoe type** (groups ordered
  like the type filter, `Uncategorized` last; header = label · count · total km) with a **Retirement
  pipeline** band above it (`RetirementPipeline`/`PipelineRow`, worst-first, red/warning mileage bar,
  pct badge, "N replacement deals" button deep-linking to `/deals`; pipeline shoes still appear in
  their type group — the band is an attention surface, not a move). `useRotationOverview` hook +
  `ownedShoesApi.rotationOverview`. "Add a shoe" is now a full-width button below the groups.
- Tests: `tests/test_rotation_overview.py` (6) — threshold + boundary (exactly 75% included),
  worst-first ordering, replacement-deal counting (type-scoped, active-only, case-insensitive),
  untyped→0, empty pipeline. Full suite 69 passed. Desktop (grouped) + ~380px (stacked) pass, 0
  console errors.

---

## 🆕 Anton redesign Phase 4 — Home rebuilt as an attention surface — 2026-07-03

**[ADDED] `GET /api/home` + a rebuilt Home page (`/`) — four attention modules in one round trip.**
- New `app/services/home.py` (`home_summary(db, today)`) aggregates all four §4 modules; thin
  router `app/routers/home.py` (`GET /api/home`, ~110ms locally). API-first: every number computed
  server-side.
  - **Training pulse**: this-week vs last-week km (Monday-anchored, computed off the unioned run
    feed so an empty week reads 0), + newest run (distance, pace, HR, shoe, source).
  - **Shoe alerts**: active owned shoes at/over 75% of `mileage_limit`, worst-first, each with a
    replacement-deal count (active deals on a tracked `Shoe` of the same `shoe_type` — heuristic,
    no FK). Empty = "Rotation healthy" shown small + proud.
  - **Top deals**: 3 deepest active discounts, biggest savings % first.
  - **Activity strip**: last COROS sync (`app_settings.last_coros_sync_at`), last scrape
    (`max(retailers.last_scraped_at)`), newest active deal detected.
- Frontend: `pages/Home.jsx` (Dashboard convention — inline sub-components), `useHome` hook,
  `homeApi.summary`. Every module deep-links into its tab (`/training`, `/deals?deal=id`, `/shoes`).
- **[REMOVED]** old `pages/Dashboard.jsx` + `components/TrainingVolumeCard.jsx` (+ now-dead
  `useRecentDeals`/`useBestDeals` hooks). `useDashboardStats` kept — still used by Layout + Settings.
- Tests: `tests/test_home.py` (10) — week-over-week math, empty-week-reads-0, last-run selection,
  75% threshold + worst-first ordering + replacement-deal counting, top-deals ranking/cap, strip.
  Full suite 63 passed. Desktop (no-scroll) + ~380px passes clean, 0 console errors.

---

## Project Commands

Only one project command exists on disk: `/project:migrate` (run a DB migration — pattern + existing scripts). A former table here listed four others that were never written; their intent is absorbed by the skills library design (`docs/skills_library.md` — e.g. `add-retailer` → S05). Corrected 2026-07-06.

---

## 🆕 Shoe detail page, purchase price/cost-per-km, notes journal, mileage checkpoints — 2026-06-24

**[ADDED] A full `/my-shoes/:id` detail page, replacing the old quick-view dialog as the permanent home for run history.**
- New route `frontend/src/pages/ShoeDetail.jsx`. Card click target ("Details" button or the
  image/name header) now navigates here instead of opening a dialog; the old `ShoeDetailDialog`
  in `MyShoes.jsx` was removed entirely (run history moved into the new page, nothing duplicated).
- Layout: image/brand/model/nickname header with status badge and purchase-price line → stats row
  (mileage bar, total runs, lifetime avg pace/HR when present) → a **Replacement Deals** placeholder
  card (explicitly empty — "Coming soon" badge, no logic, just holding the layout slot for later) →
  **Shoe Notes Journal** → **Run History**.
- **[ADDED]** `purchase_price` (nullable float) on `owned_shoes` (migration
  `backend/migrate_add_shoe_notes.py`, same idempotent-`ALTER TABLE` pattern as prior owned_shoes
  migrations). Exposed in `OwnedShoeBase`/`Update` and as computed `cost_per_km` on
  `OwnedShoeResponse` (`purchase_price / current_mileage`, rounded 2dp, only when both are set) —
  computed server-side in `_attach_computed_fields` so the REST API, MCP tools, and frontend all
  show the identical number instead of each recomputing it. `OwnedShoeForm` gained a "Purchase
  price ($)" field.
- **[ADDED]** "Adjust mileage" action on the detail page — a small two-step dialog (enter value →
  explicit confirm showing old/new) that PUTs `current_mileage` directly via the existing
  `OwnedShoeUpdate` endpoint. Deliberately not a new endpoint — `current_mileage` was already
  updatable via `PUT /owned-shoes/{id}`; this just gives it dedicated UI with a confirmation step
  since it silently overrides accumulated run mileage rather than logging a run.

**[ADDED] Shoe Notes Journal — replaces the old single free-text `owned_shoes.notes` column.**
- New table `shoe_notes` (`id`, `owned_shoe_id`, `body`, `mileage_at_note`, `triggered_by`
  ["manual"|"checkpoint"], `created_at`) — a timestamped, mileage-anchored history instead of one
  overwritable text blob. `migrate_add_shoe_notes.py` migrates any existing `owned_shoes.notes`
  text into a `triggered_by="manual"` entry (mileage_at_note = current_mileage at migration time),
  then drops the old column. Ran live: 2 existing notes migrated cleanly.
- Endpoints (`routers/owned_shoes.py`): `GET/POST /api/owned-shoes/{id}/notes`,
  `DELETE /api/owned-shoes/notes/{note_id}`. `mileage_at_note` is always set server-side from the
  shoe's current mileage at write time — never client-supplied.
- MCP: `update_shoe_notes` removed (the column it wrote no longer exists); replaced by
  `get_shoe_notes(owned_shoe_id)` and `add_shoe_note(owned_shoe_id, body)`.
- Frontend: vertical timeline in `ShoeDetail.jsx` (date · mileage · checkpoint badge when
  applicable · body), "Add note" button, per-entry delete with confirmation, empty state.

**[ADDED] 100km mileage checkpoints prompt for a journal entry.**
- `POST /owned-shoes/{id}/log-run` now returns `LogRunResponse` (`run_logged`, `updated_mileage`,
  `checkpoint_reached`, `checkpoint_km`, `shoe`) instead of the bare shoe — a breaking response-
  shape change for that one endpoint. Checkpoint crossing is `floor(new_mileage/100) >
  floor(old_mileage/100)`, e.g. 290.06km + 10km run → checkpoint_km=300.
- New shared `frontend/src/components/LogRunDialog.jsx` — logs the run, and if `checkpoint_reached`
  is true and this checkpoint hasn't been prompted before, swaps to a "Your [shoe] just hit Xkm —
  add a note?" view. "Already prompted" is tracked client-side only
  (`frontend/src/lib/checkpoints.js`, localStorage keyed by shoe id + checkpoint km).

---

## 🆕 Run pace/HR, lifetime averages, run deletion — 2026-06-24

**[ADDED] avg_pace/avg_hr wired through properly, lifetime stats, and the ability to remove a logged run.**
- `log_run_to_shoe` (MCP) gained `avg_pace`/`avg_hr` params. New computed fields on
  `OwnedShoeResponse`: `lifetime_avg_pace`, `lifetime_avg_hr`, `total_runs`. Pace strings are
  averaged correctly — converted to seconds, averaged, formatted back (`_pace_to_seconds` /
  `_seconds_to_pace` in `routers/owned_shoes.py`). Computed by `_attach_computed_fields`, called
  from every owned_shoes endpoint that returns a shoe.
- **[ADDED]** `DELETE /api/owned-shoes/runs/{run_id}` — deletes the run and subtracts its
  `distance_km` back out of the parent shoe's `current_mileage` (floored at 0), returns the
  updated shoe. New MCP tool `delete_shoe_run(run_id)` mirrors it. Frontend: Trash icon per row
  with confirmation dialog. `useDeleteShoeRun` optimistically patches the cache in `onMutate`.

---

## 🆕 My Shoes UI polish — 2026-06-24

**[ADDED] Search, active/retired split, compact mileage text, and product images on owned shoe cards.**
- Renamed "Shoes" nav tab to **"Tracked Shoes"** to disambiguate from "My Shoes".
- My Shoes page has a client-side search bar and splits cards into **Active** and **Retired** sections.
- **Images on owned shoe cards**: priority is manual `image_url` (new nullable column on
  `owned_shoes`, migration `backend/migrate_add_owned_shoe_image.py`) → best-effort
  `matched_image_url` (heuristic join against `price_records.image_url` by brand/model substring)
  → placeholder. Never a broken `<img>`.

---

## 🆕 "My Shoes" personal rotation tracker — 2026-06-24

**[ADDED] Track owned shoes (mileage, notes, run history) — separate from deal tracking.**
- New tables `owned_shoes` + `shoe_runs` (`models.py`), created automatically by `init_db()`.
  Deliberately **not** the same table as `Shoe` (deal tracking).
- Backend: `app/routers/owned_shoes.py` — full CRUD + `POST /{id}/log-run` + `GET /{id}/runs`.
  `shoe_runs.source` is `"manual"` for now; `"coros"` is reserved for future COROS sync.
- MCP: 5 tools — `get_owned_shoes`, `get_shoe_runs`, `log_run_to_shoe`, `add_shoe_note`,
  `get_shoe_notes`, `delete_shoe_run`, `retire_shoe`.
- Frontend: `pages/MyShoes.jsx`, `OwnedShoeForm.jsx`, `LogRunDialog.jsx`,
  `MileageProgressBar.jsx` (green <500km / yellow 500–800km / red >800km).

---

## 🆕 Sporting Life investigated — blocked by Cloudflare — 2026-06-22

**[BLOCKED]** Sits behind a Cloudflare managed JS challenge — 403s plain requests AND headless
Playwright. Would need a paid proxy/unblocking service (ScraperAPI, Bright Data). Not added.

---

## 🆕 New retailer — En Route Run — 2026-06-22

**[ADDED] `EnRouteRunScraper`** (`app/scrapers/enroute_run.py`).
- Shopify-backed but headless Astro storefront — `/products.json`, `/products/<handle>.js`,
  `/search/suggest.json` all 404. Bespoke scraper parses inline Astro/Qwik hydration JSON
  (`_parse_variant_blocks()` unescapes HTML-entity-encoded variant data).
- Verified: Adidas Adizero Adios Pro 4 — genuine markdowns found end-to-end.

---

## 🆕 Phase 5 — 2026-06-18 (images, colorway consolidation, +3 retailers)

**Task 2 — Product images + colorway.**
- New nullable columns `image_url` + `colorway` on `price_records` and `deals`
  (migration `backend/migrate_add_images.py`).
- Algolia scrapers: image from S3 CDN URL, colorway from `thumbnails[].color_name`.
- Shopify scrapers: `image`/`featured_image`, protocol-relative normalized to `https:`,
  colorway from the Color option.

**Task 3 — Colorway consolidation UI.**
- `Deals.jsx` groups active deals by `shoe_id` — one card per model.
- `ShoeProductCard.jsx` + `ColorwaySelector.jsx` (thumbnail gallery switching active colorway).

**Task 1 — Automatic Algolia credential rediscovery.**
- `base_scraper.discover_algolia_credentials()` drives the site's own search with headless
  Playwright, intercepts `*.algolia.net` XHR to recover app id/key/index.
- `algolia_scraper._algolia_query` detects 401/403, rediscovers once per session, caches creds.

**Task 4 — +3 Shopify retailers.** Boutique Endurance, Le Coureur, BlackToe Running added.

---

*Reference material moved to `docs/` — see `docs/architecture.md` (the Retailer Status table now lives in its §10). Stale pre-Phase-5 overview sections were removed here 2026-07-06 (R1.2); session changelog entries above are untouched and remain the authoritative history. New session entries go at the top.*
