import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, CircleDashed, Info, Minus, X } from 'lucide-react'
import { cn, formatDate, formatDuration } from '@/lib/utils'
import { Group, GroupError, Tile, TileSkeletons } from '@/components/training/StatTiles'

/**
 * "Ready for {race}?" — the race readiness checklist (R8.4.5), shown at the
 * bottom of the Races tab. A checklist with numbers, never a score: each row
 * is a stat tile with a status word. Every number and status is computed
 * server-side (race_advisor); this file only formats.
 *
 * Drill-down (R11.1): a checklist tile with a period or evidence can be tapped
 * to open one detail panel below the tiles, showing the period and the runs
 * behind the number. One item is open at a time. `no_data` means the window
 * had no source data at all, so it renders as "No data", not as a failure.
 *
 * Past builds (R11.2): under the checklist, a table sets this build beside each
 * past build of the same class cut at the same days-before-race, with its
 * result. Numbers only, no ranking or better/worse colouring.
 *
 * Consistency and taper (R11.3): weeks run, breaks, and the last three weeks as
 * % of peak week (plus days since the long run) sit beside each past build, cut
 * at the same point. Descriptive only: neutral styling, no pass/fail, no targets.
 */

const READINESS_PANEL_ID = 'readiness-detail'

const km = (v) => (v == null ? '—' : `${Number(v).toFixed(1)} km`)
const pace = (s) => (s == null ? '—' : `${formatDuration(s)}/km`)

const STATUS = {
  met: { icon: Check, tone: 'text-primary', word: 'Met' },
  not_met: { icon: X, tone: 'text-warning', word: 'Not yet' },
  info: { icon: Info, tone: 'text-muted-foreground', word: 'Info' },
  'n/a': { icon: Minus, tone: 'text-faint', word: 'Not applicable' },
  no_data: { icon: CircleDashed, tone: 'text-muted-foreground', word: 'No data' },
}

