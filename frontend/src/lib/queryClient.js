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

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      // gcTime must outlive a session for persistence to be useful — an entry
      // GC'd from memory is dropped from the persisted snapshot too. One week
      // matches the SW runtime-cache max-age.
      gcTime: 1000 * 60 * 60 * 24 * 7,
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
  throttleTime: 1000,
})

// Only persist successful GET query state — never an error/loading snapshot,
// and (defensively) never anything keyed to auth.
export const persistOptions = {
  persister: queryPersister,
  maxAge: 1000 * 60 * 60 * 24 * 7,
  dehydrateOptions: {
    shouldDehydrateQuery: (query) =>
      query.state.status === 'success' &&
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
