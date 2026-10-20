import {
  Bar,
  Cell,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

import {
  SIGNAL, MUTED, axisProps, gridProps, ChartTooltip, ChartLegend,
} from '@/components/charts/signal'

// The 4-week rolling average (R8.4.2) is context for the signal series, so it
// sits back in a muted dashed line rather than competing in a second hue.
const ROLLING = MUTED

// Bar opacities: history recedes, the latest period reads as the focus. When the
// latest period is still filling up (liveLast), it is dimmed slightly so it reads
// as "still filling" rather than as a finished week.
const HISTORY_OPACITY = 0.55
const LAST_OPACITY = 1
const LIVE_LAST_OPACITY = 0.8

function renderTooltip(d) {
  return (
    <>
      <div className="font-sans font-semibold text-foreground">{d.fullLabel}</div>
      <div>
        {d.total_km.toFixed(1)} km · {d.run_count} run{d.run_count === 1 ? '' : 's'}
      </div>
      {d.rolling_4wk_km != null && <div className="text-faint">4-wk avg {d.rolling_4wk_km.toFixed(1)} km</div>}
    </>
  )
}

/**
 * Volume trend (km per period) in the template's chart language
 * (components/charts/signal): one bar per period over a hairline grid, mono
 * axes. The last bar is the latest period; when `liveLast` (the range ends
 * today, so that period is still filling up) it is drawn slightly dimmer.
 * Data is chronological { label, fullLabel, total_km, run_count }. Weekly data
 * carries `rolling_4wk_km` (server-computed, R8.4.2), drawn as a dashed line
 * over the bars, with a key.
 */
export default function VolumeChart({ data, xTicks, xTickFormatter, liveLast = false }) {
  const showRolling = data.some((d) => d.rolling_4wk_km != null)
  const last = data.length - 1

  return (
    <>
      {/* Height lives on the wrapper: 160px on phones, 220px from sm up. */}
      <div className="h-[160px] sm:h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 12, right: 4, left: 0, bottom: 0 }} barCategoryGap="20%">
            <CartesianGrid {...gridProps} />
            <XAxis
              dataKey="label"
              {...axisProps}
              {...(xTicks ? { ticks: xTicks } : { interval: 'preserveStartEnd' })}
              {...(xTickFormatter ? { tickFormatter: xTickFormatter } : {})}
              tickMargin={8}
            />
            <YAxis
              orientation="right"
              {...axisProps}
              tickFormatter={(v) => `${v} km`}
              width={52}
              tickCount={3}
            />
            <Tooltip
              cursor={{ fill: 'var(--chart-grid)', fillOpacity: 0.6 }}
              content={<ChartTooltip render={renderTooltip} />}
            />
            <Bar
              dataKey="total_km"
              fill={SIGNAL}
              radius={[2, 2, 0, 0]}
              maxBarSize={28}
              isAnimationActive={false}
            >
              {data.map((d, i) => (
                <Cell
                  key={d.period ?? i}
                  fillOpacity={i === last ? (liveLast ? LIVE_LAST_OPACITY : LAST_OPACITY) : HISTORY_OPACITY}
                />
              ))}
            </Bar>
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
      <ChartLegend
        className="mt-3"
        items={[
          { kind: 'bar', label: 'Distance' },
          ...(showRolling ? [{ kind: 'dashed', color: ROLLING, label: '4-week average' }] : []),
        ]}
      />
    </>
  )
}
