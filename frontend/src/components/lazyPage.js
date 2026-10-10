import React from 'react'

// Route pages are split into chunks whose hashes change on every deploy. A tab
// left open across a deploy (or a PWA serving an old index) asks for chunks the
// new build deleted, so the import rejects. One reload fetches the fresh index;
// the sessionStorage flag stops a reload loop when the failure is real.
// Lives in components/ (not lib/) because it wraps React.lazy.
const FLAG = 'anton:chunk-reload'

export function lazyPage(loader) {
  return React.lazy(() =>
    loader()
      .then((mod) => {
        // Successful load: clear the flag so a later deploy can reload once more.
        try {
          sessionStorage.removeItem(FLAG)
        } catch {
          /* storage unavailable: nothing to clear */
        }
        return mod
      })
      .catch((err) => {
        // If storage is unavailable, assume we already reloaded: rethrow, never loop.
        let reloaded = true
        try {
          reloaded = sessionStorage.getItem(FLAG) === '1'
        } catch {
          /* keep reloaded = true */
        }
        if (reloaded) {
          try {
            sessionStorage.removeItem(FLAG)
          } catch {
            /* ignore */
          }
          throw err
        }
        try {
          sessionStorage.setItem(FLAG, '1')
        } catch {
          /* ignore: worst case the next failure rethrows */
        }
        window.location.reload()
        // Never resolve: React keeps the Suspense fallback while the page reloads.
        return new Promise(() => {})
      })
  )
}
