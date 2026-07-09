import { Trophy } from 'lucide-react'
import PBCard from './PBCard'
import { ErrorState, EmptyState } from '@/components/StatusViews'
import { Skeleton } from '@/components/ui/skeleton'

/**
 * Card wrapper for the personal-best records grid (F4 — extracted from the
 * inline Training.jsx Records section into the standard card shell).
 */
export default function RecordsCard({ records }) {
  return (
    <div className="rounded-2xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2.5">
          <Trophy className="h-4 w-4 text-primary" />
          <span className="font-heading text-md-plus font-bold text-foreground">Records</span>
        </div>
        <span className="text-2xs text-faint">fastest whole-activity · not segment PBs</span>
      </div>
      <div className="p-4">
        {records.isLoading ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-[140px] rounded-[14px]" />
            ))}
          </div>
        ) : records.isError ? (
          <ErrorState error={records.error} onRetry={records.refetch} />
        ) : records.data?.records?.length ? (
          <div className="space-y-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {records.data.records.map((r) => (
                <PBCard key={r.band} record={r} />
              ))}
            </div>
            {records.data.excluded_count > 0 && (
              <p className="text-xs text-muted-foreground">
                {records.data.excluded_count}{' '}
                {records.data.excluded_count === 1 ? 'activity' : 'activities'} excluded
                {' '}({records.data.excluded_reason}) — tag interval/track sessions to reconsider.
              </p>
            )}
          </div>
        ) : (
          <EmptyState icon={Trophy} title="No records yet" description="Log some runs to see your bests." />
        )}
      </div>
    </div>
  )
}
