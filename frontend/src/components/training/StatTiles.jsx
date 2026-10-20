import { RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

/**
 * The stat-tile shell shared by the Training "Now" strip (NowStrip.jsx) and
 * the race readiness checklist (RaceReadiness.jsx): a responsive grid of
 * tiles (muted label, one big value, one short sub-line), plus the matching
 * skeleton and error states. Presentation only; no domain logic lives here.
 */

export const GRID = 'grid grid-cols-2 gap-3 lg:grid-cols-4'

export function Group({ title, children }) {
  return (
    <div className="space-y-2.5">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <div className={GRID}>{children}</div>
    </div>
  )
}

// `tone` colours the value; the word itself always carries the meaning.
export function Tile({ label, value, unit, sub, tone = 'text-foreground', compact = false }) {
  return (
    <div className="panel min-w-0 rounded-2xl border border-border bg-card p-4">
      <div className="line-clamp-2 text-xs text-muted-foreground" title={typeof label === 'string' ? label : undefined}>{label}</div>
      <div className={`mt-1.5 font-heading ${compact ? 'text-lg sm:text-xl' : 'text-2xl sm:text-3xl'} font-bold leading-none tabular-nums ${tone}`}>
        {value}
        {unit && <small className="ml-1 text-xs font-medium tracking-normal text-muted-foreground">{unit}</small>}
      </div>
      {sub && <div className="mt-1.5 text-xs text-muted-foreground">{sub}</div>}
    </div>
  )
}

// `heading = false` renders just the tile grid, for callers that already sit under a heading.
export function TileSkeletons({ title, heading = true }) {
  const tiles = (
    <div className={GRID}>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="panel space-y-2.5 rounded-2xl border border-border bg-card p-4">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-7 w-20" />
          <Skeleton className="h-3 w-24" />
        </div>
      ))}
    </div>
  )
  if (!heading) return tiles
  return (
    <div className="space-y-2.5">
      <Skeleton className="h-4 w-40" aria-label={title} />
      {tiles}
    </div>
  )
}

export function GroupError({ title, error, onRetry }) {
  return (
    <div className="space-y-2.5">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <div className="rounded-2xl border border-border bg-card p-4">
        <p className="text-sm text-destructive">Couldn't load this answer.</p>
        <p className="mt-1 text-xs text-muted-foreground">{error?.message || 'Unable to load data.'}</p>
        {onRetry && (
          <div className="mt-3">
            <Button variant="outline" size="sm" onClick={onRetry}>
              <RefreshCw className="h-4 w-4" /> Try again
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
