import { Link } from 'react-router-dom'
import { Tag, Footprints, ArrowRight } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import StatCard from '@/components/StatCard'
import ScrapeButton from '@/components/ScrapeButton'
import TrainingVolumeCard from '@/components/TrainingVolumeCard'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorState, EmptyState, CardSkeletonGrid, RowSkeleton } from '@/components/StatusViews'
import { useDashboardStats, useRecentDeals, useBestDeals } from '@/hooks/useApi'
import { formatCurrency, formatPercent, formatRelativeTime } from '@/lib/utils'

export default function Dashboard() {
  const stats = useDashboardStats()
  const recent = useRecentDeals(6)
  const best = useBestDeals(4)
  const s = stats.data
  const biggest = best.data?.[0]

  return (
    <div className="space-y-7">
      <PageHeader eyebrow="DASHBOARD" title="Top deals">
        <ScrapeButton />
      </PageHeader>

      {stats.isError ? (
        <ErrorState error={stats.error} onRetry={stats.refetch} />
      ) : (
        <div className="grid grid-cols-2 gap-3.5 lg:grid-cols-4">
          <StatCard
            label="Active deals"
            value={s?.active_deals ?? 0}
            hint={s ? `${s.total_shoes} shoes tracked` : undefined}
            loading={stats.isLoading}
          />
          <StatCard
            label="Biggest discount"
            value={biggest ? `${formatPercent(biggest.savings_percent)}` : '—'}
            hint={
              biggest
                ? `${biggest.shoe?.brand ?? ''} · ${
                    typeof biggest.retailer === 'string' ? biggest.retailer : biggest.retailer?.name
                  }`
                : undefined
            }
            loading={best.isLoading}
          />
          <StatCard
            label="Avg. savings"
            value={s?.average_savings != null ? formatCurrency(s.average_savings) : '—'}
            hint="per active deal"
            loading={stats.isLoading}
          />
          <StatCard
            label="Retailers"
            value={s?.active_retailers ?? 0}
            hint={s ? `${s.total_retailers} total` : undefined}
            loading={stats.isLoading}
          />
        </div>
      )}

      {/* Training volume (imported Strava history) */}
      <TrainingVolumeCard />

      {/* Highest deals */}
      <section>
        <div className="mb-3.5 flex items-center justify-between">
          <h2 className="font-heading text-lg-plus font-bold text-foreground">Highest deals</h2>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/deals">
              View all <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>

        {best.isLoading ? (
          <CardSkeletonGrid count={4} />
        ) : best.isError ? (
          <ErrorState error={best.error} onRetry={best.refetch} />
        ) : best.data?.length ? (
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
            {best.data.map((deal) => (
              <HighestDealTile key={deal.id} deal={deal} />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Tag}
            title="No deals yet"
            description="Run a scrape to find deals on your tracked shoes."
          />
        )}
      </section>

      {/* Recently detected */}
      <section className="overflow-hidden rounded-2xl border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            <span className="h-2 w-2 rounded-full bg-primary shadow-[0_0_0_3px_oklch(0.74_0.17_153_/_0.18)]" />
            <span className="font-heading text-md-plus font-bold text-foreground">
              Recently detected
            </span>
          </div>
          <span className="font-mono text-2xs text-faint">live</span>
        </div>

        {recent.isLoading ? (
          <div className="p-4">
            <RowSkeleton count={4} />
          </div>
        ) : recent.isError ? (
          <div className="p-4">
            <ErrorState error={recent.error} onRetry={recent.refetch} />
          </div>
        ) : recent.data?.length ? (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
              {recent.data.map((deal) => (
                <RecentDealRow key={deal.id} deal={deal} />
              ))}
            </div>
            <Link
              to="/deals"
              className="focus-ring block border-t border-border py-3.5 text-center text-sm font-semibold text-muted-foreground hover:text-foreground"
            >
              View all activity →
            </Link>
          </>
        ) : (
          <div className="p-4">
            <EmptyState
              icon={Tag}
              title="Nothing detected recently"
              description="New deals will appear here after the next scrape."
            />
          </div>
        )}
      </section>
    </div>
  )
}

function HighestDealTile({ deal }) {
  const shoe = deal.shoe || {}
  const retailerName = typeof deal.retailer === 'string' ? deal.retailer : deal.retailer?.name

  return (
    <Link
      to={`/deals?deal=${deal.id}`}
      className="focus-ring flex flex-col overflow-hidden rounded-[14px] border border-border bg-surface"
    >
      <div className="relative flex h-[140px] items-center justify-center bg-placeholder-stripes">
        {deal.image_url ? (
          <img src={deal.image_url} alt={shoe.model} className="h-full w-full object-contain" />
        ) : (
          <Footprints className="h-8 w-8 text-faint" />
        )}
        {deal.savings_percent != null && (
          <Badge className="absolute left-[11px] top-[11px] rounded-[7px] bg-primary px-[9px] py-[5px] font-heading text-sm-plus font-extrabold text-primary-foreground">
            {formatPercent(deal.savings_percent)} OFF
          </Badge>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-0.5 p-4">
        <span className="text-2xs font-bold uppercase tracking-[0.1em] text-accent-foreground">
          {shoe.brand}
        </span>
        <span className="font-heading text-base font-bold text-foreground">{shoe.model}</span>
        <span className="text-sm-plus text-muted-foreground">{retailerName}</span>
        <div className="mt-auto pt-3">
          <div className="flex items-baseline gap-2 tabular-nums">
            <span className="font-heading text-stat font-extrabold text-foreground">
              {formatCurrency(deal.current_price)}
            </span>
            {shoe.msrp != null && (
              <span
                className="text-sm text-faint line-through"
                title={`Retail price ${formatCurrency(shoe.msrp)}`}
              >
                {formatCurrency(shoe.msrp)}
              </span>
            )}
          </div>
          <p className="text-sm-plus text-faint">
            {[
              shoe.msrp != null && `Retail price ${formatCurrency(shoe.msrp)}`,
              deal.target_price != null && `Target ${formatCurrency(deal.target_price)}`,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
      </div>
    </Link>
  )
}

function RecentDealRow({ deal }) {
  const shoe = deal.shoe || {}
  const retailerName = typeof deal.retailer === 'string' ? deal.retailer : deal.retailer?.name

  return (
    <Link
      to={`/deals?deal=${deal.id}`}
      className="focus-ring flex items-center gap-[13px] border-b border-divider px-[18px] py-[13px] last:border-b-0"
    >
      <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-[9px] bg-placeholder-stripes">
        {deal.image_url && (
          <img src={deal.image_url} alt={shoe.model} className="h-full w-full object-contain" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5">
          <span className="text-2xs font-bold uppercase tracking-[0.06em] text-accent-foreground">
            {shoe.brand}
          </span>
          <span className="font-mono text-[10px] text-faint">
            {formatRelativeTime(deal.detected_at)}
          </span>
        </div>
        <div className="truncate text-sm font-semibold text-foreground">{shoe.model}</div>
        <div className="text-xs text-muted-foreground">{retailerName}</div>
      </div>
      <div className="shrink-0 text-right">
        <div className="flex items-baseline justify-end gap-1.5 tabular-nums">
          <span className="font-heading text-md-plus font-extrabold text-foreground">
            {formatCurrency(deal.current_price)}
          </span>
          {shoe.msrp != null && (
            <span
              className="text-xs text-faint line-through"
              title={`Retail price ${formatCurrency(shoe.msrp)}`}
            >
              {formatCurrency(shoe.msrp)}
            </span>
          )}
        </div>
        {deal.savings_percent != null && (
          <div className="text-2xs font-bold text-accent-foreground">
            −{formatPercent(deal.savings_percent)}
          </div>
        )}
      </div>
    </Link>
  )
}
