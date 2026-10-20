import { Check, Info, Minus, RefreshCw, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDate, formatDuration } from '@/lib/utils'

/**
 * The Training page's "Now" section (R8.4.5): up to three plain-question
 * groups — "Building or holding?" (load), "Is form improving?" (form) and
 * "Ready for {race}?" (readiness) — each a row of stat tiles (muted label,
 * one big value, one short sub-line). No charts, no rule text. Every number
 * and verdict is computed server-side (training_trends, race_advisor); this
 * file only formats. Tiles are 2-up on phones and 4-up from lg.
 */

const km = (v) => (v == null ? '—' : `${Number(v).toFixed(1)} km`)
const pace = (s) => (s == null ? '—' : `${formatDuration(s)}/km`)

// ── shared shell ─────────────────────────────────────────────────

const GRID = 'grid grid-cols-2 gap-3 lg:grid-cols-4'

function Group({ title, children }) {
  return (
    <div className="space-y-2.5">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <div className={GRID}>{children}</div>
    </div>
  )
}

// `tone` colours the value; the word itself always carries the meaning.
function Tile({ label, value, unit, sub, tone = 'text-foreground', compact = false }) {
  return (
    <div className="panel min-w-0 rounded-2xl border border-border bg-card p-4">
      <div className="line-clamp-2 text-xs text-muted-foreground" title={typeof label === 'string' ? label : undefined}>{label}</div>
      <div className={`mt-1.5 font-heading ${compact ? 'text-lg sm:text-xl' : 'text-2xl sm:text-3xl'} font-bold leading-none tabular-nums ${tone}`}>
        {value}
        {unit && <small className="ml-1 text-xs font-medium tracking-normal text-muted-foreground">{unit}</small>}
      </div>
      {sub && <div className="mt-1.5 text-xs text-muted-foreground">{sub}</div>}
    </div>
  )
}

function TileSkeletons({ title }) {
  return (
    <div className="space-y-2.5">
      <Skeleton className="h-4 w-40" aria-label={title} />
      <div className={GRID}>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="panel space-y-2.5 rounded-2xl border border-border bg-card p-4">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-7 w-20" />
            <Skeleton className="h-3 w-24" />
          </div>
        ))}
      </div>
    </div>
  )
}

