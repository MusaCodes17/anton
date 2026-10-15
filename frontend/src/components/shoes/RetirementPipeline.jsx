import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowRight, CheckCircle2, Footprints, Tag } from 'lucide-react'
import MileageProgressBar from '@/components/MileageProgressBar'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { forecastLabel } from '@/lib/forecast'

/**
 * The retirement pipeline — ONE component for Home, the Shoes page and
 * /shoes/pipeline, so the three never disagree on title, rows or details
 * (Signal redesign follow-up, 2026-10-15).
 *
 * `entries` is what to render (callers pass `pipelinePreview(...)` for the
 * two-row preview, or the full list on /shoes/pipeline); each entry is
 * `{ pct, current_mileage, mileage_limit, replacement_deals, forecast fields,
 * shoe: { id, brand, model, nickname, shoe_type, image_url, matched_image_url } }`.
 * `total` is the whole pipeline size (badge + "See all N"). With no entries it
 * renders the healthy state — callers that would rather hide it just don't
 * render it.
 */
export default function RetirementPipeline({ entries, total = entries.length, seeAllTo }) {
  return (
    <section className="panel flex flex-col rounded-2xl border border-border bg-card">
      {/* Same head as Home's module panels: icon, title, count, link. */}
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-5 sm:py-3.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <AlertTriangle className="h-4 w-4 shrink-0 text-warning" />
          <h2 className="truncate text-md-plus font-semibold text-foreground">Retirement pipeline</h2>
          {total > 0 && <Badge variant="warning">{total}</Badge>}
        </div>
        {seeAllTo && total > 0 && (
          <Button variant="ghost" size="sm" asChild>
            <Link to={seeAllTo}>
              {/* The badge already carries the count; phones drop it here so
                  the title never truncates at 375px. */}
              See all<span className="hidden sm:inline">&nbsp;{total}</span> <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        )}
      </div>

      <div className="px-4 pb-1 pt-3 sm:px-5">
        {entries.length ? (
          <>
            <p className="text-xs text-muted-foreground">
              Past 75% of their mileage limit — worst first. Time to plan a replacement.
            </p>
            <div className="mt-1 divide-y divide-border">
              {entries.map((entry) => (
                <PipelineRow key={entry.shoe.id} entry={entry} />
              ))}
            </div>
          </>
        ) : (
          <div className="flex items-center gap-2.5 pb-3 text-sm text-muted-foreground">
            <CheckCircle2 className="h-4 w-4 text-success" />
            <span>Rotation healthy — no shoes near their mileage limit.</span>
          </div>
        )}
      </div>
    </section>
  )
}

function PipelineRow({ entry }) {
  const { shoe, pct, current_mileage, mileage_limit, replacement_deals } = entry
  const forecast = forecastLabel(entry)
  const image = shoe.image_url || shoe.matched_image_url
  const overLimit = pct >= 1

  return (
    <div className="flex flex-col gap-3 py-3.5 sm:flex-row sm:items-center sm:gap-4">
      <Link to={`/shoes/${shoe.id}`} className="focus-ring group flex min-w-0 flex-1 items-center gap-3 rounded-[10px]">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-[9px] bg-placeholder-stripes">
          {image ? (
            <img src={image} alt={shoe.model} className="h-full w-full object-contain" />
          ) : (
            <Footprints className="h-5 w-5 text-faint" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="max-w-full truncate text-sm font-semibold text-foreground transition-colors duration-300 ease-signal group-hover:text-primary">
              {shoe.nickname || `${shoe.brand} ${shoe.model}`}
            </span>
            <Badge variant={overLimit ? 'destructive' : 'warning'} className="shrink-0">
              {overLimit ? 'Over limit · ' : ''}{Math.round(pct * 100)}%
            </Badge>
          </div>
          <div className="mt-2 max-w-[280px]">
            <MileageProgressBar mileage={current_mileage} limit={mileage_limit} />
          </div>
          {forecast && <div className="mt-1 font-mono text-2xs text-muted-foreground">{forecast}</div>}
        </div>
      </Link>
      <div className="shrink-0 pl-14 sm:pl-0">
        {replacement_deals > 0 ? (
          <Button asChild variant="outline" size="sm">
            <Link to="/deals">
              <Tag className="h-3.5 w-3.5" />
              {replacement_deals} replacement deal{replacement_deals === 1 ? '' : 's'}
            </Link>
          </Button>
        ) : (
          <span className="text-2xs text-faint">No replacement deals yet</span>
        )}
      </div>
    </div>
  )
}
