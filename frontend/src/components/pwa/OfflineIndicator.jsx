import { WifiOff } from 'lucide-react'
import { useOnline } from '@/hooks/useOnline'

// RA2.2 §3/§4 — honest offline signaling.
//
// When the real connectivity probe (useOnline) reports offline, a subtle
// banner tells the runner the data is last-synced and writes are paused —
// "offline, showing last synced data" over the illusion of live data. Uses the
// warning design token; no new colors. Renders nothing when online.
export default function OfflineIndicator() {
  const { online } = useOnline()
  if (online) return null

  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 bg-warning px-4 py-1.5 text-center text-xs font-semibold text-warning-foreground"
      style={{ paddingTop: 'max(0.375rem, env(safe-area-inset-top))' }}
    >
      <WifiOff className="h-3.5 w-3.5 shrink-0" />
      <span>Offline — showing last synced data. Changes are paused until you reconnect.</span>
    </div>
  )
}
