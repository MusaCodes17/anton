import { useEffect, useState } from 'react'
import { authApi, UNAUTHENTICATED_EVENT } from '@/services/api'
import { clearOfflineData } from '@/lib/queryClient'
import LoginView from '@/components/auth/LoginView'

// RA2.1 auth gate — the app's login-vs-app switch.
//
// On load it probes GET /api/auth/session to decide whether a valid session
// cookie exists. It also listens for the app-wide UNAUTHENTICATED_EVENT that
// api.js fires on any 401, so an expired session mid-session drops the user
// back to the login view instead of leaving a broken app.
//
// RA2.2 §3: a cold OFFLINE launch can't reach the probe. Since the httpOnly
// session cookie is still on the device, we optimistically enter the app so
// the persisted offline-read cache is usable — a real 401 on the next online
// request drops back to login. A genuine logged-out (200, authenticated:false)
// response instead wipes any cached personal data.
export default function AuthGate({ children }) {
  // 'loading' until the first probe resolves, then 'authed' | 'unauthed'.
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    let cancelled = false
    authApi
      .probe()
      .then((data) => {
        if (cancelled) return
        if (data?.authenticated) {
          setStatus('authed')
        } else {
          // Confirmed logged out — drop cached personal data before login.
          clearOfflineData()
          setStatus('unauthed')
        }
      })
      .catch(() => {
        if (cancelled) return
        // Probe failed. Offline → keep the app (session likely still valid,
        // cache is readable). Online → a real failure; show login.
        const offline = typeof navigator !== 'undefined' && navigator.onLine === false
        setStatus(offline ? 'authed' : 'unauthed')
      })

    const onUnauthenticated = () => setStatus('unauthed')
    window.addEventListener(UNAUTHENTICATED_EVENT, onUnauthenticated)
    return () => {
      cancelled = true
      window.removeEventListener(UNAUTHENTICATED_EVENT, onUnauthenticated)
    }
  }, [])

  if (status === 'loading') {
    // Minimal splash — avoids a login flash before the probe resolves.
    return <div className="min-h-screen bg-background" />
  }

  if (status === 'unauthed') {
    return <LoginView onAuthenticated={() => setStatus('authed')} />
  }

  return children
}
