# Spike — COROS MCP direct client (R5.7 §1)

**Run:** 2026-10-07 · script `scripts/spikes/coros_mcp_client.py` (throwaway) · fixtures `scripts/spikes/fixtures/` (coordinates/location redacted).
**Verdict: provisional GO — one condition outstanding (multi-day unattended refresh; see §4).** Runner decides.

## Findings

| # | Question | Answer |
|---|---|---|
| 1 | Endpoint | `https://mcpus.coros.com/mcp` works; unauthenticated POST → `401` + `WWW-Authenticate: Bearer resource_metadata=".../.well-known/oauth-protected-resource/mcp"`. Account resolves to the US region (token accepted there). |
| 2 | OAuth discovery | Full MCP-spec metadata. Protected-resource: `resource=https://mcpus.coros.com/mcp`, scopes `openid mcp.tools offline_access`. AS metadata: authorize `/oauth2/authorize`, token `/oauth2/token`, revoke `/oauth2/revoke`, register `/connect/register`, introspect, jwks. Grants: `authorization_code`, `refresh_token` (+ client_credentials, device_code, token-exchange). **PKCE S256 only.** Public clients (`token_endpoint_auth_method: none`) supported. |
| 3 | Client registration | **Open Dynamic Client Registration**, no approval. Public client, no secret issued. A registration with the production redirect `https://anton.musasouled.com/api/coros/callback` returned `201`. So "no application needed" = DCR. Consequence: client_id must be registered once and stored (§2 table), no client secret to manage. |
| 4 | Tokens | Refresh token issued (`offline_access`). Access token `expires_in = 2591999` s (**~30 days**). No refresh-token lifetime advertised (`refresh_token_expires_in` absent). **Refresh rotates the refresh token** (new one on every refresh) → the refresh lock in §2 is mandatory, and the new token must be persisted atomically before use. Refresh succeeded non-interactively. |
| 5 | Transport | Streamable HTTP works with plain JSON-RPC POST (`Accept: application/json, text/event-stream`, `MCP-Protocol-Version: 2025-06-18`); `initialize` returned no `Mcp-Session-Id` → stateless confirmed. Responses came back as JSON. Official `mcp` SDK client **not** tried (raw httpx is simpler and sufficient; recommend a minimal JSON-RPC client in §3, avoiding SDK/auth-flow coupling). 34 tools; **none declare an `outputSchema`**. |
| 6 | Calls | Both succeed, but see the headline below. |
| 7 | Limits | No rate-limit/`Retry-After` headers observed on initialize, list or detail. |
| 8 | Terms | No standalone MCP-developer terms found. The COROS help page says: "No application or approval required" and "All data access is scoped to the authorizing user only (single-user)". Formal API Terms (rate limits, privacy) belong to the separate Partner API. Nothing found that forbids unattended background access, but absence is not a grant — worth an email to api@coros.com if you want certainty. |

## Headline: tool results are human-formatted TEXT, not JSON

`content[0].text` is a JSON-encoded string of a report. §3's client must **regex-parse prose**. This is the single biggest risk to the plan: a wording change silently breaks parsing. Mitigation (already in §3): contract tests on these fixtures plus loud failure when an expected field is missing — never write nulls.

### `querySportRecords`
- Args (all required keys, nullable): `startDate`, `endDate` (`YYYYMMDD`), `sportTypeCodes`, `minDistanceKm`, `maxDistanceKm`, `minDurationMinutes`, `maxDurationMinutes`, `maxAveragePace`, `locationKeyword`, `limit`.
- **There is no `timezone` argument.** The plan's "query with timezone America/Toronto" has no knob. The run date is printed per record (`1. Outdoor Run — 2026-10-06`) and agrees with Toronto local (record 1: startTimestamp 2026-10-07 00:39 UTC = 2026-10-06 20:39 EDT, dated 10-06). Use that printed date directly (as the plan says); the account's timezone appears to govern it. Flag: if the COROS account timezone is ever changed, dates shift.
- Per record: sport label + date, location, start coordinates, `startTimestamp`/`endTimestamp` (epoch s), `Duration` (`M:SS` or `H:MM:SS`), `Distance: N km`, `Average Pace: M:SS /km`, `Avg HR`, `Calories`, `LabelId: <18-digit> | SportType: <int>`.
- `labelId` is an 18-digit integer (exceeds JS safe-integer range: **keep as string**).

### `getActivityDetail(labelId: string, sportType: int)`
Text lines: Workout Time, Distance, Total Time, Average Pace, Moving Average Pace, Adjusted Pace, Best Kilometer, Average Heart Rate, Average Cadence (spm), Stride Length, Average Power, **Elevation Gain / Loss: `60 m / 48 m`**, Calories, Training Load, Aerobic/Anaerobic TE, Training Focus, Performance.
- Maps to our fields: `moving_time_s` ← Workout Time, `elapsed_time_s` ← Total Time, `elevation_gain_m`, `avg_cadence`, `calories`, `training_load`, `training_focus`.
- Units are all human-formatted (km, m, `M:SS`), so the plan's "list and detail differ in scaling" worry is moot at this layer; the parser still asserts units.
- Detail text carries **no date or labelId** — the client must pair it with its list record.

## Go / no-go

- Refresh tokens: ✅ issued, rotating, refreshed non-interactively once.
- Two calls: ✅.
- ToS: no prohibition found.
- **Outstanding:** "refresh unattended for weeks" is unproven by one same-day refresh. Access tokens last ~30 days, so the poller needs refresh only monthly; the refresh-token lifetime is unadvertised. Proposal: run `scripts/spikes/coros_mcp_client.py refresh` 24 h+ from now (and again after a week) before/while §2 is built; §2's `reauth_required` path covers the failure case honestly.

## Design implications for §2–§4
1. Store `client_id` from DCR (register once at first connect; re-register if COROS rejects it).
2. Rotation ⇒ persist the new refresh token in the same transaction as use; hold the lock across refresh.
3. Access token lives 30 days, so refresh rarely; still refresh lazily on 401/near-expiry.
4. Typed client = raw httpx JSON-RPC + text parsers; fixture contract tests; fail loudly on missing fields.
5. Pass `resource=https://mcpus.coros.com/mcp` on authorize and token requests (worked here).
6. No server-side timezone control; trust the printed date.
