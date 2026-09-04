// RA2.2 §4 — real connectivity state.
//
// `navigator.onLine` lies (it reports true on a captive/dead network), so the
// truth is a lightweight GET /health with no-store. This hook drives both the
// offline indicator (§3) and the write-disable annotations (§4). It's a
// belt-and-suspenders companion to the axios write-guard in services/api.js —
// the interceptor is the hard enforcement; this hook is the UI signal.
import { useEffect, useState, useCallback } from 'react'

// /health is backend-routed and NOT under /api, so the SW never caches it —
// the check always hits the real network.
const HEALTH_URL = '/health'

async function probeOnline() {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return false
  try {
    // ANY resolved HTTP response — even a non-2xx — proves we reached the
    // server, so we're online. Only a network-level throw (DNS/TCP failure,
    // truly offline) means offline. Checking res.ok here was the bug: it
    // flipped a reachable-but-non-200 server (or a 405 from the old HEAD probe)
    // into a false "offline" ribbon.
    await fetch(HEALTH_URL, { method: 'GET', cache: 'no-store' })
    return true
  } catch {
    return false
  }
}

export function useOnline() {
  // Optimistic start: assume online so first paint isn't a false offline flash.
  const [online, setOnline] = useState(true)

  const check = useCallback(async () => {
    setOnline(await probeOnline())
  }, [])

  useEffect(() => {
    check()
    const onOnline = () => check()
    const onOffline = () => setOnline(false)
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    // Re-verify when the app returns to the foreground (mobile PWA resume).
    const onVisible = () => {
      if (document.visibilityState === 'visible') check()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [check])

  return { online, recheck: check }
}
