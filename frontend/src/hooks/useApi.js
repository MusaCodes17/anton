import { useCallback, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import {
  shoesApi,
  retailersApi,
  dealsApi,
  dashboardApi,
  scrapeApi,
  ownedShoesApi,
  corosSyncApi,
  trainingApi,
  stravaApi,
  watchlistApi,
  activitiesApi,
  racesApi,
  homeApi,
  shoeTypesApi,
  chatHistoryApi,
  checkpointsApi,
  adminApi,
  SCRAPE_STREAM_URL,
  authHeaders,
} from '@/services/api'

// Centralized query keys so mutations can invalidate precisely.
export const queryKeys = {
  shoes: (params) => ['shoes', params ?? {}],
  shoesSummary: () => ['shoes', 'summary'],
  shoe: (id) => ['shoes', 'detail', id],
  shoePrices: (id) => ['shoes', id, 'prices'],
  retailers: (params) => ['retailers', params ?? {}],
  deals: (params) => ['deals', params ?? {}],
  dashboardStats: () => ['dashboard', 'stats'],
  scrapeHistory: () => ['scrape', 'history'],
  schedule: () => ['admin', 'schedule'],
  ownedShoes: (params) => ['owned-shoes', params ?? {}],
  ownedShoe: (id) => ['owned-shoes', 'detail', id],
  shoeRuns: (id) => ['owned-shoes', id, 'runs'],
  shoeNotes: (id) => ['owned-shoes', id, 'notes'],
  replacementDeals: (id) => ['owned-shoes', id, 'replacement-deals'],
  rotationOverview: () => ['owned-shoes', 'rotation-overview'],
  corosSyncStatus: () => ['coros', 'sync-status'],
  trainingSummary: (period, range) => ['training', 'summary', period, range ?? {}],
  trainingRecords: () => ['training', 'records'],
  trainingFitness: () => ['training', 'fitness'],
  stravaStatus: () => ['strava', 'status'],
  watchlist: () => ['watchlist'],
  activities: (params) => ['activities', params ?? {}],
  races: () => ['races'],
  home: () => ['home'],
  conversations: () => ['conversations'],
  conversation: (id) => ['conversations', 'detail', id],
  checkpointPrompts: () => ['checkpoint-prompts'],
}

// ============== SHOES ==============
export function useShoes(params) {
  return useQuery({
    queryKey: queryKeys.shoes(params),
    queryFn: () => shoesApi.list(params),
  })
}

export function useShoesSummary() {
  return useQuery({
    queryKey: queryKeys.shoesSummary(),
    queryFn: () => shoesApi.summary(),
  })
}

export function useShoePrices(id) {
  return useQuery({
    queryKey: queryKeys.shoePrices(id),
    queryFn: () => shoesApi.priceHistory(id),
    enabled: !!id,
  })
}

export function useCreateShoe() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => shoesApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['shoes'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useUpdateShoe() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => shoesApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['shoes'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useDeleteShoe() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => shoesApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['shoes'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

// Not a useQuery — callers (form test button, list-page batch check) trigger
// this on demand for arbitrary brand/model pairs, including unsaved ones.
export function useTestShoeScrapability() {
  return useMutation({
    mutationFn: ({ brand, model }) => shoesApi.testScrapability(brand, model),
  })
}

// ============== RETAILERS ==============
export function useRetailers(params) {
  return useQuery({
    queryKey: queryKeys.retailers(params),
    queryFn: () => retailersApi.list(params),
  })
}

export function useCreateRetailer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => retailersApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['retailers'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useUpdateRetailer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => retailersApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['retailers'] }),
  })
}

export function useDeleteRetailer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => retailersApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['retailers'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

// ============== PROMO CODES ==============
export function useAddPromo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ retailerId, data }) =>
      retailersApi.addPromo(retailerId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['retailers'] }),
  })
}

export function useDeletePromo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (promoId) => retailersApi.deletePromo(promoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['retailers'] }),
  })
}

export function useDetectPromos() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (retailerId) =>
      retailerId ? scrapeApi.detectPromos(retailerId) : scrapeApi.detectAllPromos(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['retailers'] }),
  })
}

// ============== DEALS ==============
export function useDeals(params) {
  return useQuery({
    queryKey: queryKeys.deals(params),
    queryFn: () => dealsApi.list(params),
  })
}

export function useDeactivateDeal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => dealsApi.deactivate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deals'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

// ============== DASHBOARD ==============
export function useDashboardStats() {
  return useQuery({
    queryKey: queryKeys.dashboardStats(),
    queryFn: () => dashboardApi.stats(),
  })
}

