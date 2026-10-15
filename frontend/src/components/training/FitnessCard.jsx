import { Activity, Gauge, Timer, BarChart2 } from 'lucide-react'
import { Area, ComposedChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts'
import {
  SIGNAL, useFillId, SignalFill, endpointDot, activeDot, lineCursor, ChartTooltip, ChartLegend,
} from '@/components/charts/signal'
import { formatDate } from '@/lib/utils'

// VO₂ max history (R8.4.5) from the trends response's `form.fitness` step
// series (R8.4.1 snapshots). Values only change at a new snapshot, so it's a
// step line. Hidden below 2 readings — one point is not a trend.
function Vo2Sparkline({ history }) {
  const fillId = useFillId('vo2')
  const points = (history || []).filter((p) => p.vo2max != null)
  if (points.length < 2) return null
  return (
    <div className="border-t border-border px-5 pb-4 pt-3">
      <div className="flex items-baseline justify-between gap-3">
        <ChartLegend items={[{ kind: 'line', label: 'VO₂ max' }]} />
        <span className="font-mono text-2xs text-faint">
          {formatDate(points[0].captured_date)} → {formatDate(points[points.length - 1].captured_date)}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={56}>
        <ComposedChart data={points} margin={{ top: 8, right: 6, left: 4, bottom: 2 }}>
          <defs>
            <SignalFill id={fillId} />
          </defs>
          <YAxis hide domain={['dataMin - 1', 'dataMax + 1']} />
          <Tooltip
            cursor={lineCursor}
            content={
              <ChartTooltip
                render={(d) => (
                  <>
                    <div className="font-sans font-semibold text-foreground">{formatDate(d.captured_date)}</div>
                    <div>VO₂ max {d.vo2max}</div>
                  </>
                )}
              />
            }
          />
          <Area
            type="stepAfter"
            dataKey="vo2max"
            stroke={SIGNAL}
            strokeWidth={2}
            fill={`url(#${fillId})`}
            dot={endpointDot(points.length - 1)}
            activeDot={activeDot}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function Kpi({ icon: Icon, label, value }) {
  return (
    <div className="min-w-0 px-4 py-4 sm:px-5">
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Icon className="h-3 w-3 shrink-0" /> <span className="truncate">{label}</span>
      </div>
      <div className="mt-0.5 truncate text-lg font-semibold tracking-[-0.01em] text-foreground tabular-nums sm:text-[22px]">
        {value}
      </div>
    </div>
  )
}

/**
 * COROS athlete-level fitness metrics (R2.7 T5, F3): VO2 max, lactate-threshold
 * pace, and running level. Race predictions are split into PredictionsCard (F4).
 * Always rendered in the 2×2 grid — shows an empty state when no snapshot exists.
 * The three figures sit in one hairline-divided row (template .kpis). `history` (optional)
 * is the fitness step series from /api/training/trends, drawn as a sparkline.
 */
export default function FitnessCard({ data, history }) {
  return (
    <div className="panel rounded-2xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2.5">
          <Activity className="h-4 w-4 text-primary" />
          <span className="text-md-plus font-semibold text-foreground">Fitness</span>
        </div>
        {data?.captured_at && (
          <span className="text-2xs text-faint">as of {formatDate(data.captured_at)}</span>
        )}
      </div>

      {!data?.has_data ? (
        <p className="px-5 py-8 text-center text-sm text-muted-foreground">
          No fitness data yet — run the <code className="font-mono text-xs">sync_fitness</code> prompt in Claude Desktop.
        </p>
      ) : (
        // Template .kpis: three figures in one row, split by hairlines.
        <div className="grid grid-cols-3 divide-x divide-border">
          <Kpi icon={Gauge} label="VO₂ max" value={data.vo2max != null ? data.vo2max.toFixed(1) : '—'} />
          <Kpi icon={Timer} label="Threshold" value={data.threshold_pace ?? '—'} />
          <Kpi icon={BarChart2} label="Running level" value={data.running_level != null ? data.running_level.toFixed(1) : '—'} />
        </div>
      )}
      {data?.has_data && <Vo2Sparkline history={history} />}
    </div>
  )
}
