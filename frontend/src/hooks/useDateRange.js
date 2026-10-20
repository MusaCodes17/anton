// Date-range state for a page's date pickers (T4b), extracted from the Training
// page so each tab can hold its own range. React state only (resets on nav).
//
// Each bound has two copies: committed (dateFrom/dateTo, which feed queries)
// and drafts (draftFrom/draftTo, bound to the date inputs). Drafts commit to the
// committed pair 400 ms after the last change. Committing per change fired 2
// requests each time (iOS date wheels fire onChange repeatedly while spinning).
// Presets set draft and committed values together, immediately.
import { useEffect, useMemo, useRef, useState } from 'react'

// Local-date ISO strings (YYYY-MM-DD).
export function isoToday() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
export function isoDaysAgo(n) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// `defaultDays` seeds the committed range (365 = the 1y preset, matching the
// claude.ai dashboard's 52-week view, R10.5). `onChange` runs on every commit,
// through the debounce or a preset, so the caller can invalidate paging state.
export function useDateRange({ defaultDays = 365, onChange } = {}) {
  const [dateFrom, setDateFrom] = useState(() => isoDaysAgo(defaultDays))
  const [dateTo, setDateTo] = useState(() => isoToday())
  const [draftFrom, setDraftFrom] = useState(dateFrom)
  const [draftTo, setDraftTo] = useState(dateTo)
  const range = useMemo(() => ({
    ...(dateFrom ? { date_from: dateFrom } : {}),
    ...(dateTo ? { date_to: dateTo } : {}),
  }), [dateFrom, dateTo])

  // Read through a ref so the debounce effect (keyed on drafts only) always calls
  // the latest onChange without re-arming when its identity changes.
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  // A committed range edit invalidates the caller's current paging depth.
  const setRange = (from, to) => {
    setDateFrom(from)
    setDateTo(to)
    onChangeRef.current?.()
  }
  useEffect(() => {
    if (draftFrom === dateFrom && draftTo === dateTo) return
    const t = setTimeout(() => setRange(draftFrom, draftTo), 400)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftFrom, draftTo])
  // Presets set draft and committed values together, immediately.
  const applyPreset = (from, to) => { setDraftFrom(from); setDraftTo(to); setRange(from, to) }

  return { dateFrom, dateTo, draftFrom, draftTo, setDraftFrom, setDraftTo, applyPreset, range }
}