// Per-retailer scrape health + recent-runs log (R2.5). Read-only; the scrape
// stream (useScrapeStream) invalidates this key on "completed" so a fresh scan
// refreshes the health surface.
export function useScrapeHistory() {
  return useQuery({
    queryKey: queryKeys.scrapeHistory(),
    queryFn: () => scrapeApi.history(),
  })
}

// Nightly schedule status (R4.1): enabled state, cron expression, next fire
// time, and last 5 scheduled runs. Refreshed every 60 s so the "next run"
// countdown stays reasonably current without hammering the backend.
export function useSchedule() {
  return useQuery({
    queryKey: queryKeys.schedule(),
    queryFn: () => adminApi.scheduleStatus(),
    refetchInterval: 60_000,
  })
}

// ============== HOME ==============
export function useHome() {
  return useQuery({
    queryKey: queryKeys.home(),
    queryFn: () => homeApi.summary(),
  })
}

// ============== TRAINING ==============
export function useTrainingSummary(period = 'monthly', range) {
  return useQuery({
    queryKey: queryKeys.trainingSummary(period, range),
    queryFn: () => trainingApi.summary(period, range),
  })
}

export function useTrainingRecords() {
  return useQuery({
    queryKey: queryKeys.trainingRecords(),
    queryFn: () => trainingApi.records(),
  })
}

export function useTrainingFitness() {
  return useQuery({
    queryKey: queryKeys.trainingFitness(),
    queryFn: () => trainingApi.fitness(),
  })
}

// ============== ACTIVITIES ==============
export function useActivities(params) {
  return useQuery({
    queryKey: queryKeys.activities(params),
    queryFn: () => activitiesApi.list(params),
    placeholderData: keepPreviousData,
  })
}

export function useActivityTags() {
  return useQuery({
    queryKey: ['activities', 'tags'],
    queryFn: () => activitiesApi.tags(),
    staleTime: Infinity, // the vocabulary is effectively constant
  })
}

export function useShoeTypes() {
  return useQuery({
    queryKey: ['shoe-types'],
    queryFn: () => shoeTypesApi.list(),
    staleTime: Infinity, // the vocabulary is effectively constant (R2.4)
  })
}

// ============== CHAT HISTORY (R2.6) ==============
// Server-side conversation persistence — replaces the old localStorage store.
export function useConversations() {
  return useQuery({
    queryKey: queryKeys.conversations(),
    queryFn: () => chatHistoryApi.list(),
  })
}

export function useUpsertConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }) => chatHistoryApi.upsert(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.conversations() }),
  })
}

export function useDeleteConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => chatHistoryApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.conversations() }),
  })
}

// ============== CHECKPOINT PROMPTS (R2.6) ==============
export function useCheckpointPrompts() {
  return useQuery({
    queryKey: queryKeys.checkpointPrompts(),
    queryFn: () => checkpointsApi.list(),
  })
}

export function useMarkCheckpointPrompted() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ ownedShoeId, checkpointKm }) =>
      checkpointsApi.mark(ownedShoeId, checkpointKm),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.checkpointPrompts() }),
  })
}

export function useActivity(id) {
  return useQuery({
    queryKey: ['activities', 'detail', id],
    queryFn: () => activitiesApi.get(id),
    enabled: id != null,
  })
}

// Any activity write can shift the ledger, PBs, volume, and shoe mileage — so
// these invalidate the activity feed, this detail, owned shoes, and training.
function invalidateAfterActivityWrite(qc, id) {
  qc.invalidateQueries({ queryKey: ['activities'] })
  qc.invalidateQueries({ queryKey: ['activities', 'detail', id] })
  qc.invalidateQueries({ queryKey: ['owned-shoes'] })
  qc.invalidateQueries({ queryKey: ['training'] })
  qc.invalidateQueries({ queryKey: ['home'] })
}

export function useUpdateActivity(id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => activitiesApi.update(id, data),
    onSuccess: () => invalidateAfterActivityWrite(qc, id),
  })
}

export function useReassignShoe(id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (shoeId) => activitiesApi.reassignShoe(id, shoeId),
    onSuccess: () => invalidateAfterActivityWrite(qc, id),
  })
}

export function usePromoteToRace(id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => activitiesApi.promoteToRace(id),
    onSuccess: () => { invalidateAfterActivityWrite(qc, id); qc.invalidateQueries({ queryKey: ['races'] }) },
  })
}

// ============== PLANNED RACES ==============
export function useRaces() {
  return useQuery({
    queryKey: queryKeys.races(),
    queryFn: () => racesApi.list(),
  })
}

export function useCreateRace() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => racesApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.races() }),
  })
}

export function useUpdateRace() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => racesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.races() }),
  })
}

export function useDeleteRace() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => racesApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.races() }),
  })
}

// ============== STRAVA ==============
export function useStravaStatus() {
  return useQuery({
    queryKey: queryKeys.stravaStatus(),
    queryFn: () => stravaApi.status(),
  })
}

