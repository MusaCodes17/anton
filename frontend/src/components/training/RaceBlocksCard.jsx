import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { LineChart, Line, Customized, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { Layers } from 'lucide-react'
import { ErrorState, EmptyState } from '@/components/StatusViews'
import { Skeleton } from '@/components/ui/skeleton'
import { axisProps, gridProps, lineCursor, ChartTooltip, ChartLegend } from '@/components/charts/signal'
import { useRaceBlocks } from '@/hooks/useApi'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { formatDate, formatDuration, cn } from '@/lib/utils'

const CLASSES = [
  { value: 'marathon', label: 'Marathon', noun: 'marathon' },
  { value: 'half', label: 'Half', noun: 'half-marathon' },
  { value: '10k', label: '10k', noun: '10k' },
]

// localStorage, not a server setting: the selected class is a per-device view
// preference (like the theme in lib/theme.js), not worth a round trip.
const STORAGE_KEY = 'anton.raceBlocks.class'

function readStoredClass() {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY)
    if (CLASSES.some((c) => c.value === v)) return v
  } catch {
    /* storage unavailable (private mode, blocked) — fall through */
  }
  return 'marathon'
}

const MINUS = '−'
const colorFor = (i) => `var(--chart-${(i % 6) + 1})`
// Matches the six --chart-* tokens, so chart colours never repeat (R10.5).
const MAX_CHART_BLOCKS = 6
const hiddenCount = (count) => Math.max(0, count - MAX_CHART_BLOCKS)
// Colour slot of block i (response order, oldest first) among the charted
// blocks, or a negative number when it is an older, uncharted block. Chart and
// table both use this so their colours cannot disagree.
const chartSlot = (i, count) => i - hiddenCount(count)
const offsetLabel = (o) => (o === 0 ? 'race wk' : `wk ${MINUS}${-o}`)
const shortName = (name) => (name.length > 18 ? `${name.slice(0, 17)}…` : name)
// End labels live in a 110px margin: name capped at 12 chars + " 'YY" = 16 max.
const endName = (name) => (name.length > 12 ? `${name.slice(0, 11)}…` : name)
const yearTag = (race) => `'${String(race.race_date).slice(2, 4)}`

// Cells hidden below ~520px so the table fits a 380px phone.
const WIDE = 'hidden min-[520px]:table-cell'

const LABEL_GAP_PX = 12

/**
 * One collision-aware label layer for the line ends (rendered via recharts
 * <Customized>, which receives chart state: `yAxisMap[id].scale` is the km->px
 * scale and `offset` the plot rectangle). Lines often finish at similar km, so
 * per-line labels overlap; instead sort by y and push labels apart top-down.
 * Pixel layout only — no data math.
 */
function EndLabels({ items, yAxisMap, offset }) {
  const scale = yAxisMap && Object.values(yAxisMap)[0]?.scale
  if (!scale || !offset) return null
  const top = offset.top
  const bottom = offset.top + offset.height
  const placed = items
    .filter((it) => it.km != null)
    .map((it) => ({ ...it, y: scale(it.km) }))
    .sort((a, b) => a.y - b.y)
  placed.forEach((it, i) => {
    if (i > 0) it.y = Math.max(it.y, placed[i - 1].y + LABEL_GAP_PX)
  })
  // Clamp to the plot; walk back up so a pushed-down tail keeps its spacing.
  for (let i = placed.length - 1; i >= 0; i--) {
    const max = i === placed.length - 1 ? bottom : placed[i + 1].y - LABEL_GAP_PX
    if (placed[i].y > max) placed[i].y = max
  }
  placed.forEach((it) => { if (it.y < top) it.y = top })
  const x = offset.left + offset.width + 8
  return (
    <g>
      {placed.map((it) => (
        <text key={it.key} x={x} y={it.y} dy={4} fontSize={10.5} fill={it.color} fontFamily="IBM Plex Mono, ui-monospace, monospace">
          {it.text}
        </text>
      ))}
    </g>
  )
}

function takeaway(data, noun) {
  const done = data.blocks.filter((b) => !b.in_progress)
  const dnf = done.filter((b) => b.race.status === 'dnf').length
  const biggest = done.reduce((best, b) => (best == null || b.total_km > best.total_km ? b : best), null)
  const live = data.blocks.filter((b) => b.in_progress)
  let text = `${done.length} ${noun} block${done.length === 1 ? '' : 's'}`
  if (dnf) text += ` (${dnf} DNF)`
  if (biggest) {
    text += ` · biggest: ${biggest.race.name}, ${biggest.total_km.toFixed(0)} km, ${biggest.avg_week_km.toFixed(0)} km/wk avg`
  }
  for (const b of live) text += ` · ${b.race.name} block in progress`
  return text
}

