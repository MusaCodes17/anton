import { useId } from 'react'

/**
 * Signal chart kit — the template's chart language (redesign-template.html
 * `.chart` / `.legend`) for recharts, so every graph in Anton reads the same:
 *
 *  - hairline horizontal grid, no axis lines, mono axis labels;
 *  - the series as a 2px signal line over a soft signal gradient area;
 *  - a threshold as a dashed alert line with a mono alert label;
 *  - the latest point as a glowing dot — with a pulse ring ONLY when that point
 *    is still live (an in-progress week), per the surface brief;
 *  - a mono legend with drawn swatches instead of recharts' default legend.
 *
 * Presentation only: every number still comes from the server.
 */

export const SIGNAL = 'var(--primary)'
export const ALERT = 'var(--destructive)'
export const MUTED = 'var(--muted-foreground)'
const MONO = 'IBM Plex Mono, ui-monospace, monospace'

/** Spread onto <XAxis>/<YAxis>: mono 10.5px muted labels, no axis or tick lines. */
export const axisProps = {
  tick: { fontSize: 10.5, fill: 'var(--muted-foreground)', fontFamily: MONO },
  axisLine: false,
  tickLine: false,
}

/** Spread onto <CartesianGrid>: solid hairlines, horizontal only. */
export const gridProps = { stroke: 'var(--chart-grid)', vertical: false }

/** A unique, SVG-safe gradient id per chart instance (several charts per page). */
export function useFillId(prefix) {
  return `${prefix}-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
}

/** <defs> child: the template's area fill — signal fading to nothing. */
export function SignalFill({ id, color = SIGNAL }) {
  return (
    <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor={color} stopOpacity={0.32} />
      <stop offset="60%" stopColor={color} stopOpacity={0.08} />
      <stop offset="100%" stopColor={color} stopOpacity={0} />
    </linearGradient>
  )
}

/**
 * recharts `dot` renderer: nothing on history points, a glowing endpoint on
 * the last one, plus the pulse ring when `live` (the point is still changing).
 */
export function endpointDot(lastIndex, { live = false, color = SIGNAL } = {}) {
  return function EndpointDot({ cx, cy, index, key }) {
    if (index !== lastIndex || cx == null || cy == null) return <g key={key} />
    return (
      <g key={key}>
        {live && <circle className="chart-ring" cx={cx} cy={cy} r={4} fill={color} opacity={0.25} />}
        <circle className="chart-dot" cx={cx} cy={cy} r={4} fill={color} />
      </g>
    )
  }
}

/** activeDot for hovered points: the same glowing dot, cut out of the panel. */
export const activeDot = { r: 4.5, fill: SIGNAL, stroke: 'var(--card)', strokeWidth: 2 }

/** Hover cursor: a faint signal hairline. */
export const lineCursor = { stroke: SIGNAL, strokeOpacity: 0.35, strokeWidth: 1 }

/** Props for a <ReferenceLine> drawn as the template's threshold marker. */
export function thresholdProps(label, { color = ALERT, position = 'insideTopRight' } = {}) {
  return {
    stroke: color,
    strokeDasharray: '3 4',
    strokeOpacity: 0.7,
    ifOverflow: 'extendDomain',
    label: { value: label, position, fontSize: 10.5, fontFamily: MONO, fill: color },
  }
}

/** Tooltip content shell: a small ink panel with a mono body. */
export function ChartTooltip({ active, payload, render }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-[10px] border border-input bg-popover px-3 py-2 font-mono text-xs text-secondary-foreground shadow-[0_20px_40px_-20px_rgba(0,0,0,0.9)]">
      {render(payload[0].payload, payload)}
    </div>
  )
}

/**
 * Template `.legend`: mono 11px items with drawn swatches.
 * kind: 'line' | 'dashed' | 'threshold' | 'band' | 'bar'
 */
export function ChartLegend({ items, className = '' }) {
  return (
    <div className={`flex flex-wrap gap-x-[18px] gap-y-2 font-mono text-2xs text-muted-foreground ${className}`}>
      {items.map(({ kind = 'line', color = SIGNAL, label }) => (
        <span key={label} className="inline-flex items-center gap-[7px]">
          <Swatch kind={kind} color={color} />
          {label}
        </span>
      ))}
    </div>
  )
}

function Swatch({ kind, color }) {
  if (kind === 'band' || kind === 'bar') {
    return <i aria-hidden="true" className="inline-block h-2 w-3 rounded-[2px]" style={{ background: color, opacity: kind === 'band' ? 0.3 : 1 }} />
  }
  if (kind === 'dashed' || kind === 'threshold') {
    const dash = kind === 'threshold' ? '3 3' : '4 3'
    return (
      <svg width="14" height="4" aria-hidden="true">
        <line x1="0" y1="2" x2="14" y2="2" stroke={color} strokeWidth="1.5" strokeDasharray={dash} />
      </svg>
    )
  }
  return <i aria-hidden="true" className="inline-block h-[2px] w-3 rounded-full" style={{ background: color }} />
}