// ============== WATCHLIST ==============
export function useWatchlist() {
  return useQuery({
    queryKey: queryKeys.watchlist(),
    queryFn: () => watchlistApi.list(),
  })
}

// ============== OWNED SHOES ==============
export function useOwnedShoes(params) {
  return useQuery({
    queryKey: queryKeys.ownedShoes(params),
    queryFn: () => ownedShoesApi.list(params),
  })
}

// Retirement pipeline (server-computed: which active shoes are past 75% of
// their limit + replacement-deal counts). Invalidated by the shared
// ['owned-shoes'] key on any rotation mutation.
export function useRotationOverview() {
  return useQuery({
    queryKey: queryKeys.rotationOverview(),
    queryFn: () => ownedShoesApi.rotationOverview(),
  })
}

export function useOwnedShoe(id) {
  return useQuery({
    queryKey: queryKeys.ownedShoe(id),
    queryFn: () => ownedShoesApi.get(id),
    enabled: !!id,
  })
}

export function useShoeRuns(id) {
  return useQuery({
    queryKey: queryKeys.shoeRuns(id),
    queryFn: () => ownedShoesApi.runs(id),
    enabled: !!id,
  })
}

export function useShoeNotes(id) {
  return useQuery({
    queryKey: queryKeys.shoeNotes(id),
    queryFn: () => ownedShoesApi.notes(id),
    enabled: !!id,
  })
}

export function useAddShoeNote() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => ownedShoesApi.addNote(id, data),
    onSuccess: (_data, { id }) => qc.invalidateQueries({ queryKey: queryKeys.shoeNotes(id) }),
  })
}

// Takes { id, noteId } — id is the owned shoe, used to invalidate its notes list.
export function useDeleteShoeNote() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ noteId }) => ownedShoesApi.deleteNote(noteId),
    onSuccess: (_data, { id }) => qc.invalidateQueries({ queryKey: queryKeys.shoeNotes(id) }),
  })
}

export function useCreateOwnedShoe() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => ownedShoesApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['owned-shoes'] }),
  })
}

export function useUpdateOwnedShoe() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => ownedShoesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['owned-shoes'] }),
  })
}

// Sanctioned manual mileage override (C1). Records a journal note server-side,
// so invalidate the shoe's notes list alongside the rotation queries.
export function useAdjustMileage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, newMileage }) => ownedShoesApi.adjustMileage(id, newMileage),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ['owned-shoes'] })
      qc.invalidateQueries({ queryKey: queryKeys.shoeNotes(id) })
    },
  })
}

export function useDeleteOwnedShoe() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => ownedShoesApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['owned-shoes'] }),
  })
}

export function useReplacementDeals(id) {
  return useQuery({
    queryKey: queryKeys.replacementDeals(id),
    queryFn: () => ownedShoesApi.replacementDeals(id),
    enabled: !!id,
  })
}

export function useLogRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => ownedShoesApi.logRun(id, data),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ['owned-shoes'] })
      qc.invalidateQueries({ queryKey: queryKeys.shoeRuns(id) })
    },
  })
}

// Takes the full run object (not just its id) so it can optimistically patch
// the run list + the shoe's mileage before the server responds.
export function useDeleteShoeRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (run) => ownedShoesApi.deleteRun(run.id),
    onMutate: (run) => {
      qc.setQueryData(queryKeys.shoeRuns(run.owned_shoe_id), (old) =>
        (old || []).filter((r) => r.id !== run.id)
      )
      qc.setQueriesData({ queryKey: ['owned-shoes'] }, (old) => {
        if (!Array.isArray(old)) return old
        return old.map((s) =>
          s.id === run.owned_shoe_id
            ? {
                ...s,
                current_mileage: Math.max(0, s.current_mileage - run.distance_km),
                total_runs: Math.max(0, (s.total_runs || 0) - 1),
              }
            : s
        )
      })
    },
    onSettled: (_data, _err, run) => {
      // Re-sync with the server either way — confirms the optimistic update
      // on success, or quietly corrects it if the delete failed.
      qc.invalidateQueries({ queryKey: ['owned-shoes'] })
      qc.invalidateQueries({ queryKey: queryKeys.shoeRuns(run.owned_shoe_id) })
    },
  })
}

// ============== COROS SYNC ==============
export function useCorosSyncStatus() {
  return useQuery({
    queryKey: queryKeys.corosSyncStatus(),
    queryFn: () => corosSyncApi.status(),
  })
}

export function useFetchCorosRuns() {
  return useMutation({
    mutationFn: (daysBack) => corosSyncApi.fetch(daysBack),
  })
}

export function useConfirmCorosRuns() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (assignments) => corosSyncApi.confirm(assignments),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['owned-shoes'] })
      qc.invalidateQueries({ queryKey: queryKeys.corosSyncStatus() })
    },
  })
}

