import { Activity, Gauge, Timer, BarChart2 } from 'lucide-react'
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts'
import { formatDate } from '@/lib/utils'

// VO₂ max history (R8.4.5) from the trends response's `form.fitness` step
// series (R8.4.1 snapshots). Values only change at a new snapshot, so it's a
// step line. Hidden below 2 readings — one point is not a trend.
function Vo2Sparkline({ history }) {
  const points = (history || []).filter((p) => p.vo2max != null)
  if (points.length < 2) return null
  return (
    <div className="px-4 pb-4">
      <div className="rounded-[14px] border border-border bg-surface px-4 pb-2 pt-3">
        <div className="text-2xs font-medium uppercase tracking-[0.06em] text-faint">
          VO₂ max · {formatDate(points[0].captured_date)} → {formatDate(points[points.length - 1].captured_date)}
        </div>
        <ResponsiveContainer width="100%" height={48}>
          <LineChart data={points} margin={{ top: 6, right: 4, left: 4, bottom: 2 }}>
            <YAxis hide domain={['dataMin - 1', 'dataMax + 1']} />
            <Tooltip
              cursor={{ stroke: 'var(--primary)', strokeOpacity: 0.35, strokeWidth: 1 }}
              content={({ active, payload }) =>
                active && payload?.length ? (
                  <div className="rounded-[10px] border border-border bg-popover px-2.5 py-1.5 text-xs tabular-nums">
                    <div className="font-semibold text-foreground">{formatDate(payload[0].payload.captured_date)}</div>
                    <div className="text-muted-foreground">VO₂ max {payload[0].payload.vo2max}</div>
                  </div>
                ) : null
              }
            />
            <Line
              type="stepAfter"
              dataKey="vo2max"
              stroke="var(--primary)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: 'var(--primary)', stroke: 'var(--card)', strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

/**
 * COROS athlete-level fitness metrics (R2.7 T5, F3): VO2 max, lactate-threshold
 * pace, and running level. Race predictions are split into PredictionsCard (F4).
 * Always rendered in the 2×2 grid — shows an empty state when no snapshot exists.
 * Tiles run two-up at every width, matching PredictionsCard. `history` (optional)
 * is the fitness step series from /api/training/trends, drawn as a sparkline.
 */
export default function FitnessCard({ data, history }) {
  return (
    <div className="rounded-2xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2.5">
          <Activity className="h-4 w-4 text-primary" />
          <span className="font-heading text-md-plus font-bold text-foreground">Fitness</span>
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
        <div className="grid grid-cols-3 gap-2 p-3 sm:grid-cols-2 sm:gap-3 sm:p-4">
          <div className="rounded-[14px] border border-border bg-surface p-3 sm:p-4">
            <div className="flex max-w-[97px] items-center gap-1.5 text-2xs font-medium uppercase tracking-[0.06em] text-faint">
              <Gauge className="h-3 w-3 shrink-0" /> <span className="truncate">VO₂ Max</span>
            </div>
            <div className="mt-1 font-heading text-xl font-extrabold tracking-tight text-foreground tabular-nums sm:text-[26px] sm:leading-[inherit]">
              {data.vo2max != null ? data.vo2max.toFixed(1) : '—'}
            </div>
          </div>
          <div className="rounded-[14px] border border-border bg-surface p-3 sm:p-4">
            <div className="flex max-w-[97px] items-center gap-1.5 text-2xs font-medium uppercase tracking-[0.06em] text-faint">
              <Timer className="h-3 w-3 shrink-0" /> <span className="truncate">Threshold</span>
            </div>
            <div className="mt-1 font-heading text-xl font-extrabold tracking-tight text-foreground tabular-nums sm:text-[26px] sm:leading-[inherit]">
              {data.threshold_pace ?? '—'}
            </div>
          </div>
          <div className="rounded-[14px] border border-border bg-surface p-3 sm:p-4">
            <div className="flex max-w-[97px] items-center gap-1.5 text-2xs font-medium uppercase tracking-[0.06em] text-faint">
              <BarChart2 className="h-3 w-3 shrink-0" /> <span className="truncate">Running Level</span>
            </div>
            <div className="mt-1 font-heading text-xl font-extrabold tracking-tight text-foreground tabular-nums sm:text-[26px] sm:leading-[inherit]">
              {data.running_level != null ? data.running_level.toFixed(1) : '—'}
            </div>
          </div>
        </div>
      )}
      {data?.has_data && <Vo2Sparkline history={history} />}
    </div>
  )
}
