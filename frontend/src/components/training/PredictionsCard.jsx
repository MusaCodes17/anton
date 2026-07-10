import { Target } from 'lucide-react'
import { formatDuration } from '@/lib/utils'

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
      <div className="flex items-center border-b border-border px-5 py-3">
        <Target className="h-4 w-4 text-primary" />
        <span className="ml-2.5 font-heading text-md-plus font-bold text-foreground">Predictions</span>
      </div>
      {preds.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-muted-foreground">
          No race predictions yet — run the <code className="font-mono text-xs">sync_fitness</code> prompt in Claude Desktop.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-3 p-4">
          {preds.map((p) => (
            <div key={p.label} className="rounded-[14px] border border-border bg-surface p-4">
              <div className="text-2xs font-medium uppercase tracking-[0.06em] text-faint">{p.label}</div>
              <div className="mt-1 font-heading text-[26px] font-extrabold tracking-tight text-foreground tabular-nums">
                {formatDuration(p.s)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
