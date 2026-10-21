import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check, ChevronDown, CircleDashed, Info, Minus, X } from 'lucide-react'
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

// R11.7 finish estimate. Everything is computed server-side (finish_estimate);
// this only formats. The range is the headline, never the point.
const pct1 = (f) => (f == null ? '—' : `${(Number(f) * 100).toFixed(1)}%`)
const signedPct = (f) => (f == null ? '—' : `${f < 0 ? MINUS : '+'}${(Math.abs(Number(f)) * 100).toFixed(1)}%`)

// Grade chips: thin is a statement about the evidence, not a failure, so no red.
const GRADE_TONE = {
  strong: 'border-primary/40 text-primary',
  moderate: 'border-border text-muted-foreground',
  thin: 'border-warning/40 text-warning',
}

function RangeBar({ est }) {
  const { low_s: lo, high_s: hi, estimate_s: mid, target_time_s: target, target_position: pos } = est
  const span = hi - lo
  const midPct = span > 0 ? Math.min(100, Math.max(0, ((mid - lo) / span) * 100)) : 50
  const tgtPct = span > 0 && target != null ? Math.min(100, Math.max(0, ((target - lo) / span) * 100)) : 50
  const showTarget = target != null && pos != null
  return (
    <div className="relative h-8" role="img" aria-label={`Range ${formatDuration(lo)} to ${formatDuration(hi)}`}>
      {/* 1.5rem gutters hold the pinned "outside" markers so the bar always fits. */}
      <div className="absolute inset-x-6 top-1/2 h-2 -translate-y-1/2 rounded-full bg-primary/25" />
      <div className="absolute inset-x-6 top-0 h-full">
        <div className="absolute top-1/2 h-4 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-primary" style={{ left: `${midPct}%` }} />
        {showTarget && pos === 'inside' && (
          <div
            className="absolute top-0 h-full w-0.5 -translate-x-1/2 bg-foreground"
            style={{ left: `${tgtPct}%` }}
            title={`Target ${formatDuration(target)}`}
          />
        )}
      </div>
      {showTarget && pos === 'faster' && (
        <ArrowLeft className="absolute left-0 top-1/2 h-4 w-4 -translate-y-1/2 text-foreground" aria-hidden="true" />
      )}
      {showTarget && pos === 'slower' && (
        <ArrowRight className="absolute right-0 top-1/2 h-4 w-4 -translate-y-1/2 text-foreground" aria-hidden="true" />
      )}
    </div>
  )
}

function Disclosure({ id, title, children }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={id}
        className="focus-ring flex items-center gap-1 rounded text-xs font-semibold text-foreground"
      >
        <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', !open && '-rotate-90')} aria-hidden="true" />
        {title}
      </button>
      {open && (
        <div id={id} className="mt-2">
          {children}
        </div>
      )}
    </div>
  )
}

