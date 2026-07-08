import { Link } from 'react-router-dom'
import { Footprints, Heart } from 'lucide-react'
import { formatDate, formatDuration } from '@/lib/utils'

const BAND_LABEL = { '5k': '5K', '10k': '10K', half: 'Half', full: 'Full' }

/**
 * One personal-record card for a distance band. Headline is the fastest
 * whole-activity time in that band, with average pace and HR beneath. Honest
 * labelling: whole-activity times, not segment PBs. The date deep-links to the
 * activity's detail/editor (to retag/exclude it), and the shoe chip to the
 * attributed owned shoe.
 */
export default function PBCard({ record }) {
  const { band, total_time_s, avg_pace, avg_hr, run_date, distance_km, shoe, activity_id } = record
  return (
    <div className="flex flex-col gap-3 rounded-[14px] border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="font-heading text-sm font-extrabold uppercase tracking-[0.06em] text-accent-foreground">
          {BAND_LABEL[band] ?? band}
        </span>
        <span className="text-2xs font-medium text-faint">{distance_km.toFixed(2)} km</span>
      </div>

      <div>
        <div className="font-heading text-[26px] font-extrabold tracking-tight text-foreground tabular-nums">
          {formatDuration(total_time_s)}
        </div>
        <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground tabular-nums">
          <span>{avg_pace}</span>
          {avg_hr != null && (
            <span className="inline-flex items-center gap-1">
              <Heart className="h-3 w-3 text-faint" />
              {avg_hr}
            </span>
          )}
        </div>
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 text-xs text-muted-foreground">
        {activity_id != null ? (
          <Link
            to={`/activities/${activity_id}`}
            className="focus-ring rounded font-medium hover:text-foreground hover:underline"
            title="Open activity — retag to exclude from records"
          >
            {run_date ? formatDate(run_date) : 'Open activity'}
          </Link>
        ) : (
          <span>{run_date ? formatDate(run_date) : '—'}</span>
        )}
        {shoe && (
          <Link
            to={`/shoes/${shoe.id}`}
            className="focus-ring inline-flex min-w-0 items-center gap-1 rounded-full border border-border bg-secondary px-2 py-0.5 text-2xs font-medium text-secondary-foreground hover:border-primary/40"
            title={`${shoe.brand} ${shoe.model}`}
          >
            <Footprints className="h-3 w-3 shrink-0" />
            <span className="truncate">{shoe.nickname || shoe.model}</span>
          </Link>
        )}
      </div>
    </div>
  )
}
