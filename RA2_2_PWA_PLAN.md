# RA2.2 — Progressive Web App pass (plan doc)

**Written:** 2026-08-29. **Status:** executing contract for RA2.2.
**Scope decision (locked with the runner, 2026-08-29):** installable PWA + offline
**read** only. **Writes require connectivity** — no offline write-queue. The
write-queue is split out as a separate gated item (see §6) because replaying
confirmation-gated mutations (C9) against stale state would break the mileage
ledger (INV-1) and the single-writer assumption (INV-9).

**Why this milestone:** RA2.1 put the SPA on the internet behind session auth.
RA2.2 makes it *feel like an app* — home-screen icon, standalone launch, instant
open, useful with no signal — which is ~90% of the "app in my pocket" goal for a
fraction of native's cost. It's also the honest test of whether R5.1 (native) is
needed at all: the main native-only win (push) was retired with R3.5, so if the
PWA feels good, native may never be justified.

**Conventions:** one commit per numbered section, `ra2:` prefix, suite green each
session, backend-with-tests before UI where backend is touched (it barely is here).

---

## 0. Constraints this plan must honor

- **INV-1 (mileage ledger)** and **INV-9 (single writer)** — untouched. This is why
  writes stay online-only; see §6 for the deferred-write rationale in full.
- **C9 (confirmation gates)** — every write still confirms against live state,
  synchronously. The PWA must never create a path where a confirmed action commits
  later against different state.
- **RA2.1 session-cookie auth** — the service worker must NOT cache authenticated
  API responses in a way that leaks across a logout, and must never cache the
  session cookie or any credential. Auth stays exactly as RA2.1 built it.
- **Same-origin model** — the SPA and `/api` are same-origin behind Caddy; the
  service worker scope is the site root. No cross-origin caching.
- **380px mobile-first discipline** — already a first-class constraint (CLAUDE.md
  §5); the PWA inherits it, adds the standalone-display and safe-area polish.

---

## 1. Install shell (manifest + service worker via vite-plugin-pwa)

**Add `vite-plugin-pwa`** to `frontend/vite.config.js` (works cleanly on the current
plain Vite+React setup; no existing PWA config to reconcile). Configure:

- `registerType: 'autoUpdate'` — new deploys refresh the SW without a manual prompt
  (acceptable for a single-user app; revisit if it ever causes mid-session reloads).
- **Web app manifest:** `name: "Anton"`, `short_name: "Anton"`, `display: "standalone"`,
  `theme_color` / `background_color` from the existing design tokens (don't invent
  colors — read them from the Tailwind/token source), `start_url: "/"`, `scope: "/"`,
  `orientation: "portrait"`.
- **Icons:** generate maskable + any-purpose PNG icons (192, 512, + maskable 512)
  from the existing `favicon.svg` or a proper Anton mark if one exists (the mark/logo
  is a known backlog item — if it's not done, ship with a clean generated icon from
  the favicon and note the upgrade). Place in `frontend/public/`.
