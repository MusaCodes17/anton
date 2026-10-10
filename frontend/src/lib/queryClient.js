// RA2.2 §3 — React Query client + offline persistence.
//
// The query cache is persisted to IndexedDB so a cold offline launch shows the
// runner's LAST-LOADED rotation/deals/training instead of empty skeletons. We
// persist GET query state ONLY (React Query never persists mutations), and we
// wipe everything on logout so a shared/lost device can't read cached personal
// data after sign-out (auth safety, §0/§3).
import { QueryClient } from '@tanstack/react-query'
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister'
import { get, set, del } from 'idb-keyval'

// Runtime-cache name must match the Workbox `runtimeCaching` entry in
// vite.config.js — we clear it by name on logout.
const API_RUNTIME_CACHE = 'anton-api-reads'
const PERSIST_KEY = 'anton-rq-cache'
// Persisted-cache lifetime. 24 h (was 7 days): the cache is rehydrated on every
// cold launch, and a long-lived snapshot grows large and stale. Kept equal to
// gcTime and maxAge below so an entry is never persisted past memory GC.
const CACHE_LIFETIME_MS = 1000 * 60 * 60 * 24

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      // gcTime must outlive a session for persistence to be useful — an entry
      // GC'd from memory is dropped from the persisted snapshot too.
      gcTime: CACHE_LIFETIME_MS,
      // iOS flips online/offline on app resume, which would refetch every stale
      // query at once against the single-worker backend (a reconnect storm).
      // Stale data is still refetched on mount and on explicit invalidation.
      refetchOnReconnect: false,
    },
  },
})

// IndexedDB-backed persister (via idb-keyval) — async, so it survives large
// caches without the ~5MB localStorage ceiling.
export const queryPersister = createAsyncStoragePersister({
  key: PERSIST_KEY,
  storage: {
    getItem: (k) => get(k),
    setItem: (k, v) => set(k, v),
    removeItem: (k) => del(k),
  },
  // Each flush JSON-stringifies the whole cache on the main thread, so flush
  // at most every 5 s rather than every 1 s.
  throttleTime: 5000,
})

// Only persist successful GET query state — never an error/loading snapshot,
// and (defensively) never anything keyed to auth.
//
// `buster` is the build version (vite.config.js __APP_VERSION__). After a deploy
// the persisted snapshot is discarded if its buster differs, so old-shape cached
// data is never rehydrated (it could crash a component on a changed payload).
//
// Each flush JSON-stringifies the whole cache on the main thread; the large
// lists opt out via meta.persist = false (see useApi.js) to keep flushes small.
export const persistOptions = {
  persister: queryPersister,
  maxAge: CACHE_LIFETIME_MS,
  buster: __APP_VERSION__,
  dehydrateOptions: {
    shouldDehydrateQuery: (query) =>
      query.state.status === 'success' &&
      !(query.meta?.persist === false) &&
      !String(query.queryKey?.[0] ?? '').startsWith('auth'),
  },
}

// Logout / unauthenticated wipe: drop the in-memory cache, the persisted
// IndexedDB snapshot, and the SW runtime cache of /api reads. Called from the
// logout button and on the app-wide unauthenticated event (RA2.2 §3).
export async function clearOfflineData() {
  try {
    queryClient.clear()
    await del(PERSIST_KEY)
    if (typeof caches !== 'undefined') {
      await caches.delete(API_RUNTIME_CACHE)
    }
  } catch {
    // Best-effort — never let cache cleanup block the logout flow.
  }
}
