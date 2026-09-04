import { useEffect, useRef, useState } from 'react'
import { RefreshCw, Watch, Import, Activity, Clock } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast'
import ScrapeButton from '@/components/ScrapeButton'
import {
  useDashboardStats,
  useCorosSyncStatus,
  useStravaStatus,
  useScrapeHistory,
  useSchedule,
  useUpdateSchedule,
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

// A cron of the daily shape "M H * * *" maps cleanly onto a time picker; any
// other shape is only editable as raw cron (advanced field opens pre-expanded).
const DAILY_CRON_RE = /^(\d{1,2}) (\d{1,2}) \* \* \*$/
const pad2 = (n) => String(n).padStart(2, '0')

// #7: editable "Scheduled scraping" card. The time picker is the primary
// control for the common daily case; anything else lives in the advanced cron
// field. Saving PUTs { enabled, cron }; a 422 (bad cron) shows inline.
function ScheduledScrapingCard({ schedule }) {
  const { toast } = useToast()
  const update = useUpdateSchedule()

  const [enabled, setEnabled] = useState(false)
  const [time, setTime] = useState('03:00')   // "HH:MM" for the daily picker
  const [advanced, setAdvanced] = useState(false)
  const [cronText, setCronText] = useState('0 3 * * *')
  const [dirty, setDirty] = useState(false)
  const inited = useRef(false)

  // Seed local form state from the server; re-sync on refetch only while the
  // user hasn't started editing, so a 60 s background refetch never clobbers
  // an in-progress edit.
  const data = schedule.data
  useEffect(() => {
    if (!data) return
    if (inited.current && dirty) return
    setEnabled(!!data.enabled)
    const cron = data.cron || '0 3 * * *'
    setCronText(cron)
    const m = cron.match(DAILY_CRON_RE)
    if (m) {
      setTime(`${pad2(Number(m[2]))}:${pad2(Number(m[1]))}`)  // H then M → HH:MM
      setAdvanced(false)
    } else {
      setAdvanced(true)  // non-daily shape — don't misrepresent it in the picker
    }
    inited.current = true
  }, [data, dirty])

  // The cron we'll actually send: raw text in advanced mode, else built from
  // the HH:MM picker as "M H * * *".
  const composedCron = () => {
    if (advanced) return cronText.trim()
    const [hh, mm] = time.split(':')
    return `${Number(mm)} ${Number(hh)} * * *`
  }

  const onSave = () => {
    update.mutate(
      { enabled, cron: composedCron() },
      {
        onSuccess: (res) => {
          setDirty(false)
          update.reset()
          toast({
            title: enabled ? 'Schedule updated' : 'Schedule disabled',
            description: enabled
              ? res.next_run_utc
                ? `Next run ${formatRelativeTime(res.next_run_utc)}.`
                : 'Saved.'
              : 'No scheduled runs will fire.',
          })
        },
      }
    )
  }

  const markDirty = () => setDirty(true)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Clock className="h-4 w-4 text-accent-foreground" />
          Scheduled scraping
        </CardTitle>
        <CardDescription>Nightly automatic price scan.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Enable toggle */}
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="schedule-enabled" className="text-sm font-medium">
            Enabled
          </Label>
          <Switch
            id="schedule-enabled"
            checked={enabled}
            onCheckedChange={(v) => {
              setEnabled(v)
              markDirty()
            }}
          />
        </div>

        {/* Daily time picker (primary control) */}
        {!advanced && (
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="schedule-time" className="text-sm font-medium">
              Run at
            </Label>
            <Input
              id="schedule-time"
              type="time"
              value={time}
              onChange={(e) => {
                setTime(e.target.value)
                markDirty()
              }}
              className="w-32"
            />
          </div>
        )}

        {/* Advanced: raw cron */}
        <div>
          <button
            type="button"
            className="text-xs font-medium text-accent-foreground underline-offset-2 hover:underline"
            onClick={() => setAdvanced((a) => !a)}
          >
            {advanced ? 'Use time picker' : 'Advanced (custom cron)'}
          </button>
          {advanced && (
            <div className="mt-2 space-y-1">
              <Label htmlFor="schedule-cron" className="text-sm font-medium">
                Cron expression
              </Label>
              <Input
                id="schedule-cron"
                value={cronText}
                onChange={(e) => {
                  setCronText(e.target.value)
                  markDirty()
                }}
                placeholder="0 3 * * *"
                className="font-mono"
              />
            </div>
          )}
        </div>

        {update.isError && (
          <p className="text-xs text-destructive">{update.error?.message || 'Could not save.'}</p>
        )}

        <Button onClick={onSave} disabled={update.isPending || !dirty} className="w-full">
          {update.isPending ? 'Saving…' : 'Save schedule'}
        </Button>

        {/* Read-only status (kept from the original card) */}
        <div className="border-t border-border pt-2">
          <StatRow
            label="Next run"
            value={
              schedule.data?.next_run_utc
                ? formatRelativeTime(schedule.data.next_run_utc)
                : schedule.data?.enabled === false
                  ? 'Not scheduled'
                  : null
            }
          />
          {(() => {
            const runs = schedule.data?.recent_scheduled_runs ?? []
            const last = runs[0]
            return (
              <StatRow
                label="Last scheduled run"
                value={
                  last
                    ? `${last.status} · ${last.deals_found} deal${last.deals_found === 1 ? '' : 's'}${last.started_at ? ' · ' + formatRelativeTime(last.started_at) : ''}`
                    : 'Never'
                }
              />
            )
          })()}
          <p className="mt-3 text-xs text-faint">
            Runs in America/Toronto. Backend <code>SCRAPE_SCHEDULE_*</code> env vars remain a
            fallback when no schedule is saved here.
          </p>
        </div>
      </CardContent>
    </Card>
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
  const schedule = useSchedule()
  const retailers = history.data?.retailers ?? []
  const needsAttention = retailers.filter(
    (r) => r.health === 'warning' || r.health === 'error'
  ).length

  return (
    <div className="space-y-5">
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
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

      {/* Scheduled scraping (R4.1; UI-configurable #7) */}
      <ScheduledScrapingCard schedule={schedule} />

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
