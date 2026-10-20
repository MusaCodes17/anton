import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Activity, Compass, Flag, Layers, ListOrdered, TrendingUp } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import SyncRunsButton from '@/components/SyncRunsButton'
import PlannedRacesCard from '@/components/training/PlannedRacesCard'
import VolumeChart from '@/components/training/VolumeChart'
import NowStrip from '@/components/training/NowStrip'
import FitnessCard from '@/components/training/FitnessCard'
import PredictionsCard from '@/components/training/PredictionsCard'
import RecordsCard from '@/components/training/RecordsCard'
import RaceBlocksCard from '@/components/training/RaceBlocksCard'
import ActivityRow from '@/components/training/ActivityRow'
import DateRangeControls from '@/components/training/DateRangeControls'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ErrorState, EmptyState } from '@/components/StatusViews'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useTrainingSummary,
  useTrainingRecords,
  useTrainingFitness,
  useTrainingTrends,
  useRaceReadiness,
  useActivities,
  useOwnedShoes,
} from '@/hooks/useApi'
import { isoDaysAgo, isoToday, useDateRange } from '@/hooks/useDateRange'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const ALL = '__all__'
const PAGE = 5

// "2026-07" → { label: "Jul", fullLabel: "Jul 2026" }
function labelMonth(period) {
  const [y, m] = period.split('-')
  const mon = MONTHS[parseInt(m, 10) - 1] ?? period
  return { label: mon, fullLabel: `${mon} ${y}` }
}
// The Thursday of an ISO week (ISO 8601: the week's Thursday fixes its month/year).
function isoWeekThursday(y, w) {
  const jan4 = new Date(Date.UTC(y, 0, 4))
  const jan4Dow = jan4.getUTCDay() || 7 // Mon=1..Sun=7
  const week1Mon = new Date(jan4)
  week1Mon.setUTCDate(jan4.getUTCDate() - (jan4Dow - 1))
  const thu = new Date(week1Mon)
  thu.setUTCDate(week1Mon.getUTCDate() + (w - 1) * 7 + 3)
  return thu
}
// "2026-W27" → { label: "W27", fullLabel: "Week 27 · 2026", monthAbbrev: "Jul" }
// monthAbbrev drives the month-based x-axis on the weekly view (T4a) — the data
// stays weekly, only the axis labels are months.
function labelWeek(period) {
  const [y, w] = period.split('-W')
  const thu = isoWeekThursday(parseInt(y, 10), parseInt(w, 10))
  return {
    label: `W${w}`,
    fullLabel: `Week ${parseInt(w, 10)} · ${y}`,
    monthAbbrev: MONTHS[thu.getUTCMonth()],
  }
}

function currentMonthKey(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
function currentWeekKey(d = new Date()) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const dayNum = (date.getUTCDay() + 6) % 7 // Mon=0
  date.setUTCDate(date.getUTCDate() - dayNum + 3) // nearest Thursday
  const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4))
  const week =
    1 +
    Math.round(
      ((date - firstThursday) / 864e5 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7
    )
  return `${date.getUTCFullYear()}-W${String(week).padStart(2, '0')}`
}

// Template .stat: an open figure, not a tile. A rule on top, the value large
// in the display voice (Archivo Narrow bold) with its unit in the accent, the label underneath.
function Stat({ label, value, unit }) {
  return (
    <div className="min-w-0 border-t border-input pt-4 sm:pt-5">
      <div className="truncate font-heading text-[42px] font-bold uppercase leading-[0.9] tracking-display text-foreground tabular-nums sm:text-[46px] xl:text-[60px]">
        {value}
        {unit && <small className="ml-1 text-[0.4em] tracking-normal text-primary">{unit}</small>}
      </div>
      <div className="mt-3 text-sm font-medium text-secondary-foreground sm:text-md-plus">{label}</div>
    </div>
  )
}

function SectionHeading({ id, icon: Icon, title, hint }) {
  // scroll-mt offsets clear the sticky PageHeader band so in-page anchor jumps land below it.
  return (
    <div id={id} className="flex items-baseline gap-2 scroll-mt-28 sm:scroll-mt-36 lg:scroll-mt-40">
      <Icon className="h-[18px] w-[18px] shrink-0 self-center text-accent-foreground" />
      <h2 className="font-heading text-lg font-bold uppercase tracking-display text-foreground">{title}</h2>
      {hint && <span className="text-xs text-faint">{hint}</span>}
    </div>
  )
}

