import { Target } from 'lucide-react'
import { formatDate, formatDuration } from '@/lib/utils'

const PREDICTION_DISTANCES = [
  { label: '5K',   keys: ['5.0', '5'] },
  { label: '10K',  keys: ['10.0', '10'] },
  { label: 'Half', keys: ['21.0975', '21.1', '21'] },
  { label: 'Full', keys: ['42.195', '42.2', '42'] },
]

function predictionFor(preds, keys) {
  if (!preds) return null
  for (const k of keys) if (preds[k] != null) return preds[k]
  return null
}

/**
 * Race predictions extracted from the COROS fitness snapshot (F4 split from
 * FitnessCard). Shows predicted times across standard distances. Empty state
 * when no fitness snapshot has been recorded.
 */
export default function PredictionsCard({ data }) {
  const preds = PREDICTION_DISTANCES
    .map((d) => ({ label: d.label, s: predictionFor(data?.race_predictions, d.keys) }))
    .filter((d) => d.s != null)

  return (
    <div className="rounded-2xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2.5">
          <Target className="h-4 w-4 text-primary" />
          <span className="font-heading text-md-plus font-bold text-foreground">Predictions</span>
        </div>
        {/* Freshness (R8.4.5): predictions come from the same COROS snapshot. */}
        {preds.length > 0 && data?.captured_at && (
          <span className="text-2xs text-faint">as of {formatDate(data.captured_at)}</span>
        )}
      </div>
      {preds.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-muted-foreground">
          No race predictions yet — run the <code className="font-mono text-xs">sync_fitness</code> prompt in Claude Desktop.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-3 p-4">
          {preds.map((p) => (
            <div key={p.label} className="rounded-[14px] border border-border bg-surface p-3 sm:p-4">
              <div className="text-2xs font-medium uppercase tracking-[0.06em] text-faint">{p.label}</div>
              <div className="mt-1 font-heading text-xl font-extrabold tracking-tight text-foreground tabular-nums sm:text-[26px] sm:leading-[inherit]">
                {formatDuration(p.s)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
