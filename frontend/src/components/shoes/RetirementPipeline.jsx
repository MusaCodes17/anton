import { Link } from 'react-router-dom'
import { AlertTriangle, Footprints, Tag } from 'lucide-react'
import MileageProgressBar from '@/components/MileageProgressBar'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { forecastLabel } from '@/lib/forecast'

// Shoes past 75% of their limit, worst first. `entries` is what to render;
// `total` is the full pipeline size shown in the badge. When `seeAllTo` is set
// and there are more entries than shown, a "See all N" link opens the full list.
export default function RetirementPipeline({ entries, total = entries.length, onOpenDetail, seeAllTo }) {
  return (
    <section className="rounded-[14px] border border-warning/30 bg-warning/5 p-4">
      <div className="mb-1.5 flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-warning" />
        <h2 className="font-heading text-sm font-bold text-foreground">Retirement pipeline</h2>
        <Badge variant="warning">{total}</Badge>
        {seeAllTo && total > entries.length && (
          <Link
            to={seeAllTo}
            className="focus-ring ml-auto rounded text-xs font-semibold text-accent-foreground hover:underline"
          >
            See all {total} →
          </Link>
        )}
      </div>
      <p className="mb-3.5 text-xs text-muted-foreground">
        Past 75% of their mileage limit — worst first. Time to plan a replacement.
      </p>
      <div className="space-y-2.5">
        {entries.map((entry) => (
          <PipelineRow key={entry.owned_shoe_id} entry={entry} onOpenDetail={onOpenDetail} />
        ))}
      </div>
    </section>
  )
}

function PipelineRow({ entry, onOpenDetail }) {
  const { shoe, pct, current_mileage, mileage_limit, replacement_deals } = entry
  const forecast = forecastLabel(entry)
  const image = shoe.image_url || shoe.matched_image_url
  const overLimit = pct >= 1

  return (
    <div className="flex flex-col gap-3 rounded-[11px] border border-border bg-surface p-3 sm:flex-row sm:items-center">
      <button
        type="button"
        onClick={() => onOpenDetail(shoe.id)}
        className="focus-ring flex min-w-0 flex-1 items-center gap-3 rounded-lg text-left"
      >
        <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-[9px] bg-placeholder-stripes">
          {image ? (
            <img src={image} alt={shoe.model} className="h-full w-full object-contain" />
          ) : (
            <Footprints className="h-5 w-5 text-faint" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-heading text-sm font-bold text-foreground">
              {shoe.nickname || `${shoe.brand} ${shoe.model}`}
            </span>
            <Badge variant={overLimit ? 'destructive' : 'warning'}>{Math.round(pct * 100)}%</Badge>
          </div>
          <div className="mt-1.5 max-w-[240px]">
            <MileageProgressBar mileage={current_mileage} limit={mileage_limit} />
          </div>
          {forecast && <div className="mt-1 text-2xs text-muted-foreground">{forecast}</div>}
        </div>
      </button>
      <div className="shrink-0 sm:pl-2">
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