// Fixed windows behind the header meta line, the stat row and the Now strip's
// Load chart. Called by both the page (header) and OverviewTab; React Query
// dedupes on identical keys, so it's one request each.
function useVolumeStats() {
  // Fixed trailing-365-day window for the "Last 12 mo" stat tile — computed
  // once at mount so the tile matches the Volume header total when 1y is selected.
  const trailing365Range = useMemo(() => ({ date_from: isoDaysAgo(365), date_to: isoToday() }), [])
  const trailing365 = useTrainingSummary('monthly', trailing365Range) // fixed 365-day window for 12-mo tile
  // Last 12 ISO weeks for the Now strip's Load card — independent of any range picker.
  const recentWeeksRange = useMemo(() => ({ date_from: isoDaysAgo(7 * 12 + 6), date_to: isoToday() }), [])
  const recentWeekly = useTrainingSummary('weekly', recentWeeksRange)

  // Stat strip — "Last 12 mo" sums the fixed trailing-365-day window so it
  // equals the Volume header total when the 1y preset is selected.
  const stats = useMemo(() => {
    // thisMonth comes from the 365-day monthly buckets and thisWeek from the
    // 12-week weekly buckets: both windows contain the current bucket, so the
    // two extra unranged summary requests are unnecessary.
    const t = trailing365.data || []
    const w = recentWeekly.data || []
    const total12 = t.reduce((s, b) => s + b.total_km, 0)
    const runs12 = t.reduce((s, b) => s + b.run_count, 0)
    const thisMonth = t.find((b) => b.period === currentMonthKey())?.total_km ?? 0
    const thisWeek = w.find((b) => b.period === currentWeekKey())?.total_km ?? 0
    return { thisWeek, thisMonth, total12, runs12 }
  }, [trailing365.data, recentWeekly.data])

  return { trailing365, recentWeekly, stats }
}

