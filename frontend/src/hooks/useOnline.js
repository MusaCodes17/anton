// RA2.2 §4 — real connectivity state.
//
// `navigator.onLine` lies (it reports true on a captive/dead network), so the
// truth is a lightweight HEAD /health with no-store. This hook drives both the
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
    const res = await fetch(HEALTH_URL, { method: 'HEAD', cache: 'no-store' })
    return res.ok
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
