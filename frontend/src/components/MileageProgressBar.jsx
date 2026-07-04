import { cn } from '@/lib/utils'

const DEFAULT_LIMIT_KM = 800 // fallback when a shoe has no mileage_limit set

/**
 * Mileage progress bar scaled to a per-shoe `limit` (owned_shoes.mileage_limit,
 * falling back to 800km): green under 75% of the limit, warning 75–100%, red
 * beyond. `compact` shows just "Current Mileage: X km" instead of mileage +
 * limit — the bar's color already communicates the limit visually on cards.
 */
export default function MileageProgressBar({ mileage, limit = DEFAULT_LIMIT_KM, compact = false, className }) {
  const pct = Math.min(100, (mileage / limit) * 100)
  const colorClass =
    mileage > limit ? 'bg-destructive' : mileage >= limit * 0.75 ? 'bg-warning' : 'bg-success'

  return (
    <div className={cn('space-y-1', className)}>
      <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className={cn('h-full rounded-full transition-all', colorClass)}
          style={{ width: `${pct}%` }}
        />
      </div>
      {compact ? (
        <div className="text-2xs tabular-nums text-faint">Current Mileage: {Math.round(mileage)} km</div>
      ) : (
        <div className="flex justify-between text-2xs tabular-nums text-faint">
          <span>{Math.round(mileage)} km</span>
          <span>{limit} km limit</span>
        </div>
      )}
    </div>
  )
}