- **iOS specifics:** iOS ignores much of the manifest — add `apple-touch-icon` link
  and `apple-mobile-web-app-capable` / `apple-mobile-web-app-status-bar-style` meta
  tags in `index.html`, and test "Add to Home Screen" in mobile Safari explicitly
  (this is the runner's actual platform per prior sessions).

**Acceptance:** on the phone, "Add to Home Screen" installs Anton with its icon; it
launches standalone (no browser chrome); Lighthouse PWA-installability passes.

## 2. App-shell + static-asset caching (offline launch)

Service-worker precache of the built app shell (HTML/JS/CSS/icons/fonts) via
`vite-plugin-pwa`'s Workbox integration (`globPatterns` over the `dist` output).
Result: the app **opens** with no signal — you get the shell, navigation, and the
login/loading states, not a browser error page.

- **Navigation fallback:** SPA routing already needs `try_files … /index.html`
  (Caddy, RA2.1) — mirror that in the SW nav-fallback so client-side routes work
  offline too.
- **Cache versioning:** Workbox handles precache revisioning on each build; confirm
  old caches are cleaned on `autoUpdate` so a deploy doesn't strip-mine storage.

**Acceptance:** airplane mode → tap the installed icon → the app shell loads and
routes are navigable (data areas show the offline-read state from §3, not errors).

## 3. Offline READ — cache last-loaded data (the real value)

The app already uses **React Query** for server state — lean on it rather than
hand-rolling a data cache.

- **Runtime caching (Workbox):** register a `NetworkFirst` (or `StaleWhileRevalidate`
  for read-mostly views) strategy for **GET `/api/*`** responses, with a sane max-age
  and entry cap. NetworkFirst = fresh when online, last-good when offline. Scope this
  to safe GET reads only (dashboard/home, rotation, deals, training, watchlist).
- **React Query persistence:** add `@tanstack/react-query-persist-client` +
  an IndexedDB/localStorage persister so the query cache survives an app restart —
  this is what makes a cold offline launch show *your* last-loaded rotation/deals
  rather than empty skeletons. Persist GET query keys only.
- **Auth safety:** the SW runtime cache and the RQ persister must be **cleared on
  logout** (hook the RA2.1 `DELETE /api/auth/session` / the `anton:unauthenticated`
  event) so a shared/lost device can't read cached personal data after sign-out.
  Never cache the session probe or any auth response.
- **Explicit staleness signaling:** when data is served from cache while offline,
  the UI shows a subtle "offline — showing last synced data" indicator (reuse the
  existing design-token styling; no new colors). Honesty over the illusion of live
  data — the same discipline as the rest of the app.

**Acceptance:** load the app online (populates cache) → airplane mode → cold-launch
from the home-screen icon → rotation, deals, and training show last-loaded data with
an offline indicator; a pull-to-refresh / refetch cleanly no-ops or shows "offline".

## 4. Writes require connectivity (the deliberate boundary)

Every mutating action (log run, edit activity, confirm COROS, retire shoe, manage
deals/promos, onboarding writes, chat send) **requires a live connection**. When
offline:

- Detect offline state (`navigator.onLine` + a real connectivity check — `onLine`
  lies; a lightweight `/health` HEAD or a failed request is the truth).
- **Disable/annotate write controls** with a clear, non-alarming state: "You're
  offline — this needs a connection." Do NOT silently queue.
- On reconnect, controls re-enable normally. No replay, no queue, nothing to sync.

This is the line that keeps INV-1/INV-9/C9 intact. It must be explicit in the UI so
the behavior reads as *intentional*, not broken.

**Acceptance:** offline → the log-run / edit / confirm controls show the offline
state and cannot fire a write; back online → they work normally with no queued
side effects.

## 5. Backend touch (minimal)

Mostly none — the PWA is a frontend concern over the already-remote, already-authed
SPA. The only backend considerations:

- **Caddy:** ensure `service-worker.js` and the manifest are served from the SPA
  static handler with correct `Content-Type` and a **no-cache** header on the SW file
  itself (the SW must always be revalidated so updates propagate; Workbox/Vite handle
  precache revisioning, but the SW script must not be HTTP-cached stale). Verify the
  RA2.1 `@backend` matcher doesn't accidentally swallow these paths.
- **No new endpoints, no migration, no auth change.**

**Acceptance:** `curl -I` on the SW file shows no-cache/revalidate; manifest and
icons load with correct content-types over HTTPS.

## 6. Explicitly deferred — offline WRITE-QUEUE (separate gated item)

Recorded here so a future session doesn't quietly build it under RA2.2's banner.

Offline write-queue (queue confirmed actions, replay on reconnect) is **out of scope
by decision**, deferred to a standalone R5.x item, built only on a felt "I needed to
log off-grid and genuinely couldn't" need. It is not a UI nicety — doing it correctly
requires:
- **Idempotency keys** on every mutation (so a replay can't double-apply — critical
  for the mileage ledger).
- **Conflict detection on replay** (the queued action was confirmed against state
  that may have changed — e.g. the shoe was retired, or the same run synced via
  COROS on another device).
- **Re-confirmation of stale queued actions** (C9 can't be satisfied by a
  confirmation made against state that no longer holds).

Also note the need is genuinely thin for this runner: the primary run-logging path is
**COROS sync, which is connector-mediated (C6) and cannot be queued offline anyway**.
The pure offline-manual-log-with-no-signal case is the only thing a write-queue would
serve, and it's rare. Revisit only if that specific gap becomes real.

---

## 7. Sequence & acceptance summary

1. §1 install shell (manifest + SW + icons) — the "it's an app" win, ship first.
2. §2 app-shell precache — offline launch.
3. §3 offline read (Workbox runtime cache + RQ persistence + offline indicator +
   logout-clear) — the real daily value; the biggest piece.
4. §4 offline-write boundary UI — the deliberate line.
5. §5 Caddy SW/ manifest headers — the small backend touch.

**Milestone done when:** installed to the phone home screen, launches standalone,
opens and shows last-loaded rotation/deals/training with no signal (honestly
labeled), and every write cleanly requires connectivity with no silent queue.
Then: does the PWA feel like enough? If yes, R5.1 native is not needed. If a
specific limitation bites, that limitation is the spec for R5.1 — a far better input
than guessing now.

**Complexity:** Medium (one focused build; §3 is the substantive part). No backend
migration, no auth change, no invariant touched.
