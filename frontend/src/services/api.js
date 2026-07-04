import axios from 'axios'

// In dev, leave VITE_API_URL empty and let the Vite proxy forward /api to the
// backend. In production, set VITE_API_URL to the backend origin.
const baseURL = import.meta.env.VITE_API_URL || ''

const client = axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 120000, // scraping can be slow
})

// Normalize errors so the UI gets a readable message regardless of shape.
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail
    let message
    if (Array.isArray(detail)) {
      // FastAPI validation errors: [{ loc, msg, type }, ...]
      message = detail.map((d) => d.msg).join(', ')
    } else if (typeof detail === 'string') {
      message = detail
    } else {
      message = error.message || 'An unexpected error occurred'
    }
    return Promise.reject(new Error(message))
  }
)

// ============== SHOES ==============
export const shoesApi = {
  list: (params) => client.get('/api/shoes/', { params }).then((r) => r.data),
  summary: () => client.get('/api/shoes/summary').then((r) => r.data),
  get: (id) => client.get(`/api/shoes/${id}`).then((r) => r.data),
  create: (data) => client.post('/api/shoes/', data).then((r) => r.data),
  update: (id, data) => client.put(`/api/shoes/${id}`, data).then((r) => r.data),
  remove: (id) => client.delete(`/api/shoes/${id}`).then((r) => r.data),
  priceHistory: (id, limit = 100) =>
    client.get(`/api/shoes/${id}/prices`, { params: { limit } }).then((r) => r.data),
  testScrapability: (brand, model) =>
    client.post('/api/shoes/test', { brand, model }).then((r) => r.data),
}

// ============== RETAILERS ==============
export const retailersApi = {
  list: (params) => client.get('/api/retailers/', { params }).then((r) => r.data),
  get: (id) => client.get(`/api/retailers/${id}`).then((r) => r.data),
  create: (data) => client.post('/api/retailers/', data).then((r) => r.data),
  update: (id, data) =>
    client.put(`/api/retailers/${id}`, data).then((r) => r.data),
  remove: (id) => client.delete(`/api/retailers/${id}`).then((r) => r.data),
  promos: (id, isActive = true) =>
    client
      .get(`/api/retailers/${id}/promos`, { params: { is_active: isActive } })
      .then((r) => r.data),
  addPromo: (id, data) =>
    client.post(`/api/retailers/${id}/promos`, data).then((r) => r.data),
  deletePromo: (promoId) =>
    client.delete(`/api/retailers/promos/${promoId}`).then((r) => r.data),
}

// ============== EXPORT ==============
export const exportApi = {
  // Returns seed_data.py source as plain text.
  seedData: () =>
    client.get('/api/export/seed-data', { responseType: 'text' }).then((r) => r.data),
}

// ============== DEALS ==============
export const dealsApi = {
  list: (params) => client.get('/api/deals/', { params }).then((r) => r.data),
  get: (id) => client.get(`/api/deals/${id}`).then((r) => r.data),
  deactivate: (id) =>
    client.put(`/api/deals/${id}/deactivate`).then((r) => r.data),
  forShoe: (shoeId, params) =>
    client.get(`/api/deals/shoe/${shoeId}`, { params }).then((r) => r.data),
  forRetailer: (retailerId, params) =>
    client.get(`/api/deals/retailer/${retailerId}`, { params }).then((r) => r.data),
}

// ============== DASHBOARD ==============
export const dashboardApi = {
  stats: () => client.get('/api/dashboard/stats').then((r) => r.data),
  recentDeals: (limit = 10) =>
    client.get('/api/dashboard/recent-deals', { params: { limit } }).then((r) => r.data),
  bestDeals: (limit = 10) =>
    client.get('/api/dashboard/best-deals', { params: { limit } }).then((r) => r.data),
}

// ============== SCRAPING ==============
// /scrape/shoe/{id} and /scrape/retailer/{id} are still synchronous and can
// take a while — the default 120s client timeout would fire long before the
// backend finishes (it keeps running server-side regardless, just rejected
// retries with 409 now instead of stacking). Give those calls real headroom.
// /scrape/all is no longer one of these — it now returns immediately and
// reports progress over SSE (see SCRAPE_STREAM_URL / useScrapeStream).
const SCRAPE_TIMEOUT_MS = 35 * 60 * 1000

