// Training page section layout: pure helpers (no React, no fetch).

// Must match TRAINING_SECTIONS in backend/app/services/settings.py (ids and
// default order). The server validates; this copy only drives rendering.
export const TRAINING_SECTIONS = ['trends', 'now', 'races', 'records', 'fitness', 'predictions', 'activities']

export const SECTION_LABELS = {
  trends: 'Trends',
  now: 'Now',
  races: 'Races',
  records: 'Records',
  fitness: 'Fitness',
  predictions: 'Predictions',
  activities: 'Activities',
}

// Sections rendered as cards that pair up two-per-row on desktop.
export const CARD_SECTIONS = new Set(['races', 'records', 'fitness', 'predictions'])

/**
 * Same rules as the backend: drop unknown ids and duplicates, append missing
 * ids in default order, keep `hidden` filtered to known ids. null/undefined
 * yields the default layout.
 */
export function normalizeLayout(layout) {
  const known = new Set(TRAINING_SECTIONS)
  const seen = new Set()
  const order = []
  for (const id of layout?.order ?? []) {
    if (known.has(id) && !seen.has(id)) { seen.add(id); order.push(id) }
  }
  for (const id of TRAINING_SECTIONS) if (!seen.has(id)) order.push(id)
  const hidden = []
  for (const id of layout?.hidden ?? []) {
    if (known.has(id) && !hidden.includes(id)) hidden.push(id)
  }
  return { order, hidden }
}

/**
 * Turn an order + hidden list into render blocks. Walks the visible ids in
 * order: a run of consecutive CARD_SECTIONS becomes one `{ kind: 'cards', ids }`
 * block (a 2-up grid on desktop); every other id becomes `{ kind: 'section', id }`.
 * Cards therefore pair up on desktop only when they are adjacent.
 */
export function layoutBlocks(order, hidden = []) {
  const hide = new Set(hidden)
  const blocks = []
  for (const id of order) {
    if (hide.has(id)) continue
    if (CARD_SECTIONS.has(id)) {
      const last = blocks[blocks.length - 1]
      if (last?.kind === 'cards') last.ids.push(id)
      else blocks.push({ kind: 'cards', ids: [id] })
    } else {
      blocks.push({ kind: 'section', id })
    }
  }
  return blocks
}