function OverviewTab() {
  const [period, setPeriod] = useState('weekly')

  // Volume's own date range (T4b). Default: last 365 days (the 1y preset).
  // Independent of the Activities tab's range.
  const dr = useDateRange()
  const { range } = dr

  const { trailing365, recentWeekly, stats } = useVolumeStats()
  const ranged = useTrainingSummary(period, range) // the volume chart honours the range
  const records = useTrainingRecords()
  const fitness = useTrainingFitness()

  // "Now" strip (R8.4.5). The Load card's chart is the last 12 ISO weeks of
  // the weekly summary — fixed at mount, independent of the range picker.
  const trends = useTrainingTrends()
  const readiness = useRaceReadiness()

  // Chart data (chronological). Shows every period inside the selected range —
  // no fixed 12-bar cap, so widening the range visibly extends the weekly chart
  // too (a 1-year range → ~52 weeks), not just the monthly one. Month axis
  // labels (T4a) keep it legible at density.
  const chartData = useMemo(() => {
    const src = ranged.data
    if (!src) return []
    const label = period === 'weekly' ? labelWeek : labelMonth
    return [...src].reverse().map((b) => ({ ...b, ...label(b.period) }))
  }, [period, ranged.data])

  // Totals across the selected range (each run lands in exactly one bucket, so
  // the sum is range-total regardless of weekly/monthly bucketing).
  const rangeTotals = useMemo(() => {
    const src = ranged.data || []
    return {
      km: src.reduce((s, b) => s + (b.total_km || 0), 0),
      runs: src.reduce((s, b) => s + (b.run_count || 0), 0),
    }
  }, [ranged.data])

  // Weekly view (T4a): label the x-axis by month instead of week number. One
  // tick at the first week of each month; the formatter maps that week's label
  // to its month name. Monthly view already labels by month, so no override.
  const xAxis = useMemo(() => {
    if (period !== 'weekly') return {}
    const map = {}
    const ticks = []
    let prev = null
    for (const d of chartData) {
      map[d.label] = d.monthAbbrev
      if (d.monthAbbrev !== prev) { ticks.push(d.label); prev = d.monthAbbrev }
    }
    return { xTicks: ticks, xTickFormatter: (lab) => map[lab] ?? lab }
  }, [period, chartData])

  // Last 12 ISO weeks, oldest first. The summary omits empty weeks; they're
  // filled with 0 km here (presentation only — no number is derived).
  const recentWeeks = useMemo(() => {
    const byKey = Object.fromEntries((recentWeekly.data || []).map((b) => [b.period, b]))
    const out = []
    for (let i = 11; i >= 0; i--) {
      const d = new Date()
      d.setDate(d.getDate() - 7 * i)
      const key = currentWeekKey(d)
      const b = byKey[key]
      out.push({
        period: key,
        fullLabel: labelWeek(key).fullLabel,
        total_km: b?.total_km ?? 0,
        rolling_4wk_km: b?.rolling_4wk_km ?? null,
      })
    }
    return out
  }, [recentWeekly.data])

  const summaryLoading = trailing365.isLoading || recentWeekly.isLoading
  const summaryError = trailing365.isError ? trailing365 : recentWeekly.isError ? recentWeekly : null

  return (
    <div className="space-y-5 md:space-y-8">
      <section className="space-y-4">
        <SectionHeading id="now" icon={Compass} title="Now" />
        <NowStrip trends={trends} readiness={readiness} weeks={recentWeeks} />
      </section>

      <section className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <SectionHeading id="volume" icon={TrendingUp} title="Volume" />
          <DateRangeControls range={dr} />
        </div>

        {summaryLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-[220px] w-full rounded-[12px] sm:h-[120px]" />
            <Skeleton className="h-[160px] w-full rounded-[12px] sm:h-[220px]" />
          </div>
        ) : summaryError ? (
          <ErrorState
            error={summaryError.error}
            onRetry={() => { trailing365.refetch(); recentWeekly.refetch() }}
          />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-x-5 gap-y-6 pb-2 sm:grid-cols-4 sm:gap-x-8">
              <Stat label="This week" value={stats.thisWeek.toFixed(1)} unit="km" />
              <Stat label="This month" value={stats.thisMonth.toFixed(1)} unit="km" />
              <Stat label="Last 12 mo" value={stats.total12.toFixed(1)} unit="km" />
              <Stat label="Runs · 12 mo" value={stats.runs12} />
            </div>

            <div className="panel overflow-hidden rounded-2xl border border-border bg-card">
              <div className="flex items-center justify-between border-b border-border px-5 py-3">
                <div className="flex min-w-0 items-center gap-2.5">
                  <Activity className="h-4 w-4 shrink-0 text-primary" />
                  <span className="text-md-plus font-semibold text-foreground">Volume</span>
                  {/* Range totals — what the selected date range adds up to. */}
                  <span className="truncate text-xs text-faint tabular-nums">
                    · {rangeTotals.km.toFixed(1)} km · {rangeTotals.runs} run{rangeTotals.runs === 1 ? '' : 's'}
                  </span>
                </div>
                <div className="flex rounded-lg border border-border p-0.5">
                  {['weekly', 'monthly'].map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setPeriod(p)}
                      className={
                        'focus-ring rounded-md px-2.5 py-1 text-xs font-semibold capitalize transition-colors ' +
                        (period === p
                          ? 'bg-accent text-accent-foreground'
                          : 'text-muted-foreground hover:text-foreground')
                      }
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
              <div className="p-4">
                {ranged.isLoading ? (
                  <Skeleton className="h-[160px] w-full rounded-[12px] sm:h-[220px]" />
                ) : chartData.length ? (
                  <VolumeChart
                    data={chartData}
                    {...xAxis}
                    // Pulse only when the newest point is the period still in progress.
                    liveLast={chartData.at(-1)?.period === (period === 'weekly' ? currentWeekKey() : currentMonthKey())}
                  />
                ) : (
                  <EmptyState
                    icon={Activity}
                    title="No runs in this range"
                    description="Widen the date range or sync more runs."
                  />
                )}
              </div>
            </div>
          </>
        )}
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div id="fitness" className="scroll-mt-28 sm:scroll-mt-36 lg:scroll-mt-40">
          <FitnessCard data={fitness.data} history={trends.data?.form?.fitness} />
        </div>
        <div id="records" className="scroll-mt-28 sm:scroll-mt-36 lg:scroll-mt-40">
          <RecordsCard records={records} />
        </div>
      </section>
    </div>
  )
}

function RacesTab() {
  const fitness = useTrainingFitness()
  return (
    <div className="space-y-5 md:space-y-8">
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div id="races" className="scroll-mt-28 sm:scroll-mt-36 lg:scroll-mt-40">
          <PlannedRacesCard />
        </div>
        <div id="predictions" className="scroll-mt-28 sm:scroll-mt-36 lg:scroll-mt-40">
          <PredictionsCard data={fitness.data} />
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeading id="blocks" icon={Layers} title="Race blocks" hint="the weeks before each race" />
        <RaceBlocksCard />
      </section>
    </div>
  )
}