// ============== SCRAPING ==============
/**
 * Replaces the old blocking useScrapeAll mutation. POSTs /api/scrape/all
 * (now returns immediately) then opens an SSE connection to
 * /api/scrape/stream for live per-retailer progress.
 *
 * - Patches the ['retailers'] cache in real time on each retailer_done
 *   event, so "Last scraped" updates immediately wherever the retailers
 *   list happens to be rendered, with no refetch needed.
 * - Invalidates everything once "completed" arrives (a scrape can touch
 *   deals/dashboard/retailers/shoes anywhere) — same blast radius as the
 *   old mutation's onSuccess.
 * - `start(onEvent)` returns a promise resolving to the POST body
 *   ({started: true} or {started: false, reason}); callers handle the
 *   false case (e.g. a toast) and pass `onEvent` for per-event UI (toasts,
 *   inline notices) without this hook needing to know about any of that.
 */
export function useScrapeStream() {
  const qc = useQueryClient()
  const [isRunning, setIsRunning] = useState(false)
  const [connectionLost, setConnectionLost] = useState(false)
  const abortRef = useRef(null)

  const closeStream = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  // Opens the SSE connection and wires up its handlers. Used both for a job
  // this hook just started AND for one already running server-side (the
  // stream replays full history to any subscriber, so reattaching after e.g.
  // a page reload picks up exactly where the real job actually is, instead
  // of just reporting "already in progress" with no way to see it finish).
  //
  // This reads the SSE over fetch() rather than a native EventSource because
  // fetch lets us abort the stream via AbortController. Auth is the RA2.1
  // session cookie, sent via credentials:'include' (a native EventSource would
  // send same-origin cookies too, but couldn't be aborted the same way). The
  // frame parsing mirrors useChatStream (split on blank lines, take `data:`).
  const attachStream = useCallback(
    (onEvent) => {
      setIsRunning(true)
      const controller = new AbortController()
      abortRef.current = controller

      const handleEvent = (event) => {
        if (event.type === 'retailer_done') {
          qc.setQueriesData({ queryKey: ['retailers'] }, (old) => {
            if (!Array.isArray(old)) return old
            return old.map((r) =>
              r.name === event.retailer ? { ...r, last_scraped_at: event.timestamp } : r
            )
          })
        }

        onEvent?.(event)

        if (event.type === 'completed') {
          closeStream()
          setIsRunning(false)
          // Patch the dashboard "Last scraped" timestamp with this exact
          // completion instant immediately — invalidateQueries() below will
          // also refetch it, but that's an async round-trip, so without this
          // the sidebar can briefly show stale data (or lag the real
          // completion moment) until the refetch resolves.
          qc.setQueryData(['dashboard', 'stats'], (old) =>
            old ? { ...old, last_scrape: event.completed_at } : old
          )
          qc.invalidateQueries()
        }
      }

      ;(async () => {
        try {
          const res = await fetch(SCRAPE_STREAM_URL, {
            headers: authHeaders(),
            credentials: 'include',
            signal: controller.signal,
          })
          if (!res.ok || !res.body) throw new Error(`stream failed (${res.status})`)

          const reader = res.body.getReader()
          const decoder = new TextDecoder()
          let buffer = ''

          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            const parts = buffer.split(/\r?\n\r?\n/)
            buffer = parts.pop() ?? ''
            for (const part of parts) {
              for (const line of part.split(/\r?\n/)) {
                if (!line.startsWith('data:')) continue
                const raw = line.slice(line.indexOf(':') + 1).trim()
                if (!raw) continue
                let event
                try {
                  event = JSON.parse(raw)
                } catch {
                  continue
                }
                handleEvent(event)
              }
            }
          }

          // Server closed the stream without a 'completed' event (handleEvent
          // aborts the controller on 'completed', so reaching here while still
          // running means the connection dropped) — surface it like the old
          // EventSource onerror did.
          setIsRunning((running) => {
            if (running) setConnectionLost(true)
            return false
          })
        } catch (err) {
          if (controller.signal.aborted) return // intentional close (completed/unmount)
          closeStream()
          setIsRunning(false)
          setConnectionLost(true)
        }
      })()
    },
    [qc, closeStream]
  )

  const start = useCallback(
    (onEvent) => {
      setConnectionLost(false)
      setIsRunning(true)

      return scrapeApi
        .all()
        .then((data) => {
          // Either we just started it, or one's already running (e.g.
          // kicked off before a page reload) — either way, attach and
          // watch it finish rather than just erroring on the latter.
          attachStream(onEvent)
          return data
        })
        .catch((err) => {
          setIsRunning(false)
          throw err
        })
    },
    [attachStream]
  )

  return { isRunning, connectionLost, start }
}
