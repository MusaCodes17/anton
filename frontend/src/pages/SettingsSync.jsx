import { RefreshCw, Watch, Import } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import ScrapeButton from '@/components/ScrapeButton'
import { useDashboardStats, useCorosSyncStatus, useStravaStatus } from '@/hooks/useApi'
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

  return (
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
  )
}
