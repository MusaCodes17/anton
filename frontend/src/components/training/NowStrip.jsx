import {
  ArrowRight,
  Check,
  Flag,
  Info,
  Minus,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react'
import {
  Bar,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDate, formatDuration } from '@/lib/utils'

/**
 * The Training page's "Now" strip (R8.4.5): three answer cards — Load, Form,
 * Next race — each a verdict line in words, one line of numbers, one small
 * chart. Every number and verdict is computed server-side (training_trends,
 * race_advisor); this file only formats. Stacked on mobile (answers first at
 * 380 px), a 3-column row on desktop — 2 columns when no race is planned, so
 * the readiness card's absence leaves no hole.
 */

const PRIMARY = 'var(--primary)'
const MUTED = 'var(--muted-foreground)'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// Phone chart height (px); sm+ keeps 88. Footers are never hidden (B20).
const chartHeight = (isSm) => (isSm ? 88 : 64)

const km = (v) => (v == null ? '—' : `${Number(v).toFixed(1)} km`)
const pace = (s) => (s == null ? '—' : `${formatDuration(s)}/km`)

// ── shared shell ─────────────────────────────────────────────────

function NowCard({ eyebrow, children, footer }) {
  return (
    <div className="flex min-w-0 flex-col rounded-2xl border border-border bg-card p-4">
      <div className="text-2xs font-bold uppercase tracking-[0.08em] text-faint">{eyebrow}</div>
      <div className="mt-1.5 flex flex-1 flex-col">{children}</div>
      {footer && <p className="mt-2 text-2xs leading-snug text-faint sm:mt-3">{footer}</p>}
    </div>
  )
}

// The verdict: icon + words. Colour is a second cue, never the only one.
function Verdict({ icon: Icon, tone = 'text-foreground', children }) {
  return (
    <div className="flex items-start gap-2">
      <Icon className={`mt-[3px] h-4 w-4 shrink-0 ${tone}`} aria-hidden="true" />
      <p className="font-heading text-md-plus font-bold leading-snug text-foreground">{children}</p>
    </div>
  )
}

function Numbers({ children }) {
  return <p className="mt-1 text-xs leading-relaxed text-muted-foreground tabular-nums">{children}</p>
}

function CardSkeleton() {
  return (
    <div className="space-y-3 rounded-2xl border border-border bg-card p-4">
      <Skeleton className="h-3 w-16" />
      <Skeleton className="h-5 w-4/5" />
      <Skeleton className="h-3 w-3/5" />
      <Skeleton className="h-16 w-full sm:h-[88px] rounded-[10px]" />
    </div>
  )
}

function CardError({ eyebrow, error, onRetry }) {
  return (
    <NowCard eyebrow={eyebrow}>
      <p className="text-sm text-destructive">Couldn't load this answer.</p>
      <p className="mt-1 text-xs text-muted-foreground">{error?.message || 'Unable to load data.'}</p>
      {onRetry && (
        <div className="mt-3">
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw className="h-4 w-4" /> Try again
          </Button>
        </div>
      )}
    </NowCard>
  )
}

function ChartTooltip({ active, payload, render }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-[10px] border border-border bg-popover px-2.5 py-1.5 text-xs tabular-nums">
      {render(payload[0].payload)}
    </div>
  )
}

// ── Load: "am I building or holding?" ───────────────────────────

const LOAD_VERDICT = {
  building: { icon: TrendingUp, tone: 'text-primary', word: 'Building' },
  holding: { icon: ArrowRight, tone: 'text-muted-foreground', word: 'Holding' },
  easing: { icon: TrendingDown, tone: 'text-muted-foreground', word: 'Easing' },
  taper: { icon: Flag, tone: 'text-primary', word: 'Taper' },
}