function BlocksChart({ data }) {
  const wide = useMediaQuery('(min-width: 640px)')
  const { blocks, block_weeks } = data
  // Only the newest blocks get lines; the older ones stay in the table.
  const hidden = hiddenCount(blocks.length)
  const charted = useMemo(() => blocks.slice(hidden), [blocks, hidden])

  const rows = useMemo(() => {
    const out = []
    for (let offset = -(block_weeks - 1); offset <= 0; offset++) {
      const row = { offset }
      for (const b of charted) {
        const w = b.weeks.find((x) => x.offset === offset)
        row[`b${b.race.id}`] = w ? w.km : null
        row[`r${b.race.id}`] = w ? w.runs : null
      }
      out.push(row)
    }
    return out
  }, [charted, block_weeks])

  // Label value per block: the race-week km, or the last non-null week for an
  // in-progress block that has no race-week point yet.
  const endItems = charted.map((b, i) => {
    const at0 = b.weeks.find((w) => w.offset === 0)
    const last = at0 ?? (b.in_progress ? [...b.weeks].reverse().find((w) => w.km != null) : null)
    return {
      key: b.race.id,
      km: last ? last.km : null,
      color: colorFor(i),
      text: `${endName(b.race.name)} ${yearTag(b.race)}`,
    }
  })

  const ticks = useMemo(() => rows.filter((r) => r.offset === 0 || r.offset % 4 === 0).map((r) => r.offset), [rows])

  const renderTooltip = (row) => (
    <>
      <div className="font-sans font-semibold text-foreground">
        {row.offset === 0 ? 'Race week' : `Week ${MINUS}${-row.offset}`}
      </div>
      {charted.map((b, i) => {
        const km = row[`b${b.race.id}`]
        if (km == null) return null
        const runs = row[`r${b.race.id}`]
        return (
          <div key={b.race.id} className="mt-0.5 flex items-center gap-2">
            <i aria-hidden="true" className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: colorFor(i) }} />
            <span className="font-sans text-muted-foreground">{shortName(b.race.name)} {yearTag(b.race)}</span>
            <span className="ml-auto pl-3 tabular-nums">
              {km.toFixed(1)} km · {runs} run{runs === 1 ? '' : 's'}
            </span>
          </div>
        )
      })}
    </>
  )

  return (
    <>
      <div className="h-[240px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 12, right: wide ? 110 : 24, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis
              dataKey="offset"
              {...axisProps}
              ticks={ticks}
              interval={0}
              tickFormatter={offsetLabel}
              tickMargin={8}
            />
            <YAxis {...axisProps} width={44} tickCount={4} />
            <Tooltip cursor={lineCursor} content={<ChartTooltip render={renderTooltip} />} />
            {charted.map((b, i) => (
              <Line
                key={b.race.id}
                type="monotone"
                dataKey={`b${b.race.id}`}
                stroke={colorFor(i)}
                strokeWidth={2}
                strokeDasharray={b.in_progress ? '5 4' : undefined}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            ))}
            {wide && <Customized component={<EndLabels items={endItems} />} />}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {!wide && (
        <ChartLegend
          className="mt-3"
          items={charted.map((b, i) => ({
            key: b.race.id,
            kind: b.in_progress ? 'dashed' : 'line',
            color: colorFor(i),
            label: `${shortName(b.race.name)} ${yearTag(b.race)}`,
          }))}
        />
      )}
      {hidden > 0 && (
        <p className="mt-2 text-xs text-faint">
          Chart shows the {MAX_CHART_BLOCKS} newest of {blocks.length} blocks; the table lists all.
        </p>
      )}
    </>
  )
}

function Result({ block }) {
  const { race } = block
  if (race.status === 'dnf') return <span className="font-semibold text-warning">DNF</span>
  if (block.in_progress) return <span className="text-muted-foreground">upcoming</span>
  return <>{race.result_time_s != null ? formatDuration(race.result_time_s) : '—'}</>
}