function itemValue(item, weeksElapsed) {
  const { key, value, target, unit } = item
  // Consistency (R11.3): weeks with a run out of the weeks the block has run so far.
  if (key === 'weeks_with_running') return `${value ?? '—'} / ${weeksElapsed ?? '—'}`
  if (unit === '% of peak') return value == null ? '—' : `${value}%`
  if (unit === 'days') return value == null ? '—' : `${value} d`
  if (unit === 'breaks') return value == null ? '—' : String(value)
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

// Only items that can explain their number get a drill-down.
const isTappable = (item) => Boolean(item.period_from) || (item.evidence?.length ?? 0) > 0

function ageText(days) {
  if (days === 0) return 'today'
  if (days === 1) return '1 day ago'
  return `${days} days ago`
}

function ReadinessDetail({ item }) {
  const hasPeriod = Boolean(item.period_from && item.period_to)
  const evidence = item.evidence ?? []
  return (
    <div id={READINESS_PANEL_ID} className="panel col-span-full min-w-0 rounded-2xl border border-border bg-card p-4">
      <h4 className="text-sm font-semibold text-foreground">{item.label}</h4>
      {item.rule && <p className="mt-1 text-xs text-muted-foreground">{item.rule}</p>}
      {hasPeriod && (
        <p className="mt-2 text-xs text-muted-foreground">
          {`${formatDate(item.period_from)} – ${formatDate(item.period_to)}`}
        </p>
      )}
      {item.key === 'key_effort' && item.age_days != null && (
        <p className="mt-1 text-xs text-muted-foreground">{ageText(item.age_days)}</p>
      )}
      {evidence.length === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">No runs behind this number yet.</p>
      ) : (
        <ul className="mt-3 divide-y divide-border">
          {evidence.map((run, i) => {
            const name = run.name || 'Run'
            return (
              <li key={run.activity_id ?? i} className="flex min-w-0 items-baseline gap-3 py-2 text-xs">
                <span className="shrink-0 text-muted-foreground">{formatDate(run.run_date)}</span>
                <span className="min-w-0 flex-1 truncate text-foreground">
                  {run.activity_id ? (
                    <Link to={`/activities/${run.activity_id}`} className="focus-ring font-medium hover:underline">
                      {name}
                    </Link>
                  ) : (
                    name
                  )}
                  {run.segment && <span className="ml-1 text-faint">(segment)</span>}
                </span>
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  {run.distance_km != null ? `${Number(run.distance_km).toFixed(1)} km` : '—'}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

const MINUS = '−'
const oneDp = (v) => (v == null ? '—' : Number(v).toFixed(1))

// R11.3 cells. Consistency is the whole block; taper is the last weeks up to the
// cut date. Weeks are listed oldest first, with the unit "%" only on the last one.
const weeksRun = (c) => (c ? `${c.weeks_with_runs}/${c.weeks_elapsed}` : '—')
const breakCount = (c) => (c?.gaps ? c.gaps.length : '—')
const taperPcts = (taper, cutDate) => {
  const weeks = (taper?.weeks ?? []).filter((w) => cutDate != null && w.week_start <= cutDate)
  if (weeks.length === 0) return '—'
  const last = weeks[weeks.length - 1].pct_of_peak
  const parts = weeks.map((w) => (w.pct_of_peak == null ? '—' : String(w.pct_of_peak)))
  return parts.join(' · ') + (last == null ? '' : '%')
}
const sinceLongRun = (taper) => (taper?.days_since_long_run == null ? '—' : `${taper.days_since_long_run} d`)

function PastBuildResult({ build }) {
  const { race, result_vs_target_s: vs } = build
  if (race.status === 'dnf') return <span className="font-semibold text-warning">DNF</span>
  if (race.result_time_s == null) return '—'
  return (
    <>
      {formatDuration(race.result_time_s)}
      {vs != null && (
        <span className="ml-1 text-xs text-muted-foreground">
          ({vs < 0 ? MINUS : '+'}
          {formatDuration(Math.abs(vs))} vs target)
        </span>
      )}
    </>
  )
}

function PastBuilds({ rd }) {
  const builds = rd.past_builds ?? []
  if (builds.length === 0) return null
  const d = rd.days_before_race
  const th = 'px-2 py-1.5 text-right font-semibold'
  const td = 'whitespace-nowrap px-2 py-2 text-right tabular-nums'
  const longRuns = (rd.long_runs ?? []).length
  const taperOn = rd.taper != null

  return (
    <div className="min-w-0 space-y-2.5">
      <div>
        <h3 className="text-sm font-semibold text-foreground">At this point in past builds</h3>
        {d != null && (
          <p className="mt-0.5 text-xs text-muted-foreground">
            {`Each build up to ${d} day${d === 1 ? '' : 's'} before its race.`}
          </p>
        )}
      </div>
      <div className="panel min-w-0 overflow-x-auto rounded-2xl border border-border bg-card">
        <table className={cn('w-full text-xs', taperOn ? 'min-w-[44rem]' : 'min-w-[36rem]')}>
          <thead className="text-2xs uppercase tracking-wide text-faint">
            <tr className="border-b border-border">
              <th className="px-2 py-1.5 text-left font-semibold">Build</th>
              <th className={th}>Result</th>
              <th className={th}>km</th>
              <th className={th}>Runs</th>
              <th className={th}>Long runs</th>
              <th className={th}>Longest</th>
              <th className={th}>Peak week</th>
              <th className={th}>Weeks run</th>
              <th className={th}>Breaks</th>
              {taperOn && <th className={th}>Taper</th>}
              {taperOn && <th className={th}>Since long run</th>}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-border/60">
              <td className="px-2 py-2 text-left font-bold text-foreground">This build</td>
              <td className={td}>—</td>
              <td className={td}>{oneDp(rd.block_km)}</td>
              <td className={td}>{rd.block_runs ?? '—'}</td>
              <td className={td}>{longRuns}</td>
              <td className={td}>{oneDp(rd.longest_run?.distance_km)}</td>
              <td className={td}>{oneDp(rd.peak_week?.total_km)}</td>
              <td className={td}>{weeksRun(rd.consistency)}</td>
              <td className={td}>{breakCount(rd.consistency)}</td>
              {taperOn && <td className={td}>{taperPcts(rd.taper, rd.block_end)}</td>}
              {taperOn && <td className={td}>{sinceLongRun(rd.taper)}</td>}
            </tr>
            {builds.map((b) => (
              <tr key={b.race.id} className="border-b border-border/60 last:border-0">
                <td className="px-2 py-2 text-left">
                  {b.race.activity_id != null ? (
                    <Link to={`/activities/${b.race.activity_id}`} className="focus-ring font-semibold text-foreground hover:underline">
                      {b.race.name}
                    </Link>
                  ) : (
                    <span className="font-semibold text-foreground">{b.race.name}</span>
                  )}
                  <div className="text-xs text-muted-foreground">{formatDate(b.race.race_date)}</div>
                </td>
                <td className={td}><PastBuildResult build={b} /></td>
                <td className={td}>{oneDp(b.km)}</td>
                <td className={td}>{b.runs ?? '—'}</td>
                <td className={td}>{b.long_runs ?? '—'}</td>
                <td className={td}>{oneDp(b.longest_km)}</td>
                <td className={td}>{oneDp(b.peak_week_km)}</td>
                <td className={td}>{weeksRun(b.consistency)}</td>
                <td className={td}>{breakCount(b.consistency)}</td>
                {taperOn && <td className={td}>{taperPcts(b.taper, b.cut_date)}</td>}
                {taperOn && <td className={td}>{sinceLongRun(b.taper)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {taperOn && (
        <p className="text-xs text-muted-foreground">
          Taper: each of the last weeks as % of that build's peak week, oldest first.
        </p>
      )}
    </div>
  )
}

function ReadinessGroup({ rd }) {
  const race = rd.race
  const [openKey, setOpenKey] = useState(null)
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
  const openItem = rows.find((c) => c.key === openKey && isTappable(c)) ?? null

  return (
    <div className="space-y-4">
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
          const tile = (
            <Tile
              label={item.label}
              compact
              value={itemValue(item, rd.consistency?.weeks_elapsed)}
              sub={
                <span className="inline-flex items-center gap-1">
                  <Icon className={`h-3 w-3 shrink-0 ${s.tone}`} aria-hidden="true" />
                  <span>{s.word}</span>
                </span>
              }
            />
          )
          if (!isTappable(item)) return <div key={item.key} className="grid min-w-0">{tile}</div>
          const isOpen = openItem?.key === item.key
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => setOpenKey(isOpen ? null : item.key)}
              aria-expanded={isOpen}
              aria-controls={isOpen ? READINESS_PANEL_ID : undefined}
              className={cn(
                'focus-ring grid min-w-0 rounded-2xl text-left',
                isOpen && 'ring-2 ring-primary',
              )}
            >
              {tile}
            </button>
          )
        })}
        {openItem && <ReadinessDetail item={openItem} />}
      </Group>
      <PastBuilds rd={rd} />
    </div>
  )
}

/**
 * `readiness` is the React Query result of useRaceReadiness. Renders nothing
 * when there is no upcoming race (the Races tab hides the whole section then).
 */
export default function RaceReadiness({ readiness }) {
  // Branch on data presence, not isLoading: a paused/pending query (v5) has isLoading false and no data yet.
  if (readiness.data) {
    return readiness.data.has_race ? <ReadinessGroup rd={readiness.data} /> : null
  }
  if (readiness.isError) {
    return <GroupError title="Ready for your next race?" error={readiness.error} onRetry={readiness.refetch} />
  }
  return <TileSkeletons title="Ready for your next race?" />
}
