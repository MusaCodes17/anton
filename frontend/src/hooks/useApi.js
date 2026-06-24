import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  shoesApi,
  retailersApi,
  dealsApi,
  dashboardApi,
  scrapeApi,
  ownedShoesApi,
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
  recentDeals: (limit) => ['dashboard', 'recent-deals', limit],
  bestDeals: (limit) => ['dashboard', 'best-deals', limit],
  ownedShoes: (params) => ['owned-shoes', params ?? {}],
  ownedShoe: (id) => ['owned-shoes', 'detail', id],
  shoeRuns: (id) => ['owned-shoes', id, 'runs'],
  shoeNotes: (id) => ['owned-shoes', id, 'notes'],
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

export function useRecentDeals(limit = 8) {
  return useQuery({
    queryKey: queryKeys.recentDeals(limit),
    queryFn: () => dashboardApi.recentDeals(limit),
  })
}

export function useBestDeals(limit = 8) {
  return useQuery({
    queryKey: queryKeys.bestDeals(limit),
    queryFn: () => dashboardApi.bestDeals(limit),
  })
}

// ============== OWNED SHOES ==============
export function useOwnedShoes(params) {
  return useQuery({
    queryKey: queryKeys.ownedShoes(params),
    queryFn: () => ownedShoesApi.list(params),
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

export function useDeleteOwnedShoe() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => ownedShoesApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['owned-shoes'] }),
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

// ============== SCRAPING ==============
export function useScrapeAll() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (retailerIds) => scrapeApi.all(retailerIds),
    onSuccess: () => {
      // A scrape can produce new price records and deals everywhere.
      qc.invalidateQueries()
    },
  })
}