function LoadChart({ weeks }) {
  const isSm = useMediaQuery('(min-width: 640px)')
  const last = weeks.length - 1
  return (
    <ResponsiveContainer width="100%" height={chartHeight(isSm)}>
      <ComposedChart data={weeks} margin={{ top: 4, right: 0, left: 0, bottom: 0 }} barCategoryGap={2}>
        <XAxis dataKey="period" hide />
        <YAxis hide domain={[0, 'dataMax']} />
        <Tooltip
          cursor={{ fill: 'var(--chart-grid)', fillOpacity: 0.6 }}
          content={
            <ChartTooltip
              render={(d) => (
                <>
                  <div className="font-semibold text-foreground">{d.fullLabel}</div>
                  <div className="text-muted-foreground">{km(d.total_km)}</div>
                  {d.rolling_4wk_km != null && (
                    <div className="text-faint">4-wk avg {km(d.rolling_4wk_km)}</div>
                  )}
                </>
              )}
            />
          }
        />
        <Bar dataKey="total_km" radius={[4, 4, 0, 0]} isAnimationActive={false}>
          {weeks.map((w, i) => (
            <Cell key={w.period} fill={PRIMARY} fillOpacity={i === last ? 1 : 0.4} />
          ))}
        </Bar>
        <Line
          type="monotone"
          dataKey="rolling_4wk_km"
          stroke={MUTED}
          strokeWidth={2}
          strokeDasharray="4 3"
          dot={false}
          activeDot={false}
          connectNulls={false}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function LoadCard({ load, weeks }) {
  const v = LOAD_VERDICT[load.verdict]
  const vs = `${km(load.last7_km)} in the last 7 days vs ${km(load.prior_avg_week_km)} avg week`
  let verdict
  if (load.verdict === 'no_baseline') {
    verdict = <Verdict icon={Minus}>Not enough recent running to compare</Verdict>
  } else if (load.verdict === 'taper' && load.taper_race) {
    const d = load.taper_race.days_to_race
    verdict = (
      <Verdict icon={v.icon} tone={v.tone}>
        Taper — {load.taper_race.name} {d === 0 ? 'today' : `in ${d} day${d === 1 ? '' : 's'}`}
      </Verdict>
    )
  } else {
    verdict = <Verdict icon={v?.icon ?? Minus} tone={v?.tone}>{v?.word ?? load.verdict} — {vs}</Verdict>
  }

  const runs = `${load.last7_runs} run${load.last7_runs === 1 ? '' : 's'}`
  const numbers =
    load.verdict === 'no_baseline'
      ? `No runs in the 4 weeks before the last 7 days · last 7 days ${km(load.last7_km)}, ${runs}`
      : `${load.verdict === 'taper' ? `${vs} · ` : ''}${load.ratio?.toFixed(2)}× · ${runs} · longest ${km(load.last7_longest_km)} (prior 4 wks ${km(load.prior_longest_km)})`

  const hasWeeks = weeks.some((w) => w.total_km > 0)
  return (
    <NowCard
      eyebrow="Load"
      footer={`Heuristic: last 7 days vs the average week of the 28 days before — building above ${load.building_above}×, easing below ${load.easing_below}×, taper when easing within 3 weeks of a planned race.`}
    >
      {verdict}
      <Numbers>{numbers}</Numbers>
      <div className="mt-3">
        {hasWeeks ? (
          <>
            <LoadChart weeks={weeks} />
            <p className="mt-1 text-2xs text-faint">Weekly km, last 12 weeks · dashed = 4-week average</p>
          </>
        ) : (
          <p className="py-6 text-center text-xs text-faint">No runs in the last 12 weeks</p>
        )}
      </div>
    </NowCard>
  )
}

// ── Form: "what's my form now?" ─────────────────────────────────

const FORM_VERDICT = {
  improving: { icon: TrendingUp, tone: 'text-primary' },
  steady: { icon: ArrowRight, tone: 'text-muted-foreground' },
  slipping: { icon: TrendingDown, tone: 'text-warning' },
}

function formVerdictText(form) {
  const pct = form.change_pct != null ? Math.abs(form.change_pct).toFixed(1) : null
  switch (form.verdict) {
    case 'improving':
      return `Improving — ${pct}% more metres per heartbeat`
    case 'slipping':
      return `Slipping — ${pct}% fewer metres per heartbeat`
    case 'steady':
      return `Steady — efficiency within ±${form.improving_above_pct}%`
    default:
      return 'Not enough steady runs with heart rate to compare'
  }
}

function FormChart({ months }) {
  const isSm = useMediaQuery('(min-width: 640px)')
  const data = months.map((m) => {
    const [y, mm] = m.month.split('-')
    const mon = MONTHS[parseInt(mm, 10) - 1]
    return { ...m, label: mon, fullLabel: `${mon} ${y}` }
  })
  return (
    <ResponsiveContainer width="100%" height={chartHeight(isSm)}>
      <LineChart data={data} margin={{ top: 6, right: 6, left: 6, bottom: 0 }}>
        <XAxis
          dataKey="label"
          tick={{ fontSize: 10, fill: 'var(--faint)' }}
          axisLine={false}
          tickLine={false}
          interval="preserveStartEnd"
          fontFamily="JetBrains Mono, monospace"
        />
        <YAxis hide domain={['dataMin - 0.02', 'dataMax + 0.02']} />
        <Tooltip
          cursor={{ stroke: PRIMARY, strokeOpacity: 0.35, strokeWidth: 1 }}
          content={
            <ChartTooltip
              render={(d) => (
                <>
                  <div className="font-semibold text-foreground">{d.fullLabel}</div>
                  <div className="text-muted-foreground">
                    {d.m_per_beat != null ? `${d.m_per_beat.toFixed(3)} m/beat` : 'Too few steady runs'}
                  </div>
                  <div className="text-faint">{d.steady_runs} steady run{d.steady_runs === 1 ? '' : 's'}</div>
                </>
              )}
            />
          }
        />
        <Line
          type="monotone"
          dataKey="m_per_beat"
          stroke={PRIMARY}
          strokeWidth={2}
          dot={{ r: 2.5, fill: PRIMARY, strokeWidth: 0 }}
          activeDot={{ r: 4, fill: PRIMARY, stroke: 'var(--card)', strokeWidth: 2 }}
          connectNulls={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

function FormCard({ form }) {
  const v = FORM_VERDICT[form.verdict]
  const enough = form.verdict !== 'not_enough_data'
  const weeksRecent = Math.round(form.recent_days / 7)
  const weeksBase = Math.round(form.baseline_days / 7)
  const numbers = enough
    ? `${form.recent_m_per_beat?.toFixed(3)} m/beat, last ${weeksRecent} wks (${form.recent_steady_runs} runs) vs ${form.baseline_m_per_beat?.toFixed(3)}, ${weeksBase} wks before (${form.baseline_steady_runs})`
    : `Needs ${form.min_steady_runs} steady runs in the last ${weeksRecent} weeks and ${form.min_steady_runs} in the ${weeksBase} before — have ${form.recent_steady_runs} and ${form.baseline_steady_runs}`

  // 90-day best vs all-time, one compact line per distance that has a recent effort.
  const efforts = (form.best_efforts || []).filter((b) => b.recent)
  const hasMonths = form.months?.some((m) => m.m_per_beat != null)

  return (
    <NowCard
      eyebrow="Form"
      footer={`Heuristic: speed per heartbeat on steady runs (≥ 5 km, heart rate, untagged/Easy/Long Run) — ±${form.improving_above_pct}% over the last ${weeksRecent} weeks vs the ${weeksBase} before. Gaps: months with fewer than ${form.min_month_runs} steady runs.`}
    >
      <Verdict icon={v?.icon ?? Minus} tone={v?.tone}>{formVerdictText(form)}</Verdict>
      <Numbers>{numbers}</Numbers>
      {efforts.length > 0 && (
        <Numbers>
          {efforts.map((b, i) => (
            <span key={b.label}>
              {i > 0 && ' · '}
              Best {b.label}, 90 days: {formatDuration(b.recent.time_s)}
              {b.pct_off_all_time != null && b.pct_off_all_time > 0
                ? `, ${b.pct_off_all_time.toFixed(1)}% off all-time ${formatDuration(b.all_time?.time_s)}`
                : ', all-time best'}
            </span>
          ))}
        </Numbers>
      )}
      <div className="mt-3">
        {hasMonths ? (
          <>
            <FormChart months={form.months} />
            <p className="mt-1 text-2xs text-faint">Metres per heartbeat by month, last 12 months</p>
          </>
        ) : (
          <p className="py-6 text-center text-xs text-faint">No month has enough steady runs to plot yet</p>
        )}
      </div>
    </NowCard>
  )
}

// ── Next race: "am I ready?" — a checklist with numbers, never a score ──

const STATUS = {
  met: { icon: Check, tone: 'text-primary', word: 'Met' },
  not_met: { icon: X, tone: 'text-warning', word: 'Not yet' },
  info: { icon: Info, tone: 'text-muted-foreground', word: 'Info' },
  'n/a': { icon: Minus, tone: 'text-faint', word: 'Not applicable' },
}

function itemValue(item) {
  const { value, target, unit } = item
  if (unit === 's/km') {
    if (value == null) return target != null ? `— vs ${pace(target)}` : '—'
    return target != null ? `${pace(value)} vs ${pace(target)}` : pace(value)
  }
  if (unit === 'km') {
    if (value == null) return target != null ? `— / ${target} km` : '—'
    return target != null ? `${value.toFixed(1)} / ${target} km` : km(value)
  }
  if (unit === 'runs') {
    if (value == null) return target != null ? `— / ${target}` : '—'
    return target != null ? `${value} / ${target}` : String(value)
  }
  return value == null ? '—' : `${value} ${unit}`
}

function ReadinessCard({ rd }) {
  const race = rd.race
  const d = race.days_to_race
  const when = d === 0 ? 'today' : d < 14 ? `in ${d} day${d === 1 ? '' : 's'}` : `in ${race.weeks_to_race} weeks`
  const facts = [
    race.distance_km != null ? km(race.distance_km) : null,
    formatDate(race.race_date),
    race.target_time_s ? `target ${formatDuration(race.target_time_s)} (${race.target_pace})` : 'no target time',
  ].filter(Boolean)
  // weeks_to_go is already the verdict line, so the list starts at the block rows.
  const rows = rd.checklist.filter((c) => c.key !== 'weeks_to_go')

  return (
    <NowCard
      eyebrow="Next race"
      footer={`Heuristic: rules scale with race distance${rd.block_weeks ? ` over a ${rd.block_weeks}-week block` : ''}. A checklist, not a score.`}
    >
      <Verdict icon={Flag} tone="text-primary">{race.name} {when}</Verdict>
      <Numbers>
        {facts.join(' · ')}
        {rd.block_started && ` · block ${km(rd.block_km)}, ${rd.block_runs} run${rd.block_runs === 1 ? '' : 's'}`}
      </Numbers>
      <ul className="mt-3 divide-y divide-divider">
        {rows.map((item) => {
          const s = STATUS[item.status] ?? STATUS.info
          const Icon = s.icon
          return (
            <li key={item.key} className="flex items-start gap-2 py-1.5">
              <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${s.tone}`} aria-label={s.word} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-2">
                  <span className="text-xs font-medium text-foreground">{item.label}</span>
                  <span className="text-xs text-muted-foreground tabular-nums">{itemValue(item)}</span>
                </div>
                {item.rule && <p className="text-2xs leading-snug text-faint">{item.rule}</p>}
              </div>
            </li>
          )
        })}
      </ul>
    </NowCard>
  )
}

// ── the strip ───────────────────────────────────────────────────

/**
 * `trends` / `readiness` are React Query results (useTrainingTrends,
 * useRaceReadiness); `weeks` is the last 12 ISO weeks of the weekly summary,
 * zero-filled and chronological (built by the page — presentation only).
 */
export default function NowStrip({ trends, readiness, weeks }) {
  // Hide the readiness slot only once we know there's no race; while loading,
  // keep three columns so the row doesn't reflow from 2 → 3.
  // Branch on data presence, not isLoading: a paused/pending query (v5) has
  // isLoading false and no data yet.
  const showReadiness = !readiness.data || readiness.data.has_race
  const cols = showReadiness ? 'lg:grid-cols-3' : 'lg:grid-cols-2'

  return (
    <div className={`grid grid-cols-1 gap-4 ${cols}`}>
      {trends.data ? null : trends.isError ? (
        <>
          <CardError eyebrow="Load" error={trends.error} onRetry={trends.refetch} />
          <CardError eyebrow="Form" error={trends.error} />
        </>
      ) : (
        <>
          <CardSkeleton />
          <CardSkeleton />
        </>
      )}
      {trends.data && (
        <>
          <LoadCard load={trends.data.load} weeks={weeks} />
          <FormCard form={trends.data.form} />
        </>
      )}
      {readiness.data ? (
        readiness.data.has_race ? <ReadinessCard rd={readiness.data} /> : null
      ) : readiness.isError ? (
        <CardError eyebrow="Next race" error={readiness.error} onRetry={readiness.refetch} />
      ) : (
        <CardSkeleton />
      )}
    </div>
  )
}
