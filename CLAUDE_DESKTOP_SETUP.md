# Claude Desktop ↔ Anton MCP setup (with R2.1 auth)

Claude Desktop reaches Anton's MCP server (`/mcp`) through
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote), a small stdio↔HTTP
bridge launched via `npx`. After the **R2.1 security pass**, `/mcp` requires the
shared bearer token (`ANTON_SECRET`), so the bridge must send it with
`--header`. This file is the one-time config change and the safe rollout order.

> **This is a breaking change for Claude Desktop.** If the server restarts with
> auth enforced while Desktop still sends no header, Desktop sync breaks
> immediately (every MCP call 401s). Do the config change **before** you restart
> the server. See "Rollout order" below.

---

## The config file

macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

### Before (unauthenticated — pre-R2.1)

```jsonc
{
  "mcpServers": {
    "running-shoe-deals": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://localhost:8000/mcp/"
      ]
    }
  }
}
```

### After (send the bearer token)

```jsonc
{
  "mcpServers": {
    "running-shoe-deals": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://localhost:8000/mcp/",
        "--header",
        "Authorization: Bearer <YOUR_ANTON_SECRET>"
      ]
    }
  }
}
```

Replace `<YOUR_ANTON_SECRET>` with the **exact** value of `ANTON_SECRET` from
`backend/.env`. `--header` and its `Name: Value` argument are two separate array
elements. Then fully quit and reopen Claude Desktop (it only reads this file at
launch).

### Notes

- **`--header` is supported.** Verified against `mcp-remote@0.1.38`
  (`parseCommandLineArgs` accepts `--header "<Name>: <Value>"`). The unpinned
  `npx mcp-remote` in the config resolves to a `--header`-capable version — no
  version pin needed. (SECURITY_PASS_PLAN §8 Q2.)
- **Use the literal token, not `${ANTON_SECRET}`.** `mcp-remote` *does* support
  `${ENV}` substitution in a header value, but Claude Desktop's launch
  environment does not reliably inherit your shell's `.env`, so a literal value
  is deterministic. The token in this file is no more exposed than the token in
  `.env` — same trusted machine, same single user.
- **Node version caveat.** `mcp-remote` needs a reasonably recent Node. On very
  old/mismatched Node it can crash at startup with
  `ReferenceError: File is not defined` (an undici incompatibility). If Desktop
  sync fails with that error after this change, the fix is a newer Node for the
  `npx` Desktop launches — **not** an auth change.

---

## Rollout order (do this exactly)

1. **Generate the secret** (if not already set):
   `python -c "import secrets; print(secrets.token_hex(32))"`.
2. **Set it in `backend/.env`** as `ANTON_SECRET=<value>` — and the same value as
   `VITE_ANTON_SECRET` in `frontend/.env` (the SPA needs it too).
3. **Update this Desktop config** to the "After" form above with the same value,
   and fully restart Claude Desktop.
4. **Restart the backend** (`python run.py`). Enforcement is now live; the app
   *fails fast* if `ANTON_SECRET` is unset.
5. **Verify, in order:** `curl http://localhost:8000/health` → `200` (no token);
   `curl http://localhost:8000/api/owned-shoes` → `401` (no token); the SPA
   loads (after a dev-server restart / rebuild so it picks up `VITE_ANTON_SECRET`);
   Son of Anton lists tools; Claude Desktop runs the `sync_coros_runs` prompt and
   connects.

If anything breaks mid-rollout, the escape hatch is `API_HOST=127.0.0.1` (keep it
off the LAN) while you fix the failing client's header — prefer fixing the header
over disabling auth.

## Rotating the token later

Rotation is a deliberate `.env` edit + restart, not a hot path
(SECURITY_PASS_PLAN §8 Q3): regenerate, set `ANTON_SECRET` **and**
`VITE_ANTON_SECRET`, update the `--header` here to match, restart the backend and
rebuild/hard-reload the SPA, and restart Claude Desktop.
