import { GRID, GroupError, Tile, TileSkeletons } from '@/components/training/StatTiles'

/**
 * The Training page's "Now" strip (R8.4.5): one grid of four stat tiles —
 * load verdict, form verdict, last 7 days, longest run — each a muted label,
 * one big value and one short sub-line. No charts, no rule text, no question
 * headings. Every number and verdict is computed server-side (training_trends);
 * this file only formats. Race readiness lives on the Races tab (RaceReadiness.jsx).
 * Tiles are 2-up on phones and 4-up from lg.
 */

const km = (v) => (v == null ? '—' : `${Number(v).toFixed(1)} km`)

const LOAD_VERDICT = {
  building: { tone: 'text-primary', word: 'Building' },
  holding: { tone: 'text-muted-foreground', word: 'Holding' },
  easing: { tone: 'text-muted-foreground', word: 'Easing' },
  taper: { tone: 'text-primary', word: 'Taper' },
}

const FORM_VERDICT = {
  improving: { tone: 'text-primary', word: 'Improving' },
  steady: { tone: 'text-muted-foreground', word: 'Steady' },
  slipping: { tone: 'text-warning', word: 'Slipping' },
}

/**
 * `trends` is the React Query result of useTrainingTrends.
 */
export default function NowStrip({ trends }) {
  // Branch on data presence, not isLoading: a paused/pending query (v5) has isLoading false and no data yet.
  if (!trends.data) {
    return trends.isError ? (
      <GroupError title="Now" error={trends.error} onRetry={trends.refetch} />
    ) : (
      <TileSkeletons heading={false} />
    )
  }

  const { load, form } = trends.data

  const lv = LOAD_VERDICT[load.verdict]
  let loadValue = lv?.word ?? load.verdict
  let loadSub = 'Last 7 days vs avg week of the 28 before'
  if (load.verdict === 'no_baseline') {
    loadValue = '—'
    loadSub = 'Not enough recent running'
  } else if (load.verdict === 'taper' && load.taper_race) {
    const d = load.taper_race.days_to_race
    loadSub = `${load.taper_race.name} ${d === 0 ? 'today' : `in ${d} day${d === 1 ? '' : 's'}`}`
  }

  const fv = FORM_VERDICT[form.verdict]
  const enough = form.verdict !== 'not_enough_data'

  return (
    <div className={GRID}>
      <Tile label="Load verdict" value={loadValue} tone={lv?.tone} sub={loadSub} />
      <Tile
        label="Form verdict"
        value={enough ? (fv?.word ?? form.verdict) : '—'}
        tone={enough ? fv?.tone : undefined}
        sub={enough ? 'Speed per heartbeat, steady runs' : `Needs ${form.min_steady_runs} steady runs`}
      />
      <Tile
        label="Last 7 days"
        value={km(load.last7_km)}
        sub={`${load.last7_runs} run${load.last7_runs === 1 ? '' : 's'}`}
      />
      <Tile
        label="Longest run"
        value={km(load.last7_longest_km)}
        sub={`Last 7 days · prior 28: ${km(load.prior_longest_km)}`}
      />
    </div>
  )
}
