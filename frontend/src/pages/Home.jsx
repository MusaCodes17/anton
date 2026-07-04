import { Link } from 'react-router-dom'
import {
  Activity, Tag, Footprints, ArrowRight, TrendingUp, TrendingDown,
  AlertTriangle, CheckCircle2, RefreshCw, Radar, ShieldCheck,
} from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import ScrapeButton from '@/components/ScrapeButton'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/StatusViews'
import { Skeleton } from '@/components/ui/skeleton'
import { useHome } from '@/hooks/useApi'
import {
  formatCurrency, formatPercent, formatDate, formatRelativeTime, cn,
} from '@/lib/utils'
import { runSourceVariant, runSourceLabel } from '@/lib/runSource'

/**
 * Home — the attention surface (§4 Phase 4). Four modules, each answering one
 * question and deep-linking into its domain tab, all from a single
 * `GET /api/home` round trip. Designed to answer everything with no scrolling
 * on desktop and one screenful at ~380px.
 */
export default function Home() {
  const home = useHome()
  const d = home.data

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="HOME" title="Today">
        <ScrapeButton />
      </PageHeader>

      {home.isError ? (
        <ErrorState error={home.error} onRetry={home.refetch} />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <TrainingPulse pulse={d?.training_pulse} loading={home.isLoading} />
            <TopDeals deals={d?.top_deals} loading={home.isLoading} />
          </div>
          <ShoeAlerts alerts={d?.shoe_alerts} loading={home.isLoading} />
          <ActivityStrip strip={d?.activity_strip} loading={home.isLoading} />
        </>
      )}
    </div>
  )
}

// ── Module shell ────────────────────────────────────────────────────────────

function ModuleCard({ icon: Icon, title, to, viewLabel = 'View all', children }) {
  return (
    <section className="flex flex-col overflow-hidden rounded-2xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
        <div className="flex items-center gap-2.5">
          <Icon className="h-4 w-4 text-primary" />
          <span className="font-heading text-md-plus font-bold text-foreground">{title}</span>
        </div>
        {to && (
          <Button variant="ghost" size="sm" asChild>
            <Link to={to}>
              {viewLabel} <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        )}
      </div>
      <div className="flex-1 p-5">{children}</div>
    </section>
  )
}

// ── Training pulse → /training ───────────────────────────────────────────────

function TrainingPulse({ pulse, loading }) {
  return (
    <ModuleCard icon={Activity} title="Training pulse" to="/training">
      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-12 w-40" />
          <Skeleton className="h-16 w-full rounded-[12px]" />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-end justify-between gap-4">
            <div>
              <div className="text-2xs font-bold uppercase tracking-[0.08em] text-faint">
                This week
              </div>
              <div className="mt-1 font-heading text-4xl font-extrabold tracking-tight text-foreground tabular-nums">
                {(pulse?.this_week_km ?? 0).toFixed(1)}
                <span className="ml-1 text-lg font-semibold text-faint">km</span>
              </div>
            </div>
            <WeekDelta delta={pulse?.delta_km ?? 0} lastWeek={pulse?.last_week_km ?? 0} />
          </div>
          <LastRun run={pulse?.last_run} />
        </div>
      )}
    </ModuleCard>
  )
}

function WeekDelta({ delta, lastWeek }) {
  const flat = Math.abs(delta) < 0.05
  const up = delta > 0
  const Icon = flat ? null : up ? TrendingUp : TrendingDown
  const tone = flat ? 'text-faint' : up ? 'text-success' : 'text-warning'
  return (
    <div className="text-right">
      <div className={cn('flex items-center justify-end gap-1 font-semibold tabular-nums', tone)}>
        {Icon && <Icon className="h-4 w-4" />}
        <span>{flat ? 'flat' : `${up ? '+' : '−'}${Math.abs(delta).toFixed(1)} km`}</span>
      </div>
      <div className="mt-0.5 text-2xs text-faint tabular-nums">
        vs {lastWeek.toFixed(1)} km last week
      </div>
    </div>
  )
}

function LastRun({ run }) {
  if (!run) {
    return (
      <div className="rounded-[12px] border border-dashed border-border px-4 py-3 text-sm text-muted-foreground">
        No runs logged yet.
      </div>
    )
  }
  return (
    <div className="rounded-[12px] border border-border bg-surface px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-2xs font-bold uppercase tracking-[0.08em] text-faint">Last run</span>
        <Badge variant={runSourceVariant(run.source)}>{runSourceLabel(run.source)}</Badge>
      </div>
      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <span className="font-heading text-xl font-extrabold text-foreground tabular-nums">
          {run.distance_km.toFixed(1)} km
        </span>
        {run.avg_pace && <span className="text-sm text-muted-foreground tabular-nums">{run.avg_pace}</span>}
        {run.avg_hr != null && (
          <span className="text-sm text-muted-foreground tabular-nums">{run.avg_hr} bpm</span>
        )}
        <span className="text-xs text-faint">{formatDate(run.date)}</span>
      </div>
      {run.shoe && (
        <Link
          to={`/shoes/${run.shoe.id}`}
          className="focus-ring mt-2 inline-flex min-w-0 items-center gap-1 rounded-full border border-border bg-secondary px-2 py-0.5 text-2xs font-medium text-secondary-foreground hover:border-primary/40"
        >
          <Footprints className="h-3 w-3 shrink-0" />
          <span className="truncate">{run.shoe.nickname || `${run.shoe.brand} ${run.shoe.model}`}</span>
        </Link>
      )}
    </div>
  )
}

// ── Top deals → /deals ───────────────────────────────────────────────────────

