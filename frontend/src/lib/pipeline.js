// Sentinel for shoes with no shoe_type. Untyped shoes are all one "type" with
// each other, but never the same type as a named type.
const UNTYPED = Symbol('untyped')

/**
 * Pick the rows for the Shoes-page retirement preview.
 *
 * The runner wants breadth, not two of the same kind: the preview takes the
 * first (worst) entry, then the next entry whose shoe_type differs from every
 * type already picked, up to `max`. Order is the incoming order (worst first).
 * A shoe with no type counts as its own type, distinct from every named type;
 * two untyped shoes count as the same type. If nothing differs, only the first
 * entry is returned.
 *
 * @param {Array<{shoe?: {shoe_type?: string|null}}>} entries
 * @param {number} [max=2]
 * @returns {Array} up to `max` entries, in input order
 */
export function pipelinePreview(entries, max = 2) {
  if (!entries?.length || max < 1) return []
  const keyOf = (entry) => entry.shoe?.shoe_type || UNTYPED
  const picked = [entries[0]]
  const seen = new Set([keyOf(entries[0])])
  for (const entry of entries.slice(1)) {
    if (picked.length >= max) break
    const key = keyOf(entry)
    if (seen.has(key)) continue
    seen.add(key)
    picked.push(entry)
  }
  return picked
}