// Built the same way axios resolves its own baseURL, so the EventSource in
// useScrapeStream hits the right host in both dev (Vite proxies /api) and
// production (VITE_API_URL set).
export const SCRAPE_STREAM_URL = `${baseURL}/api/scrape/stream`

export const scrapeApi = {
  all: (retailerIds) =>
    client
      .post('/api/scrape/all', null, {
        params: retailerIds ? { retailer_ids: retailerIds } : undefined,
      })
      .then((r) => r.data),
  shoe: (shoeId, retailerIds) =>
    client
      .post(`/api/scrape/shoe/${shoeId}`, null, {
        params: retailerIds ? { retailer_ids: retailerIds } : undefined,
        timeout: SCRAPE_TIMEOUT_MS,
      })
      .then((r) => r.data),
  retailer: (retailerId, shoeIds) =>
    client
      .post(`/api/scrape/retailer/${retailerId}`, null, {
        params: shoeIds ? { shoe_ids: shoeIds } : undefined,
        timeout: SCRAPE_TIMEOUT_MS,
      })
      .then((r) => r.data),
  detectPromos: (retailerId) =>
    client.post(`/api/scrape/promos/${retailerId}`).then((r) => r.data),
  detectAllPromos: () =>
    client.post('/api/scrape/promos').then((r) => r.data),
}

// ============== OWNED SHOES ==============
export const ownedShoesApi = {
  list: (params) => client.get('/api/owned-shoes/', { params }).then((r) => r.data),
  get: (id) => client.get(`/api/owned-shoes/${id}`).then((r) => r.data),
  create: (data) => client.post('/api/owned-shoes/', data).then((r) => r.data),
  update: (id, data) => client.put(`/api/owned-shoes/${id}`, data).then((r) => r.data),
  remove: (id) => client.delete(`/api/owned-shoes/${id}`).then((r) => r.data),
  logRun: (id, data) => client.post(`/api/owned-shoes/${id}/log-run`, data).then((r) => r.data),
  runs: (id) => client.get(`/api/owned-shoes/${id}/runs`).then((r) => r.data),
  deleteRun: (runId) => client.delete(`/api/owned-shoes/runs/${runId}`).then((r) => r.data),
  notes: (id) => client.get(`/api/owned-shoes/${id}/notes`).then((r) => r.data),
  addNote: (id, data) => client.post(`/api/owned-shoes/${id}/notes`, data).then((r) => r.data),
  deleteNote: (noteId) => client.delete(`/api/owned-shoes/notes/${noteId}`).then((r) => r.data),
  replacementDeals: (id) => client.get(`/api/owned-shoes/${id}/replacement-deals`).then((r) => r.data),
}

// ============== TRAINING ==============
export const trainingApi = {
  summary: (period = 'monthly') =>
    client.get('/api/training/summary', { params: { period } }).then((r) => r.data),
  records: () => client.get('/api/training/records').then((r) => r.data),
}

// ============== ACTIVITIES (unified run feed) ==============
export const activitiesApi = {
  list: (params) => client.get('/api/activities', { params }).then((r) => r.data),
}

// ============== PLANNED RACES ==============
export const racesApi = {
  list: () => client.get('/api/races').then((r) => r.data),
  create: (data) => client.post('/api/races', data).then((r) => r.data),
  update: (id, data) => client.patch(`/api/races/${id}`, data).then((r) => r.data),
  remove: (id) => client.delete(`/api/races/${id}`).then((r) => r.data),
}

// ============== STRAVA ==============
export const stravaApi = {
  status: () => client.get('/api/strava/status').then((r) => r.data),
}

// ============== WATCHLIST ==============
export const watchlistApi = {
  list: () => client.get('/api/watchlist').then((r) => r.data),
}

// ============== COROS SYNC ==============
export const corosSyncApi = {
  status: () => client.get('/api/owned-shoes/sync-coros/status').then((r) => r.data),
  fetch: (daysBack = 30) =>
    client
      .post('/api/owned-shoes/sync-coros/fetch', null, { params: { days_back: daysBack } })
      .then((r) => r.data),
  confirm: (assignments) =>
    client.post('/api/owned-shoes/sync-coros/confirm', { assignments }).then((r) => r.data),
}

export default client