function TopDeals({ deals, loading }) {
  return (
    <ModuleCard icon={Tag} title="Top deals" to="/deals">
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-16 w-full rounded-[12px]" />)}
        </div>
      ) : deals?.length ? (
        <div className="space-y-3">
          {deals.map((deal) => <TopDealRow key={deal.id} deal={deal} />)}
        </div>
      ) : (
        <div className="flex h-full items-center justify-center rounded-[12px] border border-dashed border-border py-6 text-sm text-muted-foreground">
          No active deals right now.
        </div>
      )}
    </ModuleCard>
  )
}

function TopDealRow({ deal }) {
  return (
    <Link
      to={`/deals?deal=${deal.id}`}
      className="focus-ring flex items-center gap-3 rounded-[12px] border border-border bg-surface p-3 hover:border-primary/40"
    >
      <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-[9px] bg-placeholder-stripes">
        {deal.image_url ? (
          <img src={deal.image_url} alt={deal.model} className="h-full w-full object-contain" />
        ) : (
          <Footprints className="h-5 w-5 text-faint" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-2xs font-bold uppercase tracking-[0.06em] text-accent-foreground">
          {deal.brand}
        </div>
        <div className="truncate text-sm font-semibold text-foreground">{deal.model}</div>
        <div className="text-xs text-muted-foreground">{deal.retailer}</div>
      </div>
      <div className="shrink-0 text-right">
        <div className="flex items-baseline justify-end gap-1.5 tabular-nums">
          <span className="font-heading text-md-plus font-extrabold text-foreground">
            {formatCurrency(deal.current_price)}
          </span>
          {deal.msrp != null && (
            <span className="text-xs text-faint line-through">{formatCurrency(deal.msrp)}</span>
          )}
        </div>
        <Badge className="mt-0.5 rounded-[6px] bg-primary px-1.5 py-0.5 text-2xs font-extrabold text-primary-foreground">
          {formatPercent(deal.savings_percent)} OFF
        </Badge>
      </div>
    </Link>
  )
}

// ── Shoe alerts → /shoes ─────────────────────────────────────────────────────

function ShoeAlerts({ alerts, loading }) {
  return (
    <ModuleCard icon={AlertTriangle} title="Rotation alerts" to="/shoes" viewLabel="My shoes">
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 2 }).map((_, i) => <Skeleton key={i} className="h-14 w-full rounded-[12px]" />)}
        </div>
      ) : alerts?.length ? (
        <div className="space-y-3">
          {alerts.map((a) => <ShoeAlertRow key={a.id} alert={a} />)}
        </div>
      ) : (
        <div className="flex items-center gap-2.5 text-sm text-muted-foreground">
          <CheckCircle2 className="h-4 w-4 text-success" />
          <span>Rotation healthy — no shoes near their mileage limit.</span>
        </div>
      )}
    </ModuleCard>
  )
}

function ShoeAlertRow({ alert }) {
  const pct = Math.round(alert.pct * 100)
  const over = alert.pct >= 1
  const barColor = over ? 'bg-destructive' : 'bg-warning'
  return (
    <Link
      to={`/shoes/${alert.id}`}
      className="focus-ring flex flex-col gap-2 rounded-[12px] border border-border bg-surface p-3.5 hover:border-primary/40 sm:flex-row sm:items-center sm:gap-4"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-bold text-foreground">
            {alert.nickname || `${alert.brand} ${alert.model}`}
          </span>
          {over && (
            <Badge variant="destructive" className="shrink-0 text-2xs">Over limit</Badge>
          )}
        </div>
        <div className="mt-0.5 text-xs text-muted-foreground tabular-nums">
          {Math.round(alert.current_mileage)} km / {Math.round(alert.mileage_limit)} km
          {alert.replacement_deals > 0 && (
            <span className="text-accent-foreground">
              {' · '}{alert.replacement_deals} replacement deal{alert.replacement_deals === 1 ? '' : 's'}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3 sm:w-48">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
          <div className={cn('h-full rounded-full', barColor)} style={{ width: `${Math.min(100, pct)}%` }} />
        </div>
        <span className="shrink-0 text-xs font-semibold text-foreground tabular-nums">{pct}%</span>
      </div>
    </Link>
  )
}

// ── Activity strip ───────────────────────────────────────────────────────────

function ActivityStrip({ strip, loading }) {
  if (loading) {
    return <Skeleton className="h-[64px] w-full rounded-2xl" />
  }
  return (
    <div className="grid grid-cols-1 gap-3 rounded-2xl border border-border bg-card p-4 sm:grid-cols-3">
      <StripItem
        icon={RefreshCw}
        label="Last COROS sync"
        value={strip?.last_coros_sync_at ? formatRelativeTime(strip.last_coros_sync_at) : 'never'}
      />
      <StripItem
        icon={Radar}
        label="Last scrape"
        value={strip?.last_scrape_at ? formatRelativeTime(strip.last_scrape_at) : 'never'}
      />
      <StripItem
        icon={ShieldCheck}
        label="Newest deal"
        value={strip?.newest_deal_at ? formatRelativeTime(strip.newest_deal_at) : 'none yet'}
        sub={strip?.newest_deal_label}
        to={strip?.newest_deal_at ? '/deals' : undefined}
      />
    </div>
  )
}

function StripItem({ icon: Icon, label, value, sub, to }) {
  const body = (
    <div className="flex items-center gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-surface">
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="min-w-0">
        <div className="text-2xs font-bold uppercase tracking-[0.08em] text-faint">{label}</div>
        <div className="truncate text-sm font-semibold text-foreground">{value}</div>
        {sub && <div className="truncate text-xs text-muted-foreground">{sub}</div>}
      </div>
    </div>
  )
  return to ? (
    <Link to={to} className="focus-ring rounded-[12px] hover:opacity-80">{body}</Link>
  ) : (
    body
  )
}
