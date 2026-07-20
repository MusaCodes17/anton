import { useEffect, useState } from 'react'
import { authApi, UNAUTHENTICATED_EVENT } from '@/services/api'
import LoginView from '@/components/auth/LoginView'

// RA2.1 auth gate — the app's login-vs-app switch.
//
// On load it probes GET /api/auth/session to decide whether a valid session
// cookie exists. It also listens for the app-wide UNAUTHENTICATED_EVENT that
// api.js fires on any 401, so an expired session mid-session drops the user
// back to the login view instead of leaving a broken app.
export default function AuthGate({ children }) {
  // 'loading' until the first probe resolves, then 'authed' | 'unauthed'.
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    let cancelled = false
    authApi
      .probe()
      .then((data) => {
        if (!cancelled) setStatus(data?.authenticated ? 'authed' : 'unauthed')
      })
      .catch(() => {
        // Probe itself failing (network/500) — show login rather than a blank app.
        if (!cancelled) setStatus('unauthed')
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
