import { useMemo, useState } from 'react'
import { Activity, Trophy, ListOrdered, TrendingUp } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import PlannedRacesCard from '@/components/training/PlannedRacesCard'
import VolumeChart from '@/components/training/VolumeChart'
import FitnessCard from '@/components/training/FitnessCard'
import PBCard from '@/components/training/PBCard'
import ActivityRow from '@/components/training/ActivityRow'
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
  useActivities,
  useOwnedShoes,
} from '@/hooks/useApi'

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

// Local-date ISO strings (YYYY-MM-DD) for the date-range picker (T4b).
function isoToday() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function isoDaysAgo(n) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
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

function Stat({ label, value, unit }) {
  return (
    <div className="rounded-[12px] border border-border bg-surface px-4 py-3">
      <div className="text-2xs font-bold uppercase tracking-[0.08em] text-faint">{label}</div>
      <div className="mt-1 font-heading text-2xl font-extrabold tracking-tight text-foreground tabular-nums">
        {value}
        {unit && <span className="ml-1 text-sm font-semibold text-faint">{unit}</span>}
      </div>
    </div>
  )
}

function SectionHeading({ id, icon: Icon, title, hint }) {
  return (
    <div id={id} className="flex items-baseline gap-2 scroll-mt-20">
      <Icon className="h-[18px] w-[18px] shrink-0 self-center text-accent-foreground" />
      <h2 className="font-heading text-lg font-extrabold tracking-tight text-foreground">{title}</h2>
      {hint && <span className="text-xs text-faint">{hint}</span>}
    </div>
  )
}

