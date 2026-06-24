import { cn } from '@/lib/utils'

const LIMIT_KM = 800 // personal race-shoe mileage limit; configurable later

/**
 * Mileage progress bar: green under 500km, yellow 500-800km, red beyond.
 * `compact` shows just "Current Mileage: X km" instead of mileage + limit —
 * the bar's color already communicates the limit visually on cards.
 */
export default function MileageProgressBar({ mileage, limit = LIMIT_KM, compact = false, className }) {
  const pct = Math.min(100, (mileage / limit) * 100)
  const colorClass =
    mileage > limit ? 'bg-destructive' : mileage >= limit * 0.625 ? 'bg-warning' : 'bg-success'

  return (
    <div className={cn('space-y-1', className)}>
      <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className={cn('h-full rounded-full transition-all', colorClass)}
          style={{ width: `${pct}%` }}
        />
      </div>
      {compact ? (
        <div className="text-[11px] text-faint">Current Mileage: {Math.round(mileage)} km</div>
      ) : (
        <div className="flex justify-between text-[11px] text-faint">
          <span>{Math.round(mileage)} km</span>
          <span>{limit} km limit</span>
        </div>
      )}
    </div>
  )
}
