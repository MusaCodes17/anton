import React from 'react'
import ReactDOM from 'react-dom/client'
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import AuthGate from '@/components/auth/AuthGate'
import { ToastProvider } from '@/components/ui/toast'
import { queryClient, persistOptions, clearOfflineData } from '@/lib/queryClient'
import { UNAUTHENTICATED_EVENT } from '@/services/api'
import './index.css'

// RA2.2 §3 — wipe the offline read caches (in-memory + IndexedDB + SW runtime
// cache) whenever the session ends, so a shared/lost device can't read cached
// personal data after sign-out. The event fires on explicit logout and on any
// mid-session 401 (api.js).
if (typeof window !== 'undefined') {
  window.addEventListener(UNAUTHENTICATED_EVENT, () => {
    clearOfflineData()
  })
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* RA2.2 §3 — persist the GET query cache to IndexedDB so a cold offline
        launch shows last-loaded data instead of empty skeletons. */}
    <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
      <ToastProvider>
        <BrowserRouter>
          <AuthGate>
            <App />
          </AuthGate>
        </BrowserRouter>
      </ToastProvider>
    </PersistQueryClientProvider>
  </React.StrictMode>
)
