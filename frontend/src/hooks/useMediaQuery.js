// Tracks a CSS media query (e.g. '(min-width: 768px)') as a boolean.
//
// Used to mount desktop-only UI conditionally: an element hidden with CSS on
// phones still mounts its hooks and fixed overlays, so the phone never needs it.
import { useEffect, useState } from 'react'

function getMatch(query) {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(query).matches
    : false
}

export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => getMatch(query))

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mql = window.matchMedia(query)
    const onChange = (e) => setMatches(e.matches)
    setMatches(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])

  return matches
}

export default useMediaQuery
