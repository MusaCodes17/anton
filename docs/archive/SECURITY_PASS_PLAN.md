# SECURITY_PASS_PLAN.md — Anton R2.1

**Status:** Plan only. This document *gates* roadmap **R2.1**. No auth code is
written until this plan exists and has been read at the start of the R2.1
session. Written 2026-07-07 (Phase 2 Session C) alongside the C1/M3 safety fixes.

**Related:** `docs/roadmap.md` R2.1 · `docs/design_decisions.md` **E1** (the
no-auth decision and its stated repair) · `docs/architecture.md` §11/§15.1/§16.1
· `docs/dependency_graph.md` §8.1 (loopback) / §8.10 (env-as-wiring) ·
`refactoring/refactor.md` **C2** · `CLAUDE.md` §4.6 (graceful degradation),
§14 (invariants). This plan supersedes the loose "security pass: API auth, rate
limiting, MCP endpoint auth" backlog line with an ordered, executable task list.

---

## 1. Scope and non-goals

R2.1 converts Anton's trust model from a **network property** ("only things
that can reach port 8000 can mutate data") into an **application property**
("only requests carrying the shared secret can mutate data"). It is the
acknowledged precondition for every exposure-increasing feature after it —
unattended agents (R3), scheduled scraping trigger surfaces (R4), mobile
(R5.1), remote access (R5.2). Nothing unattended and nothing off-machine
proceeds until this ships.

### Threat model (explicit)

The adversary R2.1 defends against is **an untrusted process or person on the
same LAN** — a housemate's laptop, a guest on the WiFi, a compromised IoT
device, a curious script sweeping `192.168.x.x:8000`. It is **not** the public
internet (Anton is never bound to a public interface in this plan) and **not** a
malicious local root user (who can read `.env` anyway). The concrete harms being
closed:

- Anyone reaching the port can **mutate the training/deals database** (delete
  runs, retire shoes, edit the watchlist) with no credential.
- Anyone reaching the port can **spend the owner's paid LLM credits** via
  `POST /api/chat/message`, and drive an **arbitrary-URI proxy** via
  `POST /api/chat/resource/read`.
- Anyone reaching `/mcp` can **call every write tool** (log runs, trigger
  scrapes, adjust data).

### Non-goals (deliberately out of scope for R2.1)

- **No multi-tenancy, no user accounts, no roles.** Anton is single-user (A1);
  one shared secret is the whole model.
- **No OAuth, no session cookies, no login UI.** A bearer token has zero UX for
  one user (see §3).
- **No HTTPS/TLS termination.** That is a network-layer concern handled by the
  remote-access story (R5.2, e.g. a Tailscale overlay), not the app. On a
  trusted LAN the token travels in cleartext; that is an accepted limit of this
  threat model and is documented as such.
- **No rate limiting.** Basic rate limiting on `POST /api/chat/message` is a
  *separate* R2 item; R2.1's job is authentication, not throttling (see §6).
- **No secret rotation UX, no per-client keys, no key management.** One secret,
  set once in `.env` (see §7).

R2.1's job is exactly **"no anonymous mutations, no anonymous LLM spend."**
Nothing more.

---

## 2. Current exposure inventory

Every surface below is **currently unauthenticated** and bound to
`0.0.0.0:8000` by default. Derived from `docs/architecture.md` §11,
`docs/dependency_graph.md` §8, and a line-level read on 2026-07-07.