function EvidenceTable({ sources }) {
  const th = 'px-2 py-1.5 text-right font-semibold'
  const td = 'whitespace-nowrap px-2 py-2 text-right tabular-nums'
  return (
    <div className="panel min-w-0 overflow-x-auto rounded-2xl border border-border bg-card">
      <table className="w-full min-w-[34rem] text-xs">
        <thead className="text-2xs uppercase tracking-wide text-faint">
          <tr className="border-b border-border">
            <th className="px-2 py-1.5 text-left font-semibold">Source</th>
            <th className={th}>Time</th>
            <th className={th}>Date</th>
            <th className={th}>Equivalent</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((src, i) => (
            <tr
              key={`${src.kind}-${src.band}-${src.activity_id ?? i}`}
              className={cn('border-b border-border/60 last:border-0', src.sets_estimate && 'bg-primary/10')}
            >
              <td className="px-2 py-2 text-left">
                <span className="font-semibold text-foreground">{src.band}</span>
                <span className="ml-1 text-muted-foreground">
                  {`${km(src.distance_km)} · ${src.kind === 'race_pb' ? 'race' : src.segment ? 'segment of a longer run' : 'whole run'}`}
                </span>
                {src.sets_estimate && <span className="ml-1 font-semibold text-primary">sets the estimate</span>}
              </td>
              <td className={td}>{formatDuration(src.time_s)}</td>
              <td className={td}>
                {formatDate(src.run_date)}
                <span className="ml-1 text-muted-foreground">{`${src.age_days} d ago`}</span>
              </td>
              <td className={td}>{formatDuration(src.equivalent_s)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BacktestTable({ est }) {
  const rows = est.backtest ?? []
  const skipped = est.backtest_skipped ?? []
  const th = 'px-2 py-1.5 text-right font-semibold'
  const td = 'whitespace-nowrap px-2 py-2 text-right tabular-nums'
  return (
    <div className="min-w-0 space-y-2">
      <div className="panel min-w-0 overflow-x-auto rounded-2xl border border-border bg-card">
        <table className="w-full min-w-[32rem] text-xs">
          <thead className="text-2xs uppercase tracking-wide text-faint">
            <tr className="border-b border-border">
              <th className="px-2 py-1.5 text-left font-semibold">Race</th>
              <th className={th}>Actual</th>
              <th className={th}>Predicted</th>
              <th className={th}>Error</th>
              <th className={th}>Grade</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.name}-${r.race_date}-${i}`} className="border-b border-border/60 last:border-0">
                <td className="px-2 py-2 text-left">
                  <span className="font-semibold text-foreground">{r.name}</span>
                  <div className="text-xs text-muted-foreground">{formatDate(r.race_date)}</div>
                </td>
                <td className={td}>{formatDuration(r.actual_s)}</td>
                {r.predicted_s == null ? (
                  <td className={cn(td, 'text-muted-foreground')} colSpan={3}>no evidence</td>
                ) : (
                  <>
                    <td className={td}>{formatDuration(r.predicted_s)}</td>
                    <td className={td}>{signedPct(r.error_pct)}</td>
                    <td className={cn(td, 'text-muted-foreground')}>{r.grade ?? '—'}</td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > 0 && (
        <p className="text-xs text-muted-foreground">Error = predicted − actual; + means predicted slower.</p>
      )}
      {skipped.map((k, i) => (
        <p key={i} className="text-xs text-muted-foreground">{`${k.name} (${formatDate(k.race_date)}) — ${k.reason}`}</p>
      ))}
    </div>
  )
}

const TARGET_SENTENCE = {
  inside: 'inside',
  faster: 'faster than',
  slower: 'slower than',
}

function FinishEstimate({ est }) {
  if (!est) return null
  const ok = est.state === 'ok'
  const sources = est.sources ?? []
  const hasBacktest = (est.backtest?.length ?? 0) + (est.backtest_skipped?.length ?? 0) > 0
  const showEvidence = (ok || est.state === 'insufficient_history') && sources.length > 0
  const showBacktest = est.state !== 'unsupported_distance' && hasBacktest
  const thin = est.grade === 'thin'

  return (
    <div className="min-w-0 space-y-3">
      <h3 className="flex items-baseline gap-2 text-sm font-semibold text-foreground">
        Finish estimate
        <span className="text-2xs font-normal uppercase tracking-wide text-faint">heuristic</span>
      </h3>
      <div className="panel min-w-0 space-y-3 rounded-2xl border border-border bg-card p-4">
        {ok ? (
          <>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <p className="text-2xl font-bold tabular-nums text-foreground">
                {`${formatDuration(est.low_s)} – ${formatDuration(est.high_s)}`}
              </p>
              {est.grade && (
                <span className={cn('rounded-full border px-2 py-0.5 text-2xs font-semibold uppercase tracking-wide', GRADE_TONE[est.grade] ?? GRADE_TONE.moderate)}>
                  {est.grade}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">{`Middle: ${formatDuration(est.estimate_s)}`}</p>
            <RangeBar est={est} />
            {est.target_time_s != null && est.target_position && (
              <p className="text-xs text-foreground">
                {`Your target ${formatDuration(est.target_time_s)} is ${TARGET_SENTENCE[est.target_position] ?? 'compared with'} this range.`}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              {`Width = the largest miss this method made on your last ${est.backtest_n} races (${pct1(est.band_pct)})${thin ? ', ×1.5 because the evidence is thin' : ''}. Average miss ${pct1(est.backtest_mean_abs_pct)}.`}
            </p>
            {(est.grade_reasons?.length ?? 0) > 0 && (
              <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
                {est.grade_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <div className="rounded-xl border border-dashed border-border p-3 text-xs text-muted-foreground">
            <p>{est.message ?? 'No finish estimate available.'}</p>
            {est.state === 'insufficient_history' && est.estimate_s != null && (
              <p className="mt-1 text-foreground">{`Bare estimate (no range): ${formatDuration(est.estimate_s)}`}</p>
            )}
          </div>
        )}
        {showEvidence && (
          <Disclosure id="finish-evidence" title="Evidence">
            <EvidenceTable sources={sources} />
          </Disclosure>
        )}
        {showBacktest && (
          <Disclosure id="finish-backtest" title="How it did on past races">
            <BacktestTable est={est} />
          </Disclosure>
        )}
        {est.coros_prediction_s != null && (
          <p className="text-xs text-muted-foreground">
            {`COROS predicts ${formatDuration(est.coros_prediction_s)} (captured ${formatDate(est.coros_captured_at)}). A separate source — not part of this range and not backtested.`}
          </p>
        )}
      </div>
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
      <FinishEstimate est={rd.estimate} />
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