export default function Training() {
  const [period, setPeriod] = useState('weekly')

  // Shared date range (T4b) — drives the volume chart, the summary, and the
  // activities list. Default: last 90 days. React state only (resets on nav).
  const [dateFrom, setDateFrom] = useState(() => isoDaysAgo(90))
  const [dateTo, setDateTo] = useState(() => isoToday())
  const range = useMemo(() => ({
    ...(dateFrom ? { date_from: dateFrom } : {}),
    ...(dateTo ? { date_to: dateTo } : {}),
  }), [dateFrom, dateTo])

  const monthly = useTrainingSummary('monthly')          // unranged — the stat tiles' fixed windows
  const weekly = useTrainingSummary('weekly')            // unranged — this-week tile
  const ranged = useTrainingSummary(period, range)       // the volume chart honours the range
  const records = useTrainingRecords()
  const fitness = useTrainingFitness()
  const ownedShoes = useOwnedShoes()

  // Activities filters + "load more" (limit grows; offset stays 0 so the list
  // is one coherent page — cheap at personal scale and avoids client accumulation).
  const [shoeId, setShoeId] = useState(ALL)
  const [minKm, setMinKm] = useState('')
  const [pages, setPages] = useState(1)

  const activityParams = useMemo(() => {
    const p = { limit: pages * PAGE, offset: 0 }
    if (dateFrom) p.date_from = dateFrom
    if (dateTo) p.date_to = dateTo
    if (shoeId !== ALL) p.shoe_id = Number(shoeId)
    const min = parseFloat(minKm)
    if (!Number.isNaN(min) && min > 0) p.min_distance_km = min
    return p
  }, [dateFrom, dateTo, shoeId, minKm, pages])

  const activities = useActivities(activityParams)
  const hasMore = activities.data && activities.data.length === pages * PAGE

  const resetPages = () => setPages(1)

  // Stat strip
  const stats = useMemo(() => {
    const m = monthly.data || []
    const w = weekly.data || []
    const last12 = m.slice(0, 12)
    const total12 = last12.reduce((s, b) => s + b.total_km, 0)
    const runs12 = last12.reduce((s, b) => s + b.run_count, 0)
    const thisMonth = m.find((b) => b.period === currentMonthKey())?.total_km ?? 0
    const thisWeek = w.find((b) => b.period === currentWeekKey())?.total_km ?? 0
    return { thisWeek, thisMonth, total12, runs12 }
  }, [monthly.data, weekly.data])

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

  const summaryLoading = monthly.isLoading || weekly.isLoading

  // A range edit invalidates the current "load more" depth.
  const setRange = (from, to) => { setDateFrom(from); setDateTo(to); resetPages() }

  return (
    <div className="space-y-8">
      <PageHeader eyebrow="TRAIN" title="Training">
        <nav className="hidden gap-4 text-sm text-muted-foreground sm:flex">
          <a href="#trends" className="focus-ring rounded hover:text-foreground">Trends</a>
          <a href="#races" className="focus-ring rounded hover:text-foreground">Races</a>
          <a href="#records" className="focus-ring rounded hover:text-foreground">Records</a>
          <a href="#activities" className="focus-ring rounded hover:text-foreground">Activities</a>
        </nav>
      </PageHeader>

      {/* ── Trends (volume first) ──────────────────────────────── */}
      <section className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <SectionHeading id="trends" icon={TrendingUp} title="Trends" />
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Input
              type="date"
              value={dateFrom}
              max={dateTo || undefined}
              onChange={(e) => setRange(e.target.value, dateTo)}
              className="h-8 w-[9.5rem] px-2 py-1"
              aria-label="From date"
            />
            <span className="text-muted-foreground">→</span>
            <Input
              type="date"
              value={dateTo}
              min={dateFrom || undefined}
              onChange={(e) => setRange(dateFrom, e.target.value)}
              className="h-8 w-[9.5rem] px-2 py-1"
              aria-label="To date"
            />
            {[['90d', 90], ['6mo', 182], ['1y', 365]].map(([label, days]) => (
              <button
                key={label}
                type="button"
                onClick={() => setRange(isoDaysAgo(days), isoToday())}
                className="focus-ring rounded-md border border-border px-2 py-1 font-medium text-muted-foreground hover:text-foreground"
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {summaryLoading ? (
          <Skeleton className="h-[88px] w-full rounded-[12px]" />
        ) : monthly.isError ? (
          <ErrorState error={monthly.error} onRetry={monthly.refetch} />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="This week" value={stats.thisWeek.toFixed(1)} unit="km" />
              <Stat label="This month" value={stats.thisMonth.toFixed(1)} unit="km" />
              <Stat label="Last 12 mo" value={Math.round(stats.total12)} unit="km" />
              <Stat label="Runs · 12 mo" value={stats.runs12} />
            </div>

            <div className="overflow-hidden rounded-2xl border border-border bg-card">
              <div className="flex items-center justify-between border-b border-border px-5 py-3">
                <div className="flex min-w-0 items-center gap-2.5">
                  <Activity className="h-4 w-4 shrink-0 text-primary" />
                  <span className="font-heading text-md-plus font-bold text-foreground">Volume</span>
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
                  <Skeleton className="h-[220px] w-full rounded-[12px]" />
                ) : chartData.length ? (
                  <VolumeChart data={chartData} {...xAxis} />
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

      {/* ── Fitness (COROS snapshot, T5) — only when recorded ──── */}
      {fitness.data?.has_data && (
        <section id="fitness" className="scroll-mt-20">
          <FitnessCard data={fitness.data} />
        </section>
      )}

      {/* ── Races (after volume) ───────────────────────────────── */}
      <div id="races" className="scroll-mt-20">
        <PlannedRacesCard />
      </div>

      {/* ── Records ────────────────────────────────────────────── */}
      <section className="space-y-4">
        <SectionHeading
          id="records"
          icon={Trophy}
          title="Records"
          hint="fastest whole-activity time · not segment PBs"
        />
        {records.isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-[140px] rounded-[14px]" />
            ))}
          </div>
        ) : records.isError ? (
          <ErrorState error={records.error} onRetry={records.refetch} />
        ) : records.data?.records?.length ? (
          <div className="space-y-3">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {records.data.records.map((r) => (
                <PBCard key={r.band} record={r} />
              ))}
            </div>
            {records.data.excluded_count > 0 && (
              <p className="text-xs text-muted-foreground">
                {records.data.excluded_count} {records.data.excluded_count === 1 ? 'activity' : 'activities'} excluded
                {' '}({records.data.excluded_reason}) — tag interval/track sessions to reconsider.
              </p>
            )}
          </div>
        ) : (
          <EmptyState icon={Trophy} title="No records yet" description="Log some runs to see your bests." />
        )}
      </section>

      {/* ── Activities ─────────────────────────────────────────── */}
      <section className="space-y-4">
        <SectionHeading id="activities" icon={ListOrdered} title="Activities" hint="within the selected date range" />

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
            <div className="space-y-3">
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
    </div>
  )
}
