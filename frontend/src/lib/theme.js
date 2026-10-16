// Light/dark theme preference (per device). Dark is the default; light is an
// opt-in viewing mode that only re-tones the CSS tokens (index.css,
// :root[data-theme='light']). Stored in localStorage on purpose: it's a
// per-device viewing convenience, not user data worth a server round trip —
// and public/theme-boot.js (the boot script index.html loads) must read it synchronously before the
// first paint. Keep STORAGE_KEY and THEME_COLORS in step with that script.

export const STORAGE_KEY = 'anton-theme'
export const THEMES = ['dark', 'light']

// <meta name="theme-color"> per theme (iOS/Android browser chrome) = --background.
const THEME_COLORS = { dark: '#070a13', light: '#f2f4f9' }

export function getStoredTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark' // storage blocked (private mode): fall back to the default
  }
}

export function applyTheme(theme) {
  const root = document.documentElement
  if (theme === 'light') root.dataset.theme = 'light'
  else delete root.dataset.theme
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLORS[theme])
}

export function storeTheme(theme) {
  try {
    if (theme === 'light') localStorage.setItem(STORAGE_KEY, 'light')
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore — the choice still applies for this session
  }
}