| # | Surface | What it exposes | Notes |
|---|---|---|---|
| 1 | **17 REST router families under `/api`** | Full CRUD on shoes, owned-shoes, deals, watchlist, races, activities, notes, retailers, promos, export, admin | Includes destructive `DELETE`s and the new `POST /api/admin/scrape-lock/release` (M3, this session) |
| 2 | **`POST /api/chat/message`** | Unauthenticated proxy that spends the server's paid Anthropic/OpenAI/Gemini keys | The single highest-value target — it costs the owner money per call |
| 3 | **`POST /api/chat/resource/read`** | Arbitrary-URI proxy into the MCP resource layer | A second door on the same wall (refactor.md C2) |
| 4 | **`GET /api/chat/providers` / `/resources`** | Enumerates configured providers and resources | Low harm, but leaks config |
| 5 | **`/mcp` (FastMCP, Streamable HTTP)** | ~20 MCP tools; **write tools mutate the DB** (`log_run_to_shoe`, `trigger_scrape`, confirmations) | Reached by Claude Desktop via `mcp-remote`; must stay reachable post-auth |
| 6 | **Default `0.0.0.0:8000` bind** (`run.py`, env `API_HOST`) | Makes "localhost-only" a property of the network, not the app | `API_HOST` env already exists — the default is the problem |
| 7 | **CORS: `allow_credentials=True` + `allow_methods=["*"]` + `allow_headers=["*"]`** (`main.py`) | Broader than the app needs | Tighten in the same pass |
| 8 | **The loopback self-connection** (`chat_service.MCP_SERVERS → MCP_SERVER_URL → this same process's `/mcp`) | Son of Anton is itself an MCP *client* of Anton | **The subtlest item.** Once `/mcp` requires the token, this client must send it too, or Son of Anton silently degrades to "No tools available" (dependency_graph §8.1). The good news: `chat_service` already passes `headers=server.get("headers")` per server (chat_service.py ~L474) — there is a clean injection point. |

Currently exempt-worthy endpoints that already exist: `GET /` (root banner) and
`GET /health` (liveness, returns `{"status": "healthy"}`). These must remain
reachable without the token (§4 task 2).

---

## 3. Chosen mechanism — a single shared bearer token

**Decision:** one random secret in `.env` as `ANTON_SECRET`; every request to
`/api/*` (except a tiny public allowlist) and `/mcp` must carry
`Authorization: Bearer <ANTON_SECRET>`; a mismatch or absence returns **401**
with no body.

### Why this is the right choice for Anton

- **Zero UX friction for one user.** No login screen, no token refresh, no
  account. The secret is set once and forgotten.
- **Works uniformly across all three consumers:**
  - **SPA** → the existing single axios client adds one `Authorization` header
    in its request interceptor (§4 task 4).
  - **Claude Desktop** → `mcp-remote` already supports a `--header` argument
    (§4 task 6); one-time config change.
  - **Loopback (Son of Anton)** → inject the header into the existing
    `MCP_SERVERS` entry (`headers={"Authorization": ...}`), which
    `chat_service` already forwards to `StreamableHttpParameters` (§4 task 5).
- **Symmetric secret = trivial verification.** No asymmetric crypto, no cert
  lifecycle, no JWT parsing/expiry. A constant-time string compare in one
  middleware.

### Alternatives considered and rejected

| Alternative | Why rejected for R2.1 |
|---|---|
| **API-key-per-client** (separate keys for SPA / Desktop / loopback) | Key-management overhead for a single user with no revocation needs; three secrets to keep in sync instead of one. Revisit only if remote third-party clients appear (R5.2). |
| **Session cookies + login** | Adds a login flow, CSRF surface, and cookie handling to a stateless-per-request SPA — real complexity for zero benefit at single-user scale. |
| **mTLS / client certificates** | Correct for a hostile network, but overkill on a trusted LAN and a cert lifecycle burden. The LAN-trust assumption (§1) makes it unwarranted. |
| **OAuth / OIDC** | An identity system for a system with exactly one identity. |
| **Reverse-proxy basic-auth only** (no app change) | Leaves `/mcp` and the loopback unsolved, and couples security to deployment topology Anton doesn't control. The app should own its own trust boundary (seams-over-topology). |

---

## 4. Implementation plan (the ordered R2.1 task list)

Each task is one commit, `r2:` prefixed, suite green at each. Execute in order —
later tasks assume earlier ones. **Do the loopback (task 5) and the SPA (task 4)
before the smoke test (task 9), and read the rollout sequence in §5 before
enabling enforcement against a running Claude Desktop.**

1. **Add `ANTON_SECRET` to `.env.example`** with generation instructions:
   `python -c "import secrets; print(secrets.token_hex(32))"`. Document that it
   must be set before the server starts (see task 3's fail-fast).

2. **FastAPI auth middleware** verifying `Authorization: Bearer <ANTON_SECRET>`
   on every request, using a constant-time compare (`secrets.compare_digest`).
   - **Public allowlist (no token):** `GET /` and `GET /health` (existing
     liveness). Optionally add `GET /api/health` as a stable API-namespaced
     liveness alias and exempt it too.
   - **Covered:** everything else under `/api/*` **and** `/mcp` (the mount is a
     sub-app; verify the middleware runs before the mount dispatch, or apply an
     equivalent check inside the MCP layer — test both surfaces in task 8).
   - **On failure:** return `401` with an **empty body** (don't leak whether the
     path exists or why auth failed). Do not log the presented token.
   - Preserve CORS preflight: `OPTIONS` requests must not require the token, or
     the browser preflight breaks.

3. **Fail-fast on missing secret.** At startup, if `ANTON_SECRET` is unset or
   empty, the app **refuses to boot** with a clear error — never silently serve
   unauthenticated. (Contrast with the graceful-degradation pattern for optional
   creds in CLAUDE.md §4.6: auth is *not* optional, so absence is fatal, not a
   disabled feature.)

4. **Change the default bind to `127.0.0.1`** in `run.py`. The `API_HOST` env
   var already exists (default currently `0.0.0.0`); flip the default to
   `127.0.0.1` and keep `API_HOST` as the **explicit LAN opt-in** (set
   `API_HOST=0.0.0.0` to serve the LAN — now safe because the token is
   required). Document the opt-in in `.env.example`. *(This is the "loopback
   bind default is part of E1's repair" note from design_decisions E1.)*

5. **Update the SPA axios client** (`frontend/src/services/api.js`): add the
   token to every request via the existing interceptor. See §7 for how the
   browser obtains the token — resolve that open question first, then implement
   the chosen path here. Also tighten CORS in `main.py` (drop the wildcard
   methods/headers to the actual set the SPA uses; keep `allow_credentials` only
   if the chosen token-delivery path needs it).

6. **Inject the token into the loopback MCP client** (`chat_service.py`
   `MCP_SERVERS`): add
   `"headers": {"Authorization": f"Bearer {os.getenv('ANTON_SECRET','')}"}` to
   the `anton` server entry. `chat_service` already forwards
   `headers=server.get("headers")` into `StreamableHttpParameters`, so this is
   the whole change — but it is the one most likely to be forgotten and the one
   whose failure is **silent** (Son of Anton just loses its tools). Verify in
   task 9 that chat still discovers tools.

7. **Update the `mcp-remote` config in Claude Desktop** to pass the token via
   `--header "Authorization: Bearer <ANTON_SECRET>"`. This is a one-time manual
   step on the Desktop side and a **breaking change** the moment enforcement is
   on (see §5). Verify `mcp-remote`'s installed version supports `--header`
   *before* the session (§7 open question).

8. **Gate the admin force-release endpoint** (`POST /api/admin/scrape-lock/release`,
   added this session for M3) — it is covered automatically once task 2's
   middleware is in place; this task is the explicit *verification* that the
   admin surface is behind the token, and the moment to remove the "intentionally
   unauthenticated for now (E1)" note from its docstring.

9. **Tests** (land with the code, per CLAUDE.md §10):
   - An unauthenticated request to a mutation endpoint (e.g.
     `PUT /api/owned-shoes/{id}`, `POST /api/chat/message`) returns **401**.
   - The same request **with** the correct bearer token succeeds.
   - A request with a **wrong** token returns 401.
   - `GET /health` (and `/api/health` if added) returns **200 without** a token.
   - This is also the natural moment to add the **first `TestClient` HTTP-layer
     tests** the suite currently lacks (refactor.md H1) — the auth middleware is
     only testable through the real routing stack.

10. **Smoke test** (manual, recorded in the changelog — this is a config-shaped
    change tests can't fully cover):
    - Claude Desktop sync still works (after task 7's config update).
    - Son of Anton chat still discovers tools and answers (loopback token OK).
    - SPA deals/shoes pages load and a mutation (log a run) succeeds.
    - A scrape can be triggered and the SSE stream still flows.
    - An un-tokened `curl` to a mutation endpoint gets 401.

---

## 5. Rollout notes

**This is a breaking change for Claude Desktop.** The exact safe sequence:

1. **Set `ANTON_SECRET` in `.env`** (generate per §4 task 1).
2. **Update the Claude Desktop `mcp-remote` config** to send
   `--header "Authorization: Bearer <the same secret>"` — *before* restarting
   the server. If the server restarts with enforcement on while Desktop still
   sends no header, Desktop sync breaks immediately.
3. **Restart the server** (enforcement now live; app fails fast if the secret is
   unset — §4 task 3).
4. **Verify** in order: `GET /health` 200 without token → SPA loads → Son of
   Anton lists tools → Claude Desktop sync → one mutation.

Other rollout facts:

- The SPA build must ship the token (or fetch it) per §7 — a stale build with no
  token will 401 on every call. Rebuild/redeploy the frontend as part of rollout.
- **Existing `.bak` DB files and the live DB are unaffected** — auth is purely a
  transport-layer gate; no schema change, no migration, no data movement (so the
  E4 migration ceremony does **not** apply to R2.1).
- If anything breaks mid-rollout, the escape hatch is `API_HOST=127.0.0.1` +
  temporarily unsetting enforcement — but prefer fixing the header on the
  failing client to disabling auth.

---

## 6. What R2.1 does NOT fix (scope boundaries restated)

Be explicit so a later session doesn't assume these rode along:

- **Rate limiting on `POST /api/chat/message`** — a *separate* R2 item. R2.1
  stops *anonymous* LLM spend; it does not stop an authenticated client from
  looping. Throttling is its own change.
- **HTTPS / TLS** — network layer, handled by the remote-access story (R5.2).
  On the trusted LAN the token is cleartext by accepted design (§1).
- **The in-memory scrape-lock single-process assumption** — unchanged; DB-level
  coordination is R4.1's problem (design_decisions D4; and see this session's
  `lock.py` docstring).
- **Server-side conversation/memory persistence** — still localStorage until
  R2.6 (design_decisions C8). R2.6 explicitly *depends* on R2.1 (chat endpoints
  stop being anonymous first).
- **Secret rotation, per-client keys, revocation** — one static secret; revisit
  only when remote/third-party clients appear (R5.2).

R2.1's job is exactly **"no anonymous mutations, no anonymous LLM spend."**

---

## 7. Open questions (resolve before the R2.1 session starts)

1. **How does the browser obtain the token?** Two viable paths for a local
   single-user app; pick one and record the decision at the top of the R2.1
   session:
   - **(a) Build-time env var** (`VITE_ANTON_SECRET` in `.env`, read by
     `api.js`). Simplest; the secret lands in the built JS bundle's baked-in
     env. Acceptable because the bundle is served only to the trusted single
     user on the trusted machine — anyone who can read the bundle could read
     `.env` anyway. **Recommended default** for simplicity.
   - **(b) A pre-auth `GET /api/config` (or `/api/session-token`) endpoint** that
     returns the token *only to loopback callers* (checks the client is
     `127.0.0.1`), which the SPA fetches once at startup and holds in memory.
     Keeps the secret out of the static bundle, at the cost of one exempt
     endpoint that must itself be correctly restricted.
   - There is no wrong answer at single-user local scale; **(a)** unless a
     concrete reason for **(b)** emerges. Whichever is chosen, the CORS
     `allow_credentials` decision in §4 task 5 follows from it.

2. **Does the installed `mcp-remote` support `--header`?** Verify the version in
   the current Claude Desktop config *before* the R2.1 session. If it doesn't,
   identify the upgrade path (or an alternative header-injection mechanism) as a
   pre-req — otherwise Desktop sync cannot be re-authenticated and the rollout
   (§5 step 2) stalls.

3. **Should the token be rotatable without rebuilding/restarting the SPA?**
   (i.e. stored in localStorage and refreshable.) **Decision: no** for a local
   single-user app — rotation means editing `.env` and restarting, which is
   acceptable at this scale and avoids a token-management surface. Revisit only
   if/when remote access (R5.2) introduces real rotation needs.

4. **Middleware vs. mount ordering for `/mcp`.** Confirm during implementation
   whether a top-level FastAPI middleware intercepts requests to the mounted
   `mcp.streamable_http_app()` sub-app before its internal dispatch. If it does
   not, apply an equivalent bearer check at the MCP layer. Task 8's tests must
   assert `/mcp` actually rejects an un-tokened request — do not assume the
   middleware covers the mount.

---

*Maintenance note: this is a forward-looking execution plan, not a running log.
When R2.1 ships, record what actually happened in `docs/changelog.md` and move
E1 from ⚠️ to Superseded in `docs/design_decisions.md`; leave this file as the
historical plan (append-only, like REDESIGN_PLAN.md) rather than rewriting it to
match the outcome.*

---

## 8. Addendum — §7 open questions resolved (Phase 2 Session D — 2026-07-07)

*Appended at the start of the R2.1 implementation session, per the §7 instruction
to "pick one and record the decision at the top of the R2.1 session." The §7 text
above is left intact as the historical framing; this section is the binding
resolution. Verified first-hand against the installed tooling on 2026-07-07.*

### Q1 — How does the browser obtain the token? → **(a) build-time `VITE_ANTON_SECRET`**

The SPA reads the token from `import.meta.env.VITE_ANTON_SECRET`, set in the same
`.env` mechanism as `ANTON_SECRET`. Rationale exactly as §7(a): the bundle is
served only to the trusted single user on the trusted machine, and anyone who can
read the built JS can read `.env` anyway, so baking the secret into the bundle
adds no attack surface under the LAN threat model (§1).

The `/api/config` pre-auth endpoint (§7(b)) is **rejected**: it is complexity with
no security gain here — it trades one baked-in secret for one more exempt endpoint
that must itself be correctly IP-restricted, i.e. a *new* thing to get wrong, for
a threat model where the secret's confidentiality on this machine isn't the
concern. CORS follow-through (§4 task 5): the token rides an `Authorization`
request header, not a cookie, so `allow_credentials` is **not** required for the
token itself; the CORS tightening is done independently on its own merits.

### Q2 — Does the installed `mcp-remote` support `--header`? → **Yes (0.1.38), no upgrade needed**

Verified against the resolved package source (`mcp-remote@0.1.38`,
`dist/chunk-65X3S4HB.js`): `parseCommandLineArgs` consumes `--header "<Name>: <Value>"`
pairs (line ~20711), matching `^([A-Za-z0-9_-]+):\s*(.*)$` — so
`--header "Authorization: Bearer <token>"` parses to header name `Authorization`,
value `Bearer <token>`. It additionally supports `${ENV_VAR}` substitution inside
the value (line ~20851), but we use the **literal token** in the Desktop config for
determinism (Claude Desktop's launch environment does not reliably inherit the
shell's `.env`). No version bump required; the current Desktop config uses an
unpinned `npx mcp-remote`, which already resolves to a `--header`-capable version.

- *Orthogonal caveat (not a blocker for R2.1):* this shell's Node is v19.4.0, on
  which `npx mcp-remote` crashes at startup (`ReferenceError: File is not defined`,
  an undici incompatibility). This is a **local-shell** issue, independent of
  `--header` support and of Claude Desktop (which launches `mcp-remote` under its
  own Node and works today). If Desktop sync ever fails post-rollout with that
  error, the fix is a newer Node for Desktop's `npx`, not an auth change.

### Q3 — Should the token be rotatable without restarting the SPA? → **No**

One static secret; rotation is a deliberate, infrequent, multi-step operation, not
a hot path. **Rotation procedure (documented here so a later session doesn't build
hot-rotation by reflex):**

1. Generate a new value: `python -c "import secrets; print(secrets.token_hex(32))"`.
2. Set it as **both** `ANTON_SECRET` and `VITE_ANTON_SECRET` in `backend/.env` (and
   `frontend/.env`), then update the Claude Desktop `mcp-remote` `--header` to the
   same value.
3. Restart the backend (fail-fast re-reads the secret) and rebuild / hard-reload
   the SPA so the new value is baked into the served bundle.

No localStorage token store, no refresh endpoint, no per-client keys. Revisit only
if remote/third-party clients appear (R5.2), where revocation becomes a real need.

### Q4 — Middleware vs. mount ordering for `/mcp` (resolved during implementation)

A top-level Starlette middleware added with `app.add_middleware(...)` wraps the
**entire** ASGI app, including the `app.mount("/mcp", ...)` sub-app, because the
middleware stack sits outside the router that dispatches to mounts. So the one
bearer check covers `/api/*` and `/mcp` uniformly. This is **asserted, not
assumed**: `tests/test_auth.py` sends an un-tokened request to `/mcp` and requires
a 401 (task 8). If that assertion ever regresses, the fallback is an equivalent
check inside the MCP layer.
