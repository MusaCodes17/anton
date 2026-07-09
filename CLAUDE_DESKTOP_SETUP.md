# Claude Desktop ↔ Anton MCP setup (RA1.1 — per-client tokens)

Claude Desktop reaches Anton's MCP server (`/mcp`) through
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote), a small stdio↔HTTP
bridge launched via `npx`. `/mcp` requires the Desktop bearer token (the
`desktop` entry in `ANTON_TOKENS`), sent with `--header`. Each client now has
its own revocable token — revoking Desktop doesn't affect the SPA or loopback.

---

## The config file

macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```jsonc
{
  "mcpServers": {
    "running-shoe-deals": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://localhost:8000/mcp/",
        "--header",
        "Authorization: Bearer <DESKTOP_TOKEN>"
      ]
    }
  }
}
```

Replace `<DESKTOP_TOKEN>` with the **`desktop` token** from `ANTON_TOKENS` in
`backend/.env` (the token after `desktop:`). Then fully quit and reopen Claude
Desktop (it only reads this file at launch).

### Notes

- **`--header` is supported.** Verified against `mcp-remote@0.1.38`.
- **Use the literal token, not `${ENV}`.** `mcp-remote` does support `${ENV}`
  substitution, but Claude Desktop's launch environment does not reliably inherit
  your shell's `.env`, so a literal value is deterministic.
- **Node version.** `mcp-remote` needs a reasonably recent Node. If Desktop sync
  fails with `ReferenceError: File is not defined`, the fix is a newer Node, not
  an auth change.

---

## Rollout order

1. `ANTON_TOKENS` is set in `backend/.env` with `desktop:`, `loopback:`, `spa:` entries.
2. Update this Desktop config with the `desktop` token and restart Claude Desktop.
3. Restart the backend (`python run.py`). Enforcement is now live.
4. **Verify:** `curl http://localhost:8000/health` → `200`; `curl http://localhost:8000/api/owned-shoes` → `401`; the SPA loads; Son of Anton lists tools; Claude Desktop runs `sync_coros_runs`.

## Rotating the Desktop token

Edit `backend/.env` → change the `desktop:` token in `ANTON_TOKENS`, update the
`--header` value here, restart the backend, restart Claude Desktop. The SPA and
loopback tokens are unchanged.

## Remote URL (after RA1.2)

When the always-on host is provisioned, change `http://localhost:8000/mcp/` to
the remote URL (e.g. `https://anton.example.com/mcp/`) and update the token to
the new `desktop` value generated during RA1.1 cutover. For the claude.ai
connector, use the capability URL: `https://anton.example.com/mcp/<CONNECTOR_TOKEN>`.