function GroupError({ title, error, onRetry }) {
  return (
    <div className="space-y-2.5">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <div className="rounded-2xl border border-border bg-card p-4">
        <p className="text-sm text-destructive">Couldn't load this answer.</p>
        <p className="mt-1 text-xs text-muted-foreground">{error?.message || 'Unable to load data.'}</p>
        {onRetry && (
          <div className="mt-3">
            <Button variant="outline" size="sm" onClick={onRetry}>
              <RefreshCw className="h-4 w-4" /> Try again
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Load: "Building or holding?" ────────────────────────────────

const LOAD_VERDICT = {
  building: { tone: 'text-primary', word: 'Building' },
  holding: { tone: 'text-muted-foreground', word: 'Holding' },
  easing: { tone: 'text-muted-foreground', word: 'Easing' },
  taper: { tone: 'text-primary', word: 'Taper' },
}

function LoadGroup({ load }) {
  const v = LOAD_VERDICT[load.verdict]
  let verdictValue = v?.word ?? load.verdict
  let verdictSub = 'Last 7 days vs avg week of the 28 before'
  if (load.verdict === 'no_baseline') {
    verdictValue = '—'
    verdictSub = 'Not enough recent running'
  } else if (load.verdict === 'taper' && load.taper_race) {
    const d = load.taper_race.days_to_race
    verdictSub = `${load.taper_race.name} ${d === 0 ? 'today' : `in ${d} day${d === 1 ? '' : 's'}`}`
  }
  return (
    <Group title="Building or holding?">
      <Tile label="Load verdict" value={verdictValue} tone={v?.tone} sub={verdictSub} />
      <Tile
        label="Last 7 days"
        value={km(load.last7_km)}
        sub={`${load.last7_runs} run${load.last7_runs === 1 ? '' : 's'}`}
      />
      <Tile
        label="Prior avg week"
        value={km(load.prior_avg_week_km)}
        sub={`Ratio ${load.ratio != null ? load.ratio.toFixed(2) : '—'}`}
      />
      <Tile
        label="Longest run, last 7 days"
        value={km(load.last7_longest_km)}
        sub={`Prior 28 days: ${km(load.prior_longest_km)}`}
      />
    </Group>
  )
}

// ── Form: "Is form improving?" ──────────────────────────────────

const FORM_VERDICT = {
  improving: { tone: 'text-primary', word: 'Improving' },
  steady: { tone: 'text-muted-foreground', word: 'Steady' },
  slipping: { tone: 'text-warning', word: 'Slipping' },
}

const perBeat = (v) => (v == null ? '—' : Number(v).toFixed(3))
const runsText = (n) => `${n} steady run${n === 1 ? '' : 's'}`

function FormGroup({ form }) {
  const v = FORM_VERDICT[form.verdict]
  const enough = form.verdict !== 'not_enough_data'
  const weeksRecent = Math.round(form.recent_days / 7)
  const weeksBase = Math.round(form.baseline_days / 7)
  const pct = form.change_pct
  const effort = (form.best_efforts || []).find((b) => b.recent)

  return (
    <Group title="Is form improving?">
      <Tile
        label="Form verdict"
        value={enough ? (v?.word ?? form.verdict) : '—'}
        tone={enough ? v?.tone : undefined}
        sub={enough ? 'Speed per heartbeat, steady runs' : `Needs ${form.min_steady_runs} steady runs`}
      />
      <Tile
        label={`Last ${weeksRecent} wks`}
        value={perBeat(form.recent_m_per_beat)}
        unit={form.recent_m_per_beat != null ? 'm/beat' : undefined}
        sub={runsText(form.recent_steady_runs)}
      />
      <Tile
        label={`${weeksBase} wks before`}
        value={perBeat(form.baseline_m_per_beat)}
        unit={form.baseline_m_per_beat != null ? 'm/beat' : undefined}
        sub={
          enough && pct != null
            ? `${pct > 0 ? '+' : pct < 0 ? '−' : '±'}${Math.abs(pct).toFixed(1)}% change`
            : runsText(form.baseline_steady_runs)
        }
      />
      {effort ? (
        <Tile
          label={`Best ${effort.label}, 90 days`}
          value={formatDuration(effort.recent.time_s)}
          sub={
            effort.pct_off_all_time != null && effort.pct_off_all_time > 0
              ? `${effort.pct_off_all_time.toFixed(1)}% off ${formatDuration(effort.all_time?.time_s)}`
              : 'All-time best'
          }
        />
      ) : (
        <Tile label="Best effort, 90 days" value="—" sub="No recent efforts" />
      )}
    </Group>
  )
}

// ── Readiness: "Ready for {race}?" — a checklist with numbers, never a score ──

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

function ReadinessGroup({ rd }) {
  const race = rd.race
  const d = race.days_to_race
  const when = d === 0 ? 'Race day' : d < 14 ? `${d} day${d === 1 ? '' : 's'}` : `${race.weeks_to_race} wks`
  const raceSub = [formatDate(race.race_date), race.distance_km != null ? km(race.distance_km) : null]
    .filter(Boolean)
    .join(' · ')
  const block = rd.block_started
    ? ` · block ${km(rd.block_km)}, ${rd.block_runs} run${rd.block_runs === 1 ? '' : 's'}`
    : ''
  // weeks_to_go is already the Race tile, so the checklist starts at the block rows.
  const rows = rd.checklist.filter((c) => c.key !== 'weeks_to_go')

  return (
    <Group title={`Ready for ${race.name}?`}>
      <Tile label="Race" value={when} sub={`${raceSub}${block}`} />
      <Tile
        label="Target"
        value={race.target_time_s ? formatDuration(race.target_time_s) : '—'}
        sub={race.target_time_s ? race.target_pace : 'No target time'}
      />
      {rows.map((item) => {
        const s = STATUS[item.status] ?? STATUS.info
        const Icon = s.icon
        return (
          <Tile
            key={item.key}
            label={item.label}
            compact
            value={itemValue(item)}
            sub={
              <span className="inline-flex items-center gap-1">
                <Icon className={`h-3 w-3 shrink-0 ${s.tone}`} aria-hidden="true" />
                <span>{s.word}</span>
              </span>
            }
          />
        )
      })}
    </Group>
  )
}

// ── the strip ───────────────────────────────────────────────────

/**
 * `trends` / `readiness` are React Query results (useTrainingTrends,
 * useRaceReadiness).
 */
export default function NowStrip({ trends, readiness }) {
  // Hide the readiness group only once we know there's no race; while loading
  // show a skeleton so it doesn't pop in. Branch on data presence, not
  // isLoading: a paused/pending query (v5) has isLoading false and no data yet.
  return (
    <div className="space-y-5">
      {trends.data ? (
        <>
          <LoadGroup load={trends.data.load} />
          <FormGroup form={trends.data.form} />
        </>
      ) : trends.isError ? (
        <>
          <GroupError title="Building or holding?" error={trends.error} onRetry={trends.refetch} />
          <GroupError title="Is form improving?" error={trends.error} />
        </>
      ) : (
        <>
          <TileSkeletons title="Building or holding?" />
          <TileSkeletons title="Is form improving?" />
        </>
      )}
      {readiness.data ? (
        readiness.data.has_race ? <ReadinessGroup rd={readiness.data} /> : null
      ) : readiness.isError ? (
        <GroupError title="Ready for your next race?" error={readiness.error} onRetry={readiness.refetch} />
      ) : (
        <TileSkeletons title="Ready for your next race?" />
      )}
    </div>
  )
}
