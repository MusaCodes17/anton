// RA2.2 §4 — real connectivity state.
//
// `navigator.onLine` lies (it reports true on a captive/dead network), so the
// truth is a lightweight GET /health with no-store. This hook drives both the
// offline indicator (§3) and the write-disable annotations (§4). It's a
// belt-and-suspenders companion to the axios write-guard in services/api.js —
// the interceptor is the hard enforcement; this hook is the UI signal.
//
// E11 adds a third state: 'unreachable' — the phone is online but the Anton
// server isn't answering (deploy restart, crash), so Caddy returns a 5xx. The
// service worker then serves cached reads, and the banner says they're stale.
// `online` keeps its meaning (network connectivity) for the write annotations;
// a write while the server is down fails and toasts, it is never queued.
import { useEffect, useState, useCallback } from 'react'
import { SERVER_REACHABLE_EVENT, SERVER_UNREACHABLE_EVENT } from '@/services/api'

// /health is backend-routed and NOT under /api, so the SW never caches it —
// the check always hits the real network.
const HEALTH_URL = '/health'

// While offline or unreachable, re-probe on this interval so the banner clears
// on its own once the server is back. Only runs while the banner shows.
const RECHECK_WHILE_DOWN_MS = 30_000

// → 'online' | 'offline' | 'unreachable'. Concurrent callers share one request:
// a page load whose reads all came from the SW cache fires one hint per read,
// and every mounted useOnline listens.
let inflight = null
function probeServer() {
  if (!inflight) inflight = fetchStatus().finally(() => { inflight = null })
  return inflight
}

async function fetchStatus() {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return 'offline'
  try {
    // A resolved non-5xx response — even a 4xx — proves we reached the server.
    // Only a network-level throw (DNS/TCP failure, truly offline) means
    // offline. Checking res.ok here was the bug: it flipped a reachable-but-
    // non-200 server (or a 405 from the old HEAD probe) into a false "offline"
    // ribbon. A 5xx is the proxy speaking for a backend that's down.
    const res = await fetch(HEALTH_URL, { method: 'GET', cache: 'no-store' })
    return res.status >= 500 ? 'unreachable' : 'online'
  } catch {
    return 'offline'
  }
}

export function useOnline() {
  // Optimistic start: assume online so first paint isn't a false offline flash.
  const [status, setStatus] = useState('online')

  const check = useCallback(async () => {
    setStatus(await probeServer())
  }, [])

  useEffect(() => {
    check()
    const onOnline = () => check()
    const onOffline = () => setStatus('offline')
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    // api.js hints (a cache-fallback read, a 5xx, or a fresh response): confirm
    // with the probe rather than trusting a single request.
    window.addEventListener(SERVER_UNREACHABLE_EVENT, onOnline)
    // Re-verify when the app returns to the foreground (mobile PWA resume).
    const onVisible = () => {
      if (document.visibilityState === 'visible') check()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
      window.removeEventListener(SERVER_UNREACHABLE_EVENT, onOnline)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [check])

  useEffect(() => {
    if (status === 'online') return undefined
    const onReachable = () => check()
    window.addEventListener(SERVER_REACHABLE_EVENT, onReachable)
    const timer = setInterval(check, RECHECK_WHILE_DOWN_MS)
    return () => {
      window.removeEventListener(SERVER_REACHABLE_EVENT, onReachable)
      clearInterval(timer)
    }
  }, [status, check])

  return { online: status !== 'offline', status, recheck: check }
}