function BlocksTable({ data }) {
  const { blocks, long_run_km } = data
  // Newest race first. Dot colour comes from chartSlot, so it matches the chart
  // line; older blocks past the chart limit get a hollow placeholder instead.
  const rows = blocks.map((block, i) => ({ block, i })).reverse()
  const th = 'px-2 py-1.5 text-right font-semibold'
  const td = 'px-2 py-2 text-right tabular-nums'

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-2xs uppercase tracking-wide text-faint">
          <tr className="border-b border-border">
            <th className="px-2 py-1.5 text-left font-semibold">Race</th>
            <th className={th}>Result</th>
            <th className={th}>Block km</th>
            <th className={th}>Avg/wk</th>
            <th className={th}>Peak wk</th>
            <th className={cn(th, WIDE)}>Longest</th>
            <th className={cn(th, WIDE)} title={`≥ ${long_run_km} km`}>Long runs</th>
            <th className={cn(th, WIDE)}>Steady pace</th>
            <th className={cn(th, WIDE)}>Steady HR</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ block: b, i }) => {
            const slot = chartSlot(i, blocks.length)
            return (
              <tr key={b.race.id} className="border-b border-border/60 last:border-0">
                <td className="px-2 py-2 text-left">
                  <div className="flex items-start gap-2">
                    {slot >= 0 ? (
                      <i aria-hidden="true" className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: colorFor(slot) }} />
                    ) : (
                      <i aria-hidden="true" className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full border border-border" />
                    )}
                    <div className="min-w-0">
                      {b.race.activity_id != null ? (
                        <Link to={`/activities/${b.race.activity_id}`} className="focus-ring font-semibold text-foreground hover:underline">
                          {b.race.name}
                        </Link>
                      ) : (
                        <span className="font-semibold text-foreground">{b.race.name}</span>
                      )}
                      <div className="text-2xs text-faint">{formatDate(b.race.race_date)}</div>
                    </div>
                  </div>
                </td>
                <td className={td}><Result block={b} /></td>
                <td className={td}>{b.total_km.toFixed(0)}</td>
                <td className={td}>{b.avg_week_km.toFixed(0)}</td>
                <td className={td}>
                  {b.peak_week ? (
                    <>
                      {b.peak_week.km.toFixed(0)} km
                      <div className="text-2xs text-faint">
                        {b.peak_week.offset === 0 ? 'race wk' : `wk ${MINUS}${-b.peak_week.offset}`}
                      </div>
                    </>
                  ) : '—'}
                </td>
                <td className={cn(td, WIDE)}>{b.longest_run ? `${b.longest_run.distance_km.toFixed(1)} km` : '—'}</td>
                <td className={cn(td, WIDE)}>{b.long_runs ?? '—'}</td>
                <td className={cn(td, WIDE)}>
                  {b.median_steady_pace_s_per_km != null ? `${formatDuration(b.median_steady_pace_s_per_km)}/km` : '—'}
                </td>
                <td className={cn(td, WIDE)}>{b.median_steady_hr != null ? `${b.median_steady_hr} bpm` : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Race blocks: the training weeks before each race of one class, overlaid on
 * a shared weeks-before-race axis plus a comparison table. All numbers come
 * from GET /api/races/blocks; this component only formats and picks rows.
 */
export default function RaceBlocksCard() {
  const [raceClass, setRaceClass] = useState(readStoredClass)
  const q = useRaceBlocks(raceClass)
  const noun = CLASSES.find((c) => c.value === raceClass).noun

  const choose = (value) => {
    setRaceClass(value)
    try {
      window.localStorage.setItem(STORAGE_KEY, value)
    } catch {
      /* non-fatal: the choice just won't persist */
    }
  }

  const data = q.data
  const hasBlocks = !!data && data.blocks.length > 0

  return (
    <div className="panel rounded-2xl border border-border bg-card">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
        <h3 className="text-sm font-bold text-foreground">Block comparison</h3>
        <div className="flex rounded-lg border border-border p-0.5">
          {CLASSES.map((c) => (
            <button
              key={c.value}
              type="button"
              onClick={() => choose(c.value)}
              className={
                'focus-ring rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ' +
                (raceClass === c.value ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:text-foreground')
              }
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-4 p-4">
        {q.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-[240px] w-full rounded-[12px]" />
            <Skeleton className="h-24 w-full rounded-[12px]" />
          </div>
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={q.refetch} />
        ) : !hasBlocks ? (
          <EmptyState
            icon={Layers}
            title={`No ${noun} races yet`}
            description="Completed, DNF and planned races of this distance appear here."
          />
        ) : (
          <>
            <p className="text-sm text-muted-foreground">{takeaway(data, noun)}</p>
            <BlocksChart data={data} />
            <BlocksTable data={data} />
            <p className="text-2xs text-faint">
              Heuristic. Each block is the readiness window — the {data.block_weeks} weeks ending in race week, read up to
              the day before the race — so blocks of nearby races overlap. Long runs are runs ≥ {data.long_run_km} km;
              steady pace and HR are medians over steady runs.
              {raceClass === 'half' && ' Half blocks often sit inside marathon builds, so their long-run counts run high.'}
            </p>
          </>
        )}
      </div>
    </div>
  )
}
