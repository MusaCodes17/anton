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
            value={itemValue(item)}
            sub={
              <span className="inline-flex items-center gap-1">
                <Icon className={`h-3 w-3 shrink-0 ${s.tone}`} aria-hidden="true" />
                <span>{s.word}</span>
              </span>
            }
          />
        )
        if (!isTappable(item)) return <div key={item.key} className="min-w-0">{tile}</div>
        const isOpen = openItem?.key === item.key
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => setOpenKey(isOpen ? null : item.key)}
            aria-expanded={isOpen}
            aria-controls={isOpen ? READINESS_PANEL_ID : undefined}
            className={cn(
              'focus-ring min-w-0 rounded-2xl text-left',
              isOpen && 'ring-2 ring-primary',
            )}
          >
            {tile}
          </button>
        )
      })}
      {openItem && <ReadinessDetail item={openItem} />}
    </Group>
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
