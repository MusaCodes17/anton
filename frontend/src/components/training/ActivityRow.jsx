import { Link } from 'react-router-dom'
import { Footprints } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { formatDate } from '@/lib/utils'
import { runSourceVariant, runSourceLabel } from '@/lib/runSource'

// A labelled figure in the stats cluster — value on top, caption below.
function Figure({ value, unit, caption }) {
  return (
    <div className="min-w-[52px]">
      <div className="text-sm font-semibold text-foreground tabular-nums">
        {value ?? '—'}
        {value != null && unit ? <span className="ml-0.5 text-2xs font-normal text-faint">{unit}</span> : null}
      </div>
      <div className="text-2xs uppercase tracking-[0.08em] text-faint">{caption}</div>
    </div>
  )
}

/**
 * One row in the unified activities list: date + name, distance/pace/HR,
 * source badge, and a shoe chip linking to the owned shoe. Stacks into a
 * card on narrow viewports.
 */
export default function ActivityRow({ activity }) {
  const { date, name, distance_km, avg_pace, avg_hr, source, shoe, activity_id, activity_tag } = activity
  return (
    <div className="flex flex-col gap-3 rounded-[14px] border border-border bg-surface p-4 sm:flex-row sm:items-center sm:gap-6">
      {/* Date + name → activity detail (T6) */}
      <Link
        to={activity_id != null ? `/activities/${activity_id}` : '#'}
        className="focus-ring min-w-0 flex-1 rounded-md hover:opacity-80"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-foreground">{formatDate(date)}</span>
          {activity_tag && <Badge variant="outline" className="text-[10px]">{activity_tag}</Badge>}
        </div>
        {name && <div className="mt-0.5 truncate text-xs text-muted-foreground">{name}</div>}
      </Link>

      {/* Figures */}
      <div className="flex items-start gap-5">
        <Figure value={distance_km != null ? distance_km.toFixed(2) : null} unit="km" caption="Dist" />
        <Figure value={avg_pace || null} caption="Pace" />
        <Figure
          value={avg_hr != null ? avg_hr : null}
          unit={avg_hr != null ? 'bpm' : ''}
          caption="Avg HR"
        />
      </div>

      {/* Source + shoe */}
      <div className="flex items-center gap-2 sm:w-[190px] sm:justify-end">
        <Badge variant={runSourceVariant(source)} className="text-[10px]">
          {runSourceLabel(source)}
        </Badge>
        {shoe ? (
          <Link
            to={`/shoes/${shoe.id}`}
            className="focus-ring inline-flex min-w-0 items-center gap-1 rounded-full border border-border bg-secondary px-2 py-0.5 text-2xs font-medium text-secondary-foreground hover:border-primary/40"
            title={`${shoe.brand} ${shoe.model}`}
          >
            <Footprints className="h-3 w-3 shrink-0" />
            <span className="truncate">{shoe.nickname || shoe.model}</span>
          </Link>
        ) : (
          <span className="text-2xs text-faint">No shoe</span>
        )}
      </div>
    </div>
  )
}
