import { useState } from 'react'
import { Trophy } from 'lucide-react'
import PBCard from './PBCard'
import { ErrorState, EmptyState } from '@/components/StatusViews'
import { Skeleton } from '@/components/ui/skeleton'

// R8.1 — two record lists from GET /training/records.
const VIEWS = [
  { key: 'race_pbs', label: 'Race PBs' },
  { key: 'best_efforts', label: 'Best efforts' },
]

/**
 * Card wrapper for the records grid (F4). Two lists behind one toggle: Race
 * PBs (whole runs tagged Race/Parkrun or linked to a race, R8.1) and Best
 * efforts (the fastest stretch inside any run, 1K → Full, R8.2). Both on
 * elapsed time. Two-up at every width, matching PredictionsCard.
 */
export default function RecordsCard({ records }) {
  const [view, setView] = useState('race_pbs')
  const list = records.data?.[view] ?? []

  return (
    <div className="rounded-2xl border border-border bg-card">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
        <div className="flex items-center gap-2.5">
          <Trophy className="h-4 w-4 text-primary" />
          <span className="font-heading text-md-plus font-bold text-foreground">Records</span>
        </div>
        <div className="flex rounded-lg border border-border p-0.5">
          {VIEWS.map((v) => (
            <button
              key={v.key}
              type="button"
              onClick={() => setView(v.key)}
              aria-pressed={view === v.key}
              className={
                'focus-ring rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ' +
                (view === v.key
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:text-foreground')
              }
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>
      <div className="p-4">
        {records.isLoading ? (
          <div className="grid grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-[140px] rounded-[14px]" />
            ))}
          </div>
        ) : records.isError ? (
          <ErrorState error={records.error} onRetry={records.refetch} />
        ) : list.length ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              {list.map((r) => (
                <PBCard key={r.band} record={r} />
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {view === 'race_pbs'
                ? 'Runs tagged Race or Parkrun, or linked to a race. Elapsed time.'
                : 'The fastest stretch inside any run, like a 5k inside a 10k race. Elapsed time.'}
            </p>
          </div>
        ) : view === 'race_pbs' ? (
          <EmptyState
            icon={Trophy}
            title="No race results yet"
            description="Tag a run Race or Parkrun, or link a past race to its run, to see it here."
          />
        ) : (
          <EmptyState icon={Trophy} title="No records yet" description="Log some runs to see your bests." />
        )}
      </div>
    </div>
  )
}
