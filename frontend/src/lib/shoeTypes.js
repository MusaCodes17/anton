// Shoe-type PRESENTATION only (R2.4). The controlled vocabulary itself (which
// types exist) is backend-owned and fetched via useShoeTypes() — this file no
// longer keeps an independent copy of the list or labels. It holds two pure
// presentation concerns keyed by the canonical snake_case value:
//   - formatShoeType(): the human label, derived by title-casing the value
//     (e.g. 'long_distance_racer' → 'Long Distance Racer').
//   - SHOE_TYPE_BADGE_CLASSES: Tailwind badge colours (design tokens live here,
//     not in the backend vocabulary).

/** Title-case a canonical snake_case shoe_type for display. Falls back to the
 * raw value for anything unexpected (e.g. legacy data), never throwing. */
export function formatShoeType(value) {
  if (!value) return ''
  return value
    .split('_')
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(' ')
}

// Opacity-based colours that work in both light and dark mode.
export const SHOE_TYPE_BADGE_CLASSES = {
  long_distance_racer: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
  short_distance_racer: 'bg-purple-500/15 text-purple-400 border-purple-500/20',
  long_run: 'bg-sky-500/15 text-sky-400 border-sky-500/20',
  tempo: 'bg-orange-500/15 text-orange-400 border-orange-500/20',
  intervals: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/20',
  daily_trainer: 'bg-green-500/15 text-green-400 border-green-500/20',
  trail: 'bg-amber-700/15 text-amber-500 border-amber-700/20',
  recovery: 'bg-teal-500/15 text-teal-400 border-teal-500/20',
}
