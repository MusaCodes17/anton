# Claude ↔ Anton MCP setup

Anton's MCP server (`/mcp`) supports two clients, each with its own auth
mechanism — both live side by side and are independently revocable.

| Client | Auth | Where it runs |
|---|---|---|
| **Claude Desktop** | Named bearer token (`desktop:` entry in `ANTON_TOKENS`) | Your machine, via `mcp-remote` |
| **claude.ai connector** (web + mobile) | OAuth 2.1 + PKCE (public client, RA1.1c) | Anthropic's cloud — this is why the endpoint must be public HTTPS |

Both reach the same `https://anton.musasouled.com/mcp` — there is no separate
capability-URL scheme (that RA1.1 fallback was deleted in RA1.1b once OAuth was
confirmed to work; if you see `<CONNECTOR_TOKEN>` or a token-in-the-path
referenced anywhere, it's stale documentation).

---

## Claude Desktop (named bearer token)

Claude Desktop reaches `/mcp` through
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote), a stdio↔HTTP bridge
launched via `npx`, sending the `desktop` token from `ANTON_TOKENS` as a
bearer header.

**Config file** — macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```jsonc
{
  "mcpServers": {
    "anton": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://anton.musasouled.com/mcp/",
        "--header",
        "Authorization: Bearer <DESKTOP_TOKEN>"
      ]
    }
  }
}
```

Replace `<DESKTOP_TOKEN>` with the `desktop` value from `ANTON_TOKENS` in the
**server's** `backend/.env` (the source of truth — never the laptop `.env`).
Fully quit and reopen Claude Desktop after editing (it only reads this file at
launch).

### Notes
- **Use the literal token, not `${ENV}`.** `mcp-remote` supports `${ENV}`
  substitution, but Claude Desktop's launch environment doesn't reliably
  inherit your shell's `.env`, so a literal value is deterministic.
- **Node version.** `mcp-remote` needs a reasonably recent Node. `ReferenceError:
  File is not defined` on Desktop sync means "upgrade Node," not an auth problem.

### Rotating the Desktop token
Edit `backend/.env` on the server → change the `desktop:` entry in
`ANTON_TOKENS` → `docker compose restart` → update the `--header` value here →
restart Claude Desktop. The `loopback` token (Son of Anton's internal client)
is unaffected.

---

## claude.ai connector (web + mobile — OAuth 2.1)

The claude.ai connector — used for both browser and phone — calls Anton from
**Anthropic's cloud infrastructure**, not from your device. This is why the
MCP endpoint has to be a real public HTTPS URL; a home/Tailscale-only setup
cannot satisfy this client.

### Server-side prerequisites (`backend/.env`)

```bash
ANTON_HOST_URL=https://anton.musasouled.com   # the OAuth issuer URL; also gates
                                               # whether the OAuth routes exist at all
ANTON_OAUTH_CLIENT_ID=claude-ai-connector
ANTON_OAUTH_REDIRECT_URI=https://claude.ai/api/mcp/auth_callback
ANTON_OAUTH_CLIENT_SECRET=                    # leave BLANK — public PKCE client (RA1.1c)
ANTON_LOGIN_PASSWORD=<your password>          # gates BOTH this OAuth login page
                                               # and the SPA session login (RA2.1)
```

`ANTON_OAUTH_CLIENT_SECRET` must be blank. As of RA1.1c, Anton is a proper
**public PKCE client** — no shared secret to keep in sync between the server
and the connector form, which is both simpler to operate and the correct
long-term posture for a personal single-user connector (PKCE, not a static
secret, is what actually protects the token exchange). If you see
`unauthorized_client — Unsupported auth method: None` at `/token`, the fix is
already shipped (RA1.1c) — confirm the server is on that build.

### Adding the connector (claude.ai → Settings → Connectors → Add custom connector)

Do this **on web**, not in the mobile app — the mobile connector list has no
"add custom" affordance; connectors configured on web sync down to mobile
automatically.

1. Name: `Anton`. URL: `https://anton.musasouled.com/mcp` (no trailing slash).
2. Advanced settings → Client ID: `claude-ai-connector`. Leave the secret field
   **blank**.
3. Click **Add**, then **Connect** → you'll be redirected to the
   `ANTON_LOGIN_PASSWORD` page → on success, redirected back to claude.ai,
   connected.
4. Confirm tools load in a **fresh** chat (tool lists bind at conversation
   start — a chat opened before connecting won't retroactively see them).

### If it fails
- **"Authorization … failed" after entering the password:** almost always a
  server-side issue that leaves a trace in `docker compose logs anton` and in
  Caddy's access log (`/var/log/caddy/access.log`) — two real bugs were found
  and fixed this way during RA1.5 setup (see below). Re-adding the connector
  fresh (delete, then re-add) after any server-side auth change is often
  necessary — a stale connector caches client state from before the fix.
- **`unauthorized_client` at `/token`:** confirm `ANTON_OAUTH_CLIENT_SECRET` is
  blank on the server AND the connector's secret field is blank — a mismatch
  either direction fails the exchange.
- **Connects, but shows "no tools" in chat:** check the per-chat tools/connector
  toggle in the composer, and start a genuinely new conversation.

### Known past failure modes (fixed — kept here so they're not re-diagnosed from scratch)
Three distinct bugs blocked the connector during initial RA1.5 setup, in order:
1. **Missing RFC 9728 discovery.** Anton didn't serve
   `/.well-known/oauth-protected-resource` (the metadata the connector fetches
   *first*), so the request fell through Caddy's static handler to the SPA and
   returned HTML → generic "internal server error." Fixed: `routers/oauth.py`
   now serves it; the path is public (`PUBLIC_PATHS`) and routed to the backend
   in the Caddyfile `@backend` matcher.
2. **Public-client rejection.** `unauthorized_client — Unsupported auth method:
   None` — fixed by RA1.1c (see `design_decisions.md` E9 addendum).
3. **HTTPS→HTTP downgrade redirect.** Every `/mcp` call 307'd to
   `http://…/mcp/` (not https) because Uvicorn wasn't told to trust Caddy's
   `X-Forwarded-Proto` header — OAuth-aware clients refuse to follow a TLS
   downgrade. Fixed: `--proxy-headers --forwarded-allow-ips="*"` on the Uvicorn
   launch in `entrypoint.sh` (safe because Uvicorn only ever receives traffic
   from Caddy over the container-internal network).

Diagnostic pattern that worked for all three: `curl` the specific hop directly
(discovery endpoint, `/token` with a dummy code, or `-I` on `/mcp` to see the
redirect `Location`) rather than trusting the connector's generic error text,
which doesn't distinguish between these causes.

---

## Verifying either client

```bash
curl https://anton.musasouled.com/health                          # → 200, public
curl https://anton.musasouled.com/api/owned-shoes                 # → 401, no token
TOKEN=$(grep -oP 'desktop:\K[^,]*' backend/.env)                  # on the server
curl -H "Authorization: Bearer $TOKEN" https://anton.musasouled.com/mcp/ \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'  # → tool list
```
