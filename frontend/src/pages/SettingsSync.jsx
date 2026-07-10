import { RefreshCw, Watch, Import, Activity } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import ScrapeButton from '@/components/ScrapeButton'
import {
  useDashboardStats,
  useCorosSyncStatus,
  useStravaStatus,
  useScrapeHistory,
} from '@/hooks/useApi'
import { formatDate, formatRelativeTime } from '@/lib/utils'

// One read-only status line: label on the left, value on the right, muted
// dash when we have nothing yet.
function StatRow({ label, value }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground tabular-nums">{value ?? '—'}</span>
    </div>
  )
}

// R2.5 scrape-health verdict → dot color + human label. "warning" is the
// quietly-broken case (finished clean, found nothing); "unknown" = never
// scraped or a scrape is running now.
const HEALTH = {
  ok: { dot: 'bg-success', label: 'Healthy' },
  warning: { dot: 'bg-warning', label: 'No products' },
  error: { dot: 'bg-destructive', label: 'Error' },
  unknown: { dot: 'bg-muted-foreground/40', label: 'Not scraped yet' },
}

// One retailer's scrape health: status dot + name on the left, last-run
// summary on the right. Whole row stays legible at ~380 px (wraps, no h-scroll).
function RetailerHealthRow({ retailer }) {
  const health = HEALTH[retailer.health] ?? HEALTH.unknown
  const last = retailer.latest_run
  return (
    <div className="flex items-start justify-between gap-3 py-2 text-sm">
      <div className="flex min-w-0 items-center gap-2">
        <span
          className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${health.dot}`}
          aria-hidden="true"
        />
        <span className="min-w-0 truncate font-medium text-foreground">{retailer.name}</span>
      </div>
      <div className="shrink-0 text-right">
        <div className="font-medium text-foreground tabular-nums">
          {last ? `${last.products_found} products` : health.label}
        </div>
        <div className="text-xs text-faint">
          {last?.finished_at
            ? formatRelativeTime(last.finished_at)
            : retailer.health === 'unknown'
              ? health.label
              : '—'}
        </div>
      </div>
    </div>
  )
}

/**
 * Settings → Sync & Scraping. A status surface, not a control panel: the one
 * active control is the deal scrape (ScrapeButton). COROS and Strava show
 * their current state with an honest hint about where configuration lives
 * (env/import CLI), since neither is wired for in-app setup yet.
 */
export default function SettingsSync() {
  const stats = useDashboardStats()
  const coros = useCorosSyncStatus()
  const strava = useStravaStatus()
  const history = useScrapeHistory()
  const retailers = history.data?.retailers ?? []
  const needsAttention = retailers.filter(
    (r) => r.health === 'warning' || r.health === 'error'
  ).length

  return (
    <div className="space-y-5">
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
      {/* Deal scraping */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <RefreshCw className="h-4 w-4 text-accent-foreground" />
            Deal scraping
          </CardTitle>
          <CardDescription>Pull fresh prices from every enabled retailer.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <StatRow
            label="Last scan"
            value={stats.data?.last_scrape ? formatRelativeTime(stats.data.last_scrape) : 'Never'}
          />
          <ScrapeButton className="w-full" />
        </CardContent>
      </Card>

      {/* COROS sync */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Watch className="h-4 w-4 text-accent-foreground" />
            COROS sync
          </CardTitle>
          <CardDescription>Import runs from your watch onto tracked shoes.</CardDescription>
        </CardHeader>
        <CardContent>
          <StatRow
            label="Credentials"
            value={coros.data?.coros_configured ? 'Configured' : 'Not configured'}
          />
          <StatRow
            label="Last sync"
            value={coros.data?.last_sync_at ? formatRelativeTime(coros.data.last_sync_at) : 'Never'}
          />
          <p className="mt-3 text-xs text-faint">
            Sync runs from the My Shoes page. Credentials are set via COROS env vars on the backend.
          </p>
        </CardContent>
      </Card>

      {/* Strava import */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Import className="h-4 w-4 text-accent-foreground" />
            Strava import
          </CardTitle>
          <CardDescription>Historical activities from a Strava bulk export.</CardDescription>
        </CardHeader>
        <CardContent>
          <StatRow label="Activities imported" value={strava.data?.activity_count?.toLocaleString()} />
          <StatRow label="Runs" value={strava.data?.run_count?.toLocaleString()} />
          <StatRow
            label="Latest activity"
            value={strava.data?.latest_activity_date ? formatDate(strava.data.latest_activity_date) : null}
          />
          <StatRow
            label="Last imported"
            value={strava.data?.imported_at ? formatDate(strava.data.imported_at) : null}
          />
          <p className="mt-3 text-xs text-faint">
            Imported via the Strava export CLI. New runs come from COROS, not re-import.
          </p>
        </CardContent>
      </Card>
    </div>

      {/* Retailer scrape health (R2.5) — surfaces the "quietly broken"
          retailer a green "Last scan" timestamp would otherwise hide. */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4 text-accent-foreground" />
            Retailer health
          </CardTitle>
          <CardDescription>
            {needsAttention > 0
              ? `${needsAttention} retailer${needsAttention > 1 ? 's' : ''} need${needsAttention > 1 ? '' : 's'} a look — check its scraper.`
              : 'Per-retailer results from the most recent scrape of each.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {retailers.length === 0 ? (
            <p className="py-2 text-sm text-faint">
              {history.isLoading ? 'Loading…' : 'No retailers configured.'}
            </p>
          ) : (
            <div className="divide-y divide-border">
              {retailers.map((r) => (
                <RetailerHealthRow key={r.retailer_id} retailer={r} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
