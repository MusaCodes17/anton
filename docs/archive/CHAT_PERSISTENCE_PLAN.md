# CHAT_PERSISTENCE_PLAN.md — R2.6 Server-Side Chat & Memory Persistence

**Status:** executing (2026-07-08).
**Roadmap:** R2.6 (`docs/roadmap.md`), the last ⚠️ scheduled-to-change decision (`docs/design_decisions.md` **C8**). Dependency R2.1 (auth) shipped 2026-07-07.
**Framing:** move Son of Anton conversations *and* the 100 km checkpoint-prompt state off browser `localStorage` into the backend, so memory is device-independent and (later) readable by server-side agents. The streaming endpoint (`POST /api/chat/message`) stays **stateless per request** — persistence is a separate CRUD surface, not baked into the stream.

**Scoping decisions (confirmed with the runner, 2026-07-08):**
- **Start fresh** — no one-time upload of existing localStorage conversations. The server starts empty; old localStorage data is simply no longer read (not deleted).
- **MCP exposure deferred to R3** — R2.6's only consumer is the SPA. Agents that need shared chat context are R3; no MCP tool/resource for conversations now.
- **Message storage = JSON columns, not a normalized messages table.** `displayMessages` carries pure UI concerns (tool-call events, pill previews, dividers, streaming flags); normalizing it is speculative infra against CLAUDE.md §2.5 (personal scale is a feature). Labelled O(N)/single-user in the model docstring.

---

## §1 — Schema + migration (skill S03)

Two additive tables, one reversible migration off head `d0e1f2a3b4c5`. No server-side data pre-exists to reconcile (localStorage is client data, and we start fresh), so this is additive-nullable discipline, not the full E4 move-ceremony — but reversible downgrade + a live-DB backup still apply.

**`chat_conversations`** — one row per Son of Anton conversation.
- `id` `String(36)` PK — the **client-generated UUID** (`crypto.randomUUID()`). Keeping the client id preserves the in-memory-first / persist-on-first-message flow and avoids remounting `ChatArea` (keyed by conversation id) mid-stream.
- `title` `String(200)` nullable
- `model` `String(60)` — the model id the conversation is on
- `display_messages` `JSON` — the rich UI message array (verbatim client shape)
- `api_messages` `JSON` — the LLM-facing message array
- `created_at`, `updated_at` `DateTime(timezone=True)` — server stamps (`server_default=func.now()`, `updated_at` also `onupdate=func.now()`)

No `user_id` — single-user platform, no auth identity (deliberate, consistent with the rest of the schema).

**`checkpoint_prompts`** — records that the 100 km-checkpoint note prompt was shown for a shoe (so it isn't shown again). Pure UI-state persistence, not a mileage-ledger fact.
- `id` `Integer` PK
- `owned_shoe_id` `Integer` FK → `owned_shoes.id`
- `checkpoint_km` `Integer`
- `prompted_at` `DateTime(timezone=True)` server stamp
- `UniqueConstraint(owned_shoe_id, checkpoint_km)` — idempotent "mark" target

Both tables get façade exports in `models/__init__.py`. Migration: `create_table` ×2 + indexes; downgrade drops both. Apply to the live DB (backup first per §1 checklist).

## §2 — Services + REST endpoints + tests (backend lands with tests first)

**`services/chat_history.py`** (thin, session-first, keyword-only):
- `list_conversations(db)` → summaries (id, title, model, updated_at, created_at, message_count) newest-first.
- `get_conversation(db, id)` → full row or `LookupError`.
- `upsert_conversation(db, id, *, title, model, display_messages, api_messages)` → create-or-replace by id (mirrors the old whole-conversation save); enforces the cap of 50 by trimming the oldest beyond it (server-side equivalent of `MAX_CONVERSATIONS`).
- `delete_conversation(db, id)` → idempotent.

**`services/checkpoints.py`**:
- `list_prompted(db)` → list of `{owned_shoe_id, checkpoint_km}`.
- `mark_prompted(db, *, owned_shoe_id, checkpoint_km)` → idempotent insert (no-op if the unique pair exists).

**Routes** (thin adapters):
- On the existing `/chat` router: `GET /chat/conversations`, `GET /chat/conversations/{id}`, `PUT /chat/conversations/{id}`, `DELETE /chat/conversations/{id}`.
- New tiny `routers/checkpoints.py`: `GET /checkpoint-prompts`, `POST /checkpoint-prompts`. Registered in `main.py`.

**Tests** — `tests/test_chat_history.py`: upsert-then-get round trip, upsert idempotency/replace, cap-50 trim keeps newest, delete, 404 on missing. `tests/test_checkpoints.py`: mark then list, mark idempotency (unique pair).

## §3 — Frontend: conversations → API (React Query)

- `services/api.js`: add a `chatHistory` family (list/get/put/delete).
- `hooks/useApi.js`: `useConversations`, `useConversation(id)`, `useUpsertConversation`, `useDeleteConversation` with correct query keys + invalidation.
- Rewrite `lib/conversations.js` to keep the pure helpers (`createConversation`, `generateTitle`, cap constant) but drop all `localStorage`; `ChatPage` persists via the upsert mutation on stream-end and deletes via the delete mutation. Preserve the unsaved-empty / persist-on-first-message / delete-confirm semantics. **Start fresh** — no localStorage read/migration.

## §4 — Frontend: checkpoints → API

- `api.js`/`useApi.js`: `useCheckpointPrompts()` (prefetched set) + `useMarkCheckpointPrompted()`.
- `LogRunDialog.jsx`: replace `hasPromptedCheckpoint`/`markCheckpointPrompted` (localStorage) with the query set + mark mutation. Delete `lib/checkpoints.js`.

## §5 — Wrap-up (skill S13)

- `docs/design_decisions.md`: C8 → Superseded, add successor entry (server-side persistence, JSON-column rationale, start-fresh, MCP deferred).
- `docs/architecture.md`: §5 schema table (+2 tables), §16.7 note.
- `docs/changelog.md`: dated entry (ADDED/CHANGED, verification: suite count, vite build, visual pass).
- `docs/project_state.md`: R2.6 → §3; §11 re-point to deal-domain test gaps as next; §2 table + snapshot date.
- Suite green (149 → +tests); `vite build` clean, 0 console errors; desktop + ~380 px pass.

### §1 checklist
- [ ] live-DB backup (`shoe_deals.db.bak-chat-persistence`) before applying
- [ ] migration applies + `downgrade -1` drops cleanly
- [ ] façade exports added
- [ ] architecture §5 updated (§5 wrap-up)

*One commit per section, `r2:` prefixed.*
