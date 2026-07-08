import { useMemo, useState } from 'react'
import { Activity, Trophy, ListOrdered, TrendingUp } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import PlannedRacesCard from '@/components/training/PlannedRacesCard'
import VolumeChart from '@/components/training/VolumeChart'
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
// "2026-W27" → { label: "W27", fullLabel: "Week 27 · 2026" }
function labelWeek(period) {
  const [y, w] = period.split('-W')
  return { label: `W${w}`, fullLabel: `Week ${parseInt(w, 10)} · ${y}` }
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
  const monthly = useTrainingSummary('monthly')
  const weekly = useTrainingSummary('weekly')
  const records = useTrainingRecords()
  const ownedShoes = useOwnedShoes()

  // Activities filters + "load more" (limit grows; offset stays 0 so the list
  // is one coherent page — cheap at personal scale and avoids client accumulation).
  const [year, setYear] = useState(ALL)
  const [shoeId, setShoeId] = useState(ALL)
  const [minKm, setMinKm] = useState('')
  const [pages, setPages] = useState(1)

  const activityParams = useMemo(() => {
    const p = { limit: pages * PAGE, offset: 0 }
    if (year !== ALL) p.year = Number(year)
    if (shoeId !== ALL) p.shoe_id = Number(shoeId)
    const min = parseFloat(minKm)
    if (!Number.isNaN(min) && min > 0) p.min_distance_km = min
    return p
  }, [year, shoeId, minKm, pages])

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

  // Chart data (chronological, last 12 periods)
  const chartData = useMemo(() => {
    const src = period === 'weekly' ? weekly.data : monthly.data
    if (!src) return []
    const label = period === 'weekly' ? labelWeek : labelMonth
    return [...src].slice(0, 12).reverse().map((b) => ({ ...b, ...label(b.period) }))
  }, [period, monthly.data, weekly.data])

  // Year options from the monthly periods (span all history)
  const years = useMemo(() => {
    const set = new Set((monthly.data || []).map((b) => b.period.split('-')[0]))
    return Array.from(set).sort((a, b) => b - a)
  }, [monthly.data])

  const summaryLoading = monthly.isLoading || weekly.isLoading

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
        <SectionHeading id="trends" icon={TrendingUp} title="Trends" />

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
                <div className="flex items-center gap-2.5">
                  <Activity className="h-4 w-4 text-primary" />
                  <span className="font-heading text-md-plus font-bold text-foreground">Volume</span>
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
                {chartData.length ? (
                  <VolumeChart data={chartData} />
                ) : (
                  <EmptyState
                    icon={Activity}
                    title="No training history"
                    description="Runs will appear here as they sync."
                  />
                )}
              </div>
            </div>
          </>
        )}
      </section>

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
        <SectionHeading id="activities" icon={ListOrdered} title="Activities" />

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label>Year</Label>
            <Select value={year} onValueChange={(v) => { setYear(v); resetPages() }}>
              <SelectTrigger><SelectValue placeholder="All years" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All years</SelectItem>
                {years.map((y) => <SelectItem key={y} value={y}>{y}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
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
