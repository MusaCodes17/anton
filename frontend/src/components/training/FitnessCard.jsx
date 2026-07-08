import { Activity, Gauge, Timer } from 'lucide-react'
import { formatDuration, formatDate } from '@/lib/utils'

// Standard race distances the card predicts, in the key form the backend stores
// (distance_km as a string). Matched loosely so 21.0975/42.195 line up.
const PREDICTION_DISTANCES = [
  { label: '5K', keys: ['5.0', '5'] },
  { label: '10K', keys: ['10.0', '10'] },
  { label: 'Half', keys: ['21.0975', '21.1', '21'] },
  { label: 'Full', keys: ['42.195', '42.2', '42'] },
]

function predictionFor(preds, keys) {
  if (!preds) return null
  for (const k of keys) if (preds[k] != null) return preds[k]
  return null
}

/**
 * The most recent COROS fitness snapshot (R2.7 T5): VO2 max, lactate-threshold
 * pace, and predicted race times across standard distances. Read-only — the
 * snapshot is recorded by the COROS sync agent.
 */
export default function FitnessCard({ data }) {
  const preds = PREDICTION_DISTANCES
    .map((d) => ({ label: d.label, s: predictionFor(data.race_predictions, d.keys) }))
    .filter((d) => d.s != null)

  return (
    <div className="rounded-2xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2.5">
          <Activity className="h-4 w-4 text-primary" />
          <span className="font-heading text-md-plus font-bold text-foreground">Fitness</span>
        </div>
        {data.captured_at && (
          <span className="text-2xs text-faint">as of {formatDate(data.captured_at)}</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-4">
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
        {preds.map((p) => (
          <div key={p.label} className="rounded-[14px] border border-border bg-surface p-4">
            <div className="text-2xs font-medium uppercase tracking-[0.06em] text-faint">{p.label} pred.</div>
            <div className="mt-1 font-heading text-[26px] font-extrabold tracking-tight text-foreground tabular-nums">
              {formatDuration(p.s)}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
