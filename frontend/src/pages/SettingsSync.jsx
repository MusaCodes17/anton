import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { RefreshCw, Watch, Import, Activity, Clock, ChevronDown } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { useOnline } from '@/hooks/useOnline'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useToast } from '@/components/ui/toast'
import ScrapeButton from '@/components/ScrapeButton'
import {
  useDashboardStats,
  useCorosStatus,
  useConnectCoros,
  useSyncCoros,
  useDisconnectCoros,
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

const COROS_ERROR_REASONS = {
  denied: 'You declined access on COROS.',
  invalid_state: 'That sign-in link expired or was already used. Try connecting again.',
  exchange_rejected: 'COROS rejected the sign-in. Try connecting again.',
  not_registered: 'Start the connection from Anton again.',
  not_configured: 'The server is missing its COROS encryption key.',
  unreachable: 'COROS could not be reached. Try again shortly.',
}

const OFFLINE_MSG = "You're offline — this needs a connection."

// Direct COROS connection (R5.7): Anton is an OAuth client of COROS; the server
// polls and queues runs for the inbox. States are shown honestly — a failed or
// stale sync reads as such rather than as a quietly-old "Connected".
function CorosConnectionCard() {
  const { toast } = useToast()
  const { online } = useOnline()
  const status = useCorosStatus()
  const connect = useConnectCoros()
  const sync = useSyncCoros()
  const disconnect = useDisconnectCoros()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [params, setParams] = useSearchParams()

  // Landing back from the COROS sign-in: report the outcome once, then clean the URL.
  useEffect(() => {
    const result = params.get('coros')
    if (!result) return
    if (result === 'connected') {
      toast({ title: 'COROS connected', description: 'New runs will appear in New runs within about 15 minutes.' })
    } else {
      toast({ variant: 'destructive', title: 'COROS connection failed',
        description: COROS_ERROR_REASONS[params.get('reason')] ?? 'Something went wrong. Try again.' })
    }
    params.delete('coros')
    params.delete('reason')
    setParams(params, { replace: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const st = status.data
  const sy = st?.sync
  const state = !st ? null : !st.configured ? 'unconfigured' : st.status

  function startConnect() {
    connect.mutate(undefined, {
      onSuccess: (r) => window.location.assign(r.authorize_url),
      onError: (err) => toast({ variant: 'destructive', title: 'Could not start connection', description: err.message }),
    })
  }

  function syncNow() {
    sync.mutate(undefined, {
      onSuccess: (r) => toast({
        title: r.ok ? 'Synced with COROS' : 'Sync finished with problems',
        description: r.ok ? (r.queued ? `${r.queued} new run${r.queued === 1 ? '' : 's'} found.` : 'No new runs.') : r.errors?.[0],
        variant: r.ok ? undefined : 'destructive',
      }),
      onError: (err) => toast({ variant: 'destructive', title: 'Sync failed', description: err.message }),
    })
  }

  function doDisconnect() {
    disconnect.mutate(undefined, {
      onSuccess: (r) => {
        setConfirmOpen(false)
        toast({
          title: 'COROS disconnected',
          description: r.revoked_remotely
            ? 'Anton\'s access was revoked at COROS.'
            : 'Tokens deleted from Anton. COROS did not confirm revocation — you can also remove Anton from your COROS account.',
        })
      },
      onError: (err) => toast({ variant: 'destructive', title: 'Could not disconnect', description: err.message }),
    })
  }

  const badge = {
    connected: <Badge variant="success">Connected</Badge>,
    reauth_required: <Badge variant="warning">Reconnect needed</Badge>,
    disconnected: <Badge variant="outline">Not connected</Badge>,
    unconfigured: <Badge variant="outline">Server not set up</Badge>,
  }[state]

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Watch className="h-4 w-4 text-accent-foreground" />
          COROS sync
          <span className="ml-auto">{badge}</span>
        </CardTitle>
        <CardDescription>Runs from your watch arrive in New runs for you to confirm.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {state === 'unconfigured' && (
          <p className="text-sm text-muted-foreground">
            The server has no COROS encryption key yet (<code>COROS_TOKEN_KEY</code>), so connecting is disabled.
          </p>
        )}
        {state === 'reauth_required' && (
          <p className="text-sm text-muted-foreground">
            COROS stopped accepting Anton's access, so no new runs are arriving. Reconnect to resume.
          </p>
        )}
        {(state === 'connected' || state === 'reauth_required') && (
          <div>
            <StatRow label="Last successful sync"
              value={sy?.last_success_at ? formatRelativeTime(sy.last_success_at) : 'Never'} />
            <StatRow label="Waiting for review" value={sy?.pending_count ?? 0} />
            {state === 'connected' && st?.next_poll_utc && (
              <StatRow label="Next automatic check" value={formatRelativeTime(st.next_poll_utc).replace(' ago', '')} />
            )}
          </div>
        )}
        {sy?.last_error && (
          <p className="text-sm text-destructive">
            Last sync failed{sy.last_attempt_at ? ` ${formatRelativeTime(sy.last_attempt_at)}` : ''}: {sy.last_error}
          </p>
        )}
        <div className="flex flex-wrap gap-2 pt-1">
          {state === 'connected' && (
            <>
              <Button onClick={syncNow} disabled={!online || sync.isPending} title={!online ? OFFLINE_MSG : undefined}>
                <RefreshCw className={sync.isPending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} /> Sync now
              </Button>
              {(sy?.pending_count ?? 0) > 0 && (
                <Button variant="outline" asChild><Link to="/new-runs">Review runs</Link></Button>
              )}
            </>
          )}
          {(state === 'disconnected' || state === 'reauth_required') && (
            <Button onClick={startConnect} disabled={!online || connect.isPending} title={!online ? OFFLINE_MSG : undefined}>
              {state === 'reauth_required' ? 'Reconnect COROS' : 'Connect COROS'}
            </Button>
          )}
          {(state === 'connected' || state === 'reauth_required') && (
            <Button variant="outline" onClick={() => setConfirmOpen(true)} disabled={!online}
              title={!online ? OFFLINE_MSG : undefined}>
              Disconnect
            </Button>
          )}
        </div>
        {!online && <p className="text-xs text-faint">{OFFLINE_MSG}</p>}
      </CardContent>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disconnect COROS?</DialogTitle>
            <DialogDescription>
              Anton will stop checking for new runs and its COROS tokens will be deleted. Runs already logged
              stay. You can reconnect any time.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={doDisconnect} disabled={disconnect.isPending}>Disconnect</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

/**
 * Settings → Sync & Scraping. A status surface, not a control panel: the one
 * active controls are the deal scrape (ScrapeButton) and the COROS connection
 * (R5.7). Strava shows its state with an honest hint about where configuration
 * lives (import CLI), since it is not wired for in-app setup.
 */
export default function SettingsSync() {
  const stats = useDashboardStats()
  const strava = useStravaStatus()
  const history = useScrapeHistory()
  const schedule = useSchedule()
  const retailers = history.data?.retailers ?? []
  const needsAttention = retailers.filter(
    (r) => r.health === 'warning' || r.health === 'error'
  ).length
  // Phone-only collapse: closed by default below md unless a retailer needs a
  // look; md+ is always open (the toggle is inert there). null = untouched.
  const isMd = useMediaQuery('(min-width: 768px)')
  const [healthToggled, setHealthToggled] = useState(null)
  const healthOpen = isMd || (healthToggled ?? needsAttention > 0)
  const healthSummary = `${retailers.length} retailer${retailers.length === 1 ? '' : 's'} · ${needsAttention} ${needsAttention === 1 ? 'needs' : 'need'} attention`

  return (
    <div className="space-y-5">
    <div className="grid grid-cols-1 gap-4 sm:gap-5 sm:grid-cols-2">
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

      {/* COROS direct sync (R5.7) */}
      <CorosConnectionCard />

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
          <CardTitle className="text-base">
            <button
              type="button"
              aria-expanded={healthOpen}
              aria-controls="retailer-health-body"
              onClick={() => setHealthToggled(!healthOpen)}
              className="focus-ring flex w-full items-center justify-between gap-2 rounded-md text-left md:pointer-events-none"
            >
              <span className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-accent-foreground" />
                Retailer health
              </span>
              <ChevronDown
                aria-hidden="true"
                className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform md:hidden ${healthOpen ? 'rotate-180' : ''}`}
              />
            </button>
          </CardTitle>
          <CardDescription>
            {!healthOpen && !isMd && retailers.length > 0
              ? healthSummary
              : needsAttention > 0
                ? `${needsAttention} retailer${needsAttention > 1 ? 's' : ''} need${needsAttention > 1 ? '' : 's'} a look — check its scraper.`
                : 'Per-retailer results from the most recent scrape of each.'}
          </CardDescription>
        </CardHeader>
        <CardContent id="retailer-health-body" hidden={!healthOpen}>
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
