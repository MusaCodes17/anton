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

import {
  SIGNAL, MUTED, axisProps, gridProps, useFillId, SignalFill, endpointDot,
  activeDot, lineCursor, ChartTooltip, ChartLegend,
} from '@/components/charts/signal'

// The 4-week rolling average (R8.4.2) is context for the signal series, so it
// sits back in a muted dashed line rather than competing in a second hue.
const ROLLING = MUTED

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
 * (components/charts/signal): a signal line over a gradient area, hairline
 * grid, mono axes, and the latest period as a glowing endpoint — pulsing only
 * when `liveLast` (the range ends today, so that period is still filling up).
 * Data is chronological { label, fullLabel, total_km, run_count }. Weekly data
 * carries `rolling_4wk_km` (server-computed, R8.4.2), drawn dashed with a key.
 */
export default function VolumeChart({ data, xTicks, xTickFormatter, liveLast = false }) {
  const fillId = useFillId('volume')
  const showRolling = data.some((d) => d.rolling_4wk_km != null)

  return (
    <>
      {/* Height lives on the wrapper: 160px on phones, 220px from sm up. */}
      <div className="h-[160px] sm:h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 12, right: 4, left: 0, bottom: 0 }}>
            <defs>
              <SignalFill id={fillId} />
            </defs>
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
            <Tooltip cursor={lineCursor} content={<ChartTooltip render={renderTooltip} />} />
            <Area
              type="monotone"
              dataKey="total_km"
              stroke={SIGNAL}
              strokeWidth={2}
              strokeLinecap="round"
              fill={`url(#${fillId})`}
              dot={endpointDot(data.length - 1, { live: liveLast })}
              activeDot={activeDot}
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
      <ChartLegend
        className="mt-3"
        items={[
          { kind: 'line', label: 'Distance' },
          ...(showRolling ? [{ kind: 'dashed', color: ROLLING, label: '4-week average' }] : []),
        ]}
      />
    </>
  )
}
