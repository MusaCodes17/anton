import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

const GREEN = 'oklch(0.74 0.17 153)'

function VolumeTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-[10px] border border-border bg-popover px-3 py-2 text-xs tabular-nums">
      <div className="font-semibold text-foreground">{d.fullLabel}</div>
      <div className="text-muted-foreground">
        {d.total_km.toFixed(1)} km · {d.run_count} run{d.run_count === 1 ? '' : 's'}
      </div>
    </div>
  )
}

/**
 * Presentational volume trend (km per period), Strava-style: a filled area
 * under a line, open markers at each point, and the latest period accented
 * with a solid dot + halo. Data is expected already chronological with
 * { label, fullLabel, total_km, run_count }. Kept legible at ~340px:
 * ≤12 points, abbreviated x labels, right-hand y-axis, no fixed pixel widths.
 */
export default function VolumeChart({ data, height = 220 }) {
  const lastIndex = data.length - 1

  // Open circles for history, a solid haloed dot for the most recent period —
  // matching the reference. Hollow fill uses the card background so the ring
  // reads as cut out of the area.
  const renderDot = ({ cx, cy, index, key }) => {
    if (cx == null || cy == null) return <g key={key} />
    const isLast = index === lastIndex
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
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 12, right: 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="volumeFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={GREEN} stopOpacity={0.26} />
            <stop offset="100%" stopColor={GREEN} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1E2126" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: '#6A6F76' }}
          stroke="#1E2126"
          fontFamily="JetBrains Mono, monospace"
          interval="preserveStartEnd"
          tickMargin={8}
        />
        <YAxis
          orientation="right"
          tick={{ fontSize: 11, fill: '#6A6F76' }}
          stroke="#1E2126"
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
      </AreaChart>
    </ResponsiveContainer>
  )
}