function ActivitiesTab() {
  // Activities "load more" depth. Declared before the date range so a range
  // change can reset it (see useDateRange's onChange).
  const [pages, setPages] = useState(1)
  const resetPages = () => setPages(1)

  // The list's own date range — independent of the Volume range on Overview.
  // Default: last 365 days.
  const dr = useDateRange({ onChange: resetPages })
  const { dateFrom, dateTo } = dr

  const ownedShoes = useOwnedShoes()

  // Activities filters + "load more" (limit grows; offset stays 0 so the list
  // is one coherent page — cheap at personal scale and avoids client accumulation).
  const [shoeId, setShoeId] = useState(ALL)
  const [minKm, setMinKm] = useState('')
  // Debounced copy of minKm feeds the query key: every keystroke used to create
  // a new key (and a request).
  const [debouncedMinKm, setDebouncedMinKm] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDebouncedMinKm(minKm), 400)
    return () => clearTimeout(t)
  }, [minKm])
  const activityParams = useMemo(() => {
    const p = { limit: pages * PAGE, offset: 0 }
    if (dateFrom) p.date_from = dateFrom
    if (dateTo) p.date_to = dateTo
    if (shoeId !== ALL) p.shoe_id = Number(shoeId)
    const min = parseFloat(debouncedMinKm)
    if (!Number.isNaN(min) && min > 0) p.min_distance_km = min
    return p
  }, [dateFrom, dateTo, shoeId, debouncedMinKm, pages])

  const activities = useActivities(activityParams)
  const hasMore = activities.data && activities.data.length === pages * PAGE

  return (
    <section className="space-y-4">
      <SectionHeading id="activities" icon={ListOrdered} title="Activities" hint="filter by date, shoe and distance" />

      <DateRangeControls range={dr} />

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Shoe</Label>
          <Select value={shoeId} onValueChange={(v) => { setShoeId(v); resetPages() }}>
            <SelectTrigger><SelectValue placeholder="All shoes" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All shoes</SelectItem>
              {(ownedShoes.data || []).map((s) => (
                <SelectItem key={s.id} value={String(s.id)}>
                  {s.nickname || `${s.brand} ${s.model}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>Min. distance (km)</Label>
          <Input
            type="number"
            min="0"
            placeholder="e.g. 10"
            value={minKm}
            onChange={(e) => { setMinKm(e.target.value); resetPages() }}
          />
        </div>
      </div>

      {activities.isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[74px] rounded-[14px]" />
          ))}
        </div>
      ) : activities.isError ? (
        <ErrorState error={activities.error} onRetry={activities.refetch} />
      ) : activities.data?.length ? (
        <>
          <div className="space-y-2 sm:space-y-3">
            {activities.data.map((a) => (
              <ActivityRow key={a.strava_activity_id ?? `run-${a.shoe_run_id}`} activity={a} />
            ))}
          </div>
          {hasMore && (
            <div className="flex justify-center pt-1">
              <Button variant="outline" onClick={() => setPages((p) => p + 1)} disabled={activities.isFetching}>
                {activities.isFetching ? 'Loading…' : 'Load more'}
              </Button>
            </div>
          )}
        </>
      ) : (
        <EmptyState
          icon={ListOrdered}
          title="No activities match"
          description="Try widening the filters."
        />
      )}
    </section>
  )
}

// Tab ids double as the ?tab= values; Overview is the default and carries no param.
const TABS = [
  { id: 'overview', label: 'Overview', icon: Compass },
  { id: 'races', label: 'Races', icon: Flag },
  { id: 'activities', label: 'Activities', icon: ListOrdered },
]

export default function Training() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const tab = TABS.some((t) => t.id === tabParam) ? tabParam : 'overview' // unknown → Overview

  const selectTab = (id) => {
    const next = new URLSearchParams(searchParams)
    if (id === 'overview') next.delete('tab')
    else next.set('tab', id)
    setSearchParams(next, { replace: true })
  }

  // The header meta line is all the page itself needs; OverviewTab calls the same hooks (deduped).
  const { trailing365, recentWeekly, stats } = useVolumeStats()

  return (
    <div className="space-y-5 md:space-y-8">
      <PageHeader
        title="Training"
        meta={trailing365.data && recentWeekly.data ? [`${stats.thisWeek.toFixed(1)} km this week`] : undefined}
      >
        <SyncRunsButton />
      </PageHeader>

      {/* Segmented tab bar — same idiom as the Weekly/Monthly switch, sized up. */}
      <div role="tablist" aria-label="Training sections" className="flex rounded-lg border border-border p-0.5 sm:inline-flex">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`training-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`training-panel-${id}`}
            onClick={() => selectTab(id)}
            className={
              'focus-ring inline-flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-colors sm:flex-none ' +
              (tab === id
                ? 'bg-accent text-accent-foreground'
                : 'text-muted-foreground hover:text-foreground')
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`training-panel-${tab}`} aria-labelledby={`training-tab-${tab}`}>
        {tab === 'races' ? <RacesTab /> : tab === 'activities' ? <ActivitiesTab /> : <OverviewTab />}
      </div>
    </div>
  )
}
