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
  // Phones: two grid rows, [date + name | source + shoe] then [figures].
  // sm+: the original single flex row, unchanged.
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 gap-y-2 rounded-[14px] border border-border bg-surface p-3 sm:flex sm:flex-row sm:gap-6 sm:p-4">
      {/* Date + name → activity detail (T6) */}
      <Link
        to={activity_id != null ? `/activities/${activity_id}` : '#'}
        className="focus-ring col-start-1 row-start-1 min-w-0 flex-1 rounded-md hover:opacity-80 sm:col-auto sm:row-auto"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-foreground">{formatDate(date)}</span>
          {activity_tag && <Badge variant="outline" className="text-[10px]">{activity_tag}</Badge>}
        </div>
        {name && <div className="mt-0.5 truncate text-xs text-muted-foreground">{name}</div>}
      </Link>

      {/* Figures */}
      <div className="col-span-2 row-start-2 flex items-start gap-5 sm:col-auto sm:row-auto">
        <Figure value={distance_km != null ? distance_km.toFixed(2) : null} unit="km" caption="Dist" />
        <Figure value={avg_pace || null} caption="Pace" />
        <Figure
          value={avg_hr != null ? avg_hr : null}
          unit={avg_hr != null ? 'bpm' : ''}
          caption="Avg HR"
        />
      </div>

      {/* Source + shoe */}
      <div className="col-start-2 row-start-1 flex min-w-0 max-w-[60%] items-center justify-end gap-2 sm:col-auto sm:row-auto sm:max-w-none sm:w-[190px]">
        <Badge variant={runSourceVariant(source)} className="shrink-0 text-[10px]">
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
