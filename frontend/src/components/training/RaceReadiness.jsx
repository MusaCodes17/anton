import { Check, Info, Minus, X } from 'lucide-react'
import { formatDate, formatDuration } from '@/lib/utils'
import { Group, GroupError, Tile, TileSkeletons } from '@/components/training/StatTiles'

/**
 * "Ready for {race}?" — the race readiness checklist (R8.4.5), shown at the
 * bottom of the Races tab. A checklist with numbers, never a score: each row
 * is a stat tile with a status word. Every number and status is computed
 * server-side (race_advisor); this file only formats.
 */

const km = (v) => (v == null ? '—' : `${Number(v).toFixed(1)} km`)
const pace = (s) => (s == null ? '—' : `${formatDuration(s)}/km`)

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
