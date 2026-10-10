// Refresh on-screen data when the installed app returns to the foreground after
// a long absence (a phone pulled out of a pocket after a run).
//
// Deliberately NOT React Query's refetchOnWindowFocus: that fires on every focus
// and was the refetch storm queryClient.js turns off. Here we refetch only the
// queries mounted on the current screen and already stale, and only after the
// page has been hidden for a meaningful stretch. No polling, no timers.
import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'

// Short tab switches shouldn't refetch; a phone resumed after a real absence should.
export const RESUME_REFRESH_MIN_HIDDEN_MS = 5 * 60 * 1000

export function useResumeRefresh() {
  const queryClient = useQueryClient()

  useEffect(() => {
    let hiddenAt = null

    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        hiddenAt = Date.now()
        return
      }
      // Visible again. Ignore a visible event with no preceding hidden one.
      if (hiddenAt == null) return
      const hiddenFor = Date.now() - hiddenAt
      hiddenAt = null

      // Offline on resume: skip. React Query's own online handling covers later.
      if (hiddenFor < RESUME_REFRESH_MIN_HIDDEN_MS) return
      if (typeof navigator !== 'undefined' && navigator.onLine === false) return

      queryClient.refetchQueries({ type: 'active', stale: true })
    }

    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [queryClient])
}
