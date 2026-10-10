import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

const GREEN = 'var(--primary)'
// The 4-week rolling average (R8.4.2) is context for the green series, so it
// sits back in a muted dashed line rather than competing in a second hue.
const ROLLING = 'var(--muted-foreground)'

function VolumeTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-[10px] border border-border bg-popover px-3 py-2 text-xs tabular-nums">
      <div className="font-semibold text-foreground">{d.fullLabel}</div>
      <div className="text-muted-foreground">
        {d.total_km.toFixed(1)} km · {d.run_count} run{d.run_count === 1 ? '' : 's'}
      </div>
      {d.rolling_4wk_km != null && (
        <div className="text-faint">4-wk avg {d.rolling_4wk_km.toFixed(1)} km</div>
      )}
    </div>
  )
}

/**
 * Presentational volume trend (km per period), Strava-style: a filled area
 * under a line, open markers at each point, and the latest period accented
 * with a solid dot + halo. Data is expected already chronological with
 * { label, fullLabel, total_km, run_count }. Kept legible at ~340px:
 * ≤12 points, abbreviated x labels, right-hand y-axis, no fixed pixel widths.
 * Weekly data carries `rolling_4wk_km` (server-computed, R8.4.2), drawn as a
 * dashed trend line with a one-line key; monthly data has none, so no line.
 */
export default function VolumeChart({ data, xTicks, xTickFormatter }) {
  const lastIndex = data.length - 1
  // Dense ranges (e.g. a year of weekly bars) crowd the hollow history markers,
  // so drop them past a threshold and let the line carry the trend. The accented
  // most-recent dot always renders.
  const showHistoryDots = data.length <= 16
  const showRolling = data.some((d) => d.rolling_4wk_km != null)

  // Open circles for history, a solid haloed dot for the most recent period —
  // matching the reference. Hollow fill uses the card background so the ring
  // reads as cut out of the area.
  const renderDot = ({ cx, cy, index, key }) => {
    if (cx == null || cy == null) return <g key={key} />
    const isLast = index === lastIndex
    if (!isLast && !showHistoryDots) return <g key={key} />
    return (
      <g key={key}>
        {isLast && <circle cx={cx} cy={cy} r={9} fill={GREEN} fillOpacity={0.18} />}
        <circle
          cx={cx}
          cy={cy}
          r={isLast ? 5 : 3.5}
          fill={isLast ? GREEN : 'var(--card)'}
          stroke={GREEN}
          strokeWidth={2}
        />
      </g>
    )
  }

  return (
    <>
      {/* Height lives on the wrapper: 160px on phones, 220px from sm up. */}
      <div className="h-[160px] sm:h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 12, right: 4, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="volumeFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={GREEN} stopOpacity={0.26} />
                <stop offset="100%" stopColor={GREEN} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: 'var(--faint)' }}
              stroke="var(--chart-grid)"
              fontFamily="JetBrains Mono, monospace"
              {...(xTicks ? { ticks: xTicks } : { interval: 'preserveStartEnd' })}
              {...(xTickFormatter ? { tickFormatter: xTickFormatter } : {})}
              tickMargin={8}
            />
            <YAxis
              orientation="right"
              tick={{ fontSize: 11, fill: 'var(--faint)' }}
              stroke="var(--chart-grid)"
              fontFamily="JetBrains Mono, monospace"
              tickFormatter={(v) => `${v} km`}
              width={52}
              tickCount={3}
            />
            <Tooltip cursor={{ stroke: GREEN, strokeOpacity: 0.35, strokeWidth: 1 }} content={<VolumeTooltip />} />
            <Area
              type="monotone"
              dataKey="total_km"
              stroke={GREEN}
              strokeWidth={2.5}
              fill="url(#volumeFill)"
              dot={renderDot}
              activeDot={{ r: 5, fill: GREEN, stroke: 'var(--card)', strokeWidth: 2 }}
              isAnimationActive={false}
            />
            {showRolling && (
              <Line
                type="monotone"
                dataKey="rolling_4wk_km"
                stroke={ROLLING}
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
                activeDot={false}
                isAnimationActive={false}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {showRolling && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-faint">
          <svg width="18" height="6" aria-hidden="true">
            <line x1="0" y1="3" x2="18" y2="3" stroke={ROLLING} strokeWidth="1.5" strokeDasharray="4 3" />
          </svg>
          4-week average
        </div>
      )}
    </>
  )
}
