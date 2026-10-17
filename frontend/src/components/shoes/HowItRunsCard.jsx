import {
  ComposedChart,
  Area,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import {
  SIGNAL, ALERT, axisProps, gridProps, useFillId, SignalFill, endpointDot, activeDot,
  lineCursor, thresholdProps, ChartTooltip, ChartLegend,
} from '@/components/charts/signal'
import { useShoeInsights } from '@/hooks/useApi'
import { Skeleton } from '@/components/ui/skeleton'
import { formatShoeType } from '@/lib/shoeTypes'


// Formatting only: the server sends pace as int seconds/km; M:SS is presentation.
function fmtPace(s) {
  if (s == null) return '—'
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}/km`
}

function Numbers({ p }) {
  return (
    <>
      {p.median_m_per_beat != null ? `${p.median_m_per_beat.toFixed(3)} m/beat` : '—'}
      {' · '}
      {fmtPace(p.median_pace_s_per_km)}
      {' · '}
      {p.median_avg_hr != null ? `${p.median_avg_hr} bpm` : '—'}
    </>
  )
}

function renderWearTooltip(d) {
  return (
    <>
      <div className="font-sans font-semibold text-foreground">{d.week}</div>
      <div>
        {d.cumulative_km.toFixed(0)} km total · +{d.km.toFixed(1)} km
      </div>
    </>
  )
}

// Cumulative wear in the template's chart language: signal area, mono axes,
// the mileage limit as the dashed alert threshold with its mono label, and the
// latest week as the glowing endpoint (static — wear isn't a live reading).
function WearChart({ wear }) {
  const fillId = useFillId('wear')
  const weeks = wear?.weeks || []
  if (weeks.length < 2) return null
  const limit = wear.mileage_limit
  return (
    <div>
      <div className="h-[140px] sm:h-[180px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={weeks} margin={{ top: 16, right: 4, left: 0, bottom: 0 }}>
            <defs>
              <SignalFill id={fillId} />
            </defs>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="week" {...axisProps} interval="preserveStartEnd" tickMargin={8} />
            <YAxis
              orientation="right"
              {...axisProps}
              tickFormatter={(v) => `${v} km`}
              width={52}
              tickCount={3}
              domain={[0, (max) => (limit != null ? Math.max(max, limit) : max)]}
            />
            <Tooltip cursor={lineCursor} content={<ChartTooltip render={renderWearTooltip} />} />
            {limit != null && <ReferenceLine y={limit} {...thresholdProps(`limit ${limit} km`)} />}
            <Area
              type="monotone"
              dataKey="cumulative_km"
              stroke={SIGNAL}
              strokeWidth={2}
              fill={`url(#${fillId})`}
              dot={endpointDot(weeks.length - 1)}
              activeDot={activeDot}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <ChartLegend
        className="mt-2"
        items={[
          { kind: 'line', label: 'Cumulative km' },
          ...(limit != null ? [{ kind: 'threshold', color: ALERT, label: 'Mileage limit' }] : []),
        ]}
      />
    </div>
  )
}

/**
 * "How it runs" (R5.5): steady-run efficiency for this pair (and its model), the
 * wear curve against the limit, and what retired shoes of this type actually lasted.
 * Every number is server-computed; this component only formats.
 */
export default function HowItRunsCard({ ownedShoeId }) {
  const { data, isLoading, isError, refetch } = useShoeInsights(ownedShoeId)

  return (
    <section className="space-y-3 rounded-[14px] border border-border bg-surface p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="font-mono text-2xs font-medium uppercase tracking-[0.06em] text-faint">How it runs</div>
        {data?.performance?.heuristic && (
          <span className="font-mono text-2xs uppercase tracking-[0.06em] text-faint">Heuristic</span>
        )}
      </div>

      {isLoading && (
        <div className="space-y-2">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-[140px] w-full" />
        </div>
      )}

      {isError && (
        <div className="text-sm text-muted-foreground">
          Couldn&apos;t load insights.{' '}
          <button type="button" onClick={() => refetch()} className="focus-ring rounded text-accent-foreground underline">
            Retry
          </button>
        </div>
      )}

      {data && (() => {
        const { performance: perf, model, wear, type_wear: tw } = data
        const multi = model?.pair_ids?.length > 1
        return (
          <>
            {perf.enough_data ? (
              <div className="space-y-1">
                <div className="font-heading text-base font-bold uppercase tabular-nums text-foreground sm:text-lg tracking-display">
                  <Numbers p={perf} />
                </div>
                <div className="text-xs text-muted-foreground">
                  from {perf.steady_runs} steady run{perf.steady_runs === 1 ? '' : 's'} (of {perf.runs})
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">
                Not enough steady runs yet — {perf.steady_runs} of {perf.min_steady_runs} needed.
              </div>
            )}

            {multi && model.enough_data && (
              <div className="text-xs text-faint tabular-nums">
                All {model.pair_ids.length} pairs of {model.brand} {model.model}: <Numbers p={model} /> ({model.steady_runs} steady runs)
              </div>
            )}

            <div className="text-2xs text-faint">{perf.caveat}</div>

            <WearChart wear={wear} />

            {tw && (
              <div className="space-y-0.5 text-xs text-muted-foreground">
                <div>
                  Your retired {formatShoeType(tw.shoe_type).toLowerCase()} shoes ended at ~{Math.round(tw.median_final_km)} km (n={tw.retired_count})
                </div>
                {tw.suggested_limit_km != null && (
                  <div>
                    Suggested limit: {Math.round(tw.suggested_limit_km)} km (default {Math.round(tw.default_limit_km)})
                  </div>
                )}
              </div>
            )}
          </>
        )
      })()}
    </section>
  )
}
