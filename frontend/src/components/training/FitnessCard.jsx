import { Activity, Gauge, Timer, BarChart2 } from 'lucide-react'
import { formatDate } from '@/lib/utils'

/**
 * COROS athlete-level fitness metrics (R2.7 T5, F3): VO2 max, lactate-threshold
 * pace, and running level. Race predictions are split into PredictionsCard (F4).
 * Always rendered in the 2×2 grid — shows an empty state when no snapshot exists.
 */
export default function FitnessCard({ data }) {
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
        <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-3">
          <div className="rounded-[14px] border border-border bg-surface p-4">
            <div className="flex items-center gap-1.5 text-2xs font-medium uppercase tracking-[0.06em] text-faint">
              <Gauge className="h-3 w-3" /> VO₂ Max
            </div>
            <div className="mt-1 font-heading text-[26px] font-extrabold tracking-tight text-foreground tabular-nums">
              {data.vo2max != null ? data.vo2max.toFixed(1) : '—'}
            </div>
          </div>
          <div className="rounded-[14px] border border-border bg-surface p-4">
            <div className="flex items-center gap-1.5 text-2xs font-medium uppercase tracking-[0.06em] text-faint">
              <Timer className="h-3 w-3" /> Threshold
            </div>
            <div className="mt-1 font-heading text-[26px] font-extrabold tracking-tight text-foreground tabular-nums">
              {data.threshold_pace ?? '—'}
            </div>
          </div>
          <div className="rounded-[14px] border border-border bg-surface p-4">
            <div className="flex items-center gap-1.5 text-2xs font-medium uppercase tracking-[0.06em] text-faint">
              <BarChart2 className="h-3 w-3" /> Running Level
            </div>
            <div className="mt-1 font-heading text-[26px] font-extrabold tracking-tight text-foreground tabular-nums">
              {data.running_level != null ? data.running_level.toFixed(1) : '—'}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
