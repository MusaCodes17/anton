// The current theme ('dark' | 'light') and a toggle. State lives on <html
// data-theme> (set before paint by index.html); this hook mirrors it, persists
// changes (lib/theme.js) and keeps every mounted toggle — sidebar and phone
// header — in sync via a window event.
import { useCallback, useEffect, useState } from 'react'
import { applyTheme, getStoredTheme, storeTheme } from '@/lib/theme'

const THEME_EVENT = 'anton:theme'

export function useTheme() {
  const [theme, setThemeState] = useState(getStoredTheme)

  useEffect(() => {
    const onChange = (e) => setThemeState(e.detail)
    window.addEventListener(THEME_EVENT, onChange)
    return () => window.removeEventListener(THEME_EVENT, onChange)
  }, [])

  const setTheme = useCallback((next) => {
    applyTheme(next)
    storeTheme(next)
    window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: next }))
  }, [])

  const toggleTheme = useCallback(
    () => setTheme(getStoredTheme() === 'light' ? 'dark' : 'light'),
    [setTheme]
  )

  return { theme, setTheme, toggleTheme }
}

export default useTheme
