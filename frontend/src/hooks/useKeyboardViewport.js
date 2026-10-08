import { useEffect } from 'react'

// iOS (Safari and the installed PWA) does not shrink 100dvh when the on-screen
// keyboard opens: it overlays the keyboard and pans the whole page up to keep
// the focused field visible, which pushes the fixed shell's header off-screen
// and leaves the chat composer floating mid-page. visualViewport is the only
// API that reports the space actually left above the keyboard.
//
// While the keyboard is up this hook:
//   - sets --app-height on <html> to the visible height (Layout's shell uses
//     it, falling back to 100dvh when unset),
//   - adds html.keyboard-open so components can drop safe-area padding the
//     keyboard already covers,
//   - pins the page at scroll 0, undoing iOS's pan.
// Android Chrome resizes the layout viewport itself (see the
// interactive-widget meta in index.html), so the gap below stays ~0 there and
// this hook is a no-op.
const KEYBOARD_MIN_PX = 150 // heuristic: smaller gaps are toolbars, not a keyboard

export function useKeyboardViewport() {
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv) return
    const root = document.documentElement

    const update = () => {
      // Pinch-zoom also shrinks the visual viewport; only react at scale 1.
      const zoomed = Math.abs(vv.scale - 1) > 0.01
      const open = !zoomed && window.innerHeight - vv.height > KEYBOARD_MIN_PX
      if (open) {
        root.style.setProperty('--app-height', `${Math.round(vv.height)}px`)
        root.classList.add('keyboard-open')
        if (window.scrollY !== 0) window.scrollTo(0, 0)
      } else {
        root.style.removeProperty('--app-height')
        root.classList.remove('keyboard-open')
      }
    }

    vv.addEventListener('resize', update)
    vv.addEventListener('scroll', update)
    update()
    return () => {
      vv.removeEventListener('resize', update)
      vv.removeEventListener('scroll', update)
      root.style.removeProperty('--app-height')
      root.classList.remove('keyboard-open')
    }
  }, [])
}
