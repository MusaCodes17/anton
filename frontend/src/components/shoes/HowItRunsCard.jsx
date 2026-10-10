import {
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import { useShoeInsights } from '@/hooks/useApi'
import { Skeleton } from '@/components/ui/skeleton'
import { formatShoeType } from '@/lib/shoeTypes'

const GREEN = 'var(--primary)'

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

function WearTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-[10px] border border-border bg-popover px-3 py-2 text-xs tabular-nums">
      <div className="font-semibold text-foreground">{d.week}</div>
      <div className="text-muted-foreground">
        {d.cumulative_km.toFixed(0)} km total · +{d.km.toFixed(1)} km
      </div>
    </div>
  )
}

function WearChart({ wear }) {
  const weeks = wear?.weeks || []
  if (weeks.length < 2) return null
  const limit = wear.mileage_limit
  return (
    <div className="h-[140px] sm:h-[180px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={weeks} margin={{ top: 12, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="wearFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={GREEN} stopOpacity={0.26} />
              <stop offset="100%" stopColor={GREEN} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="week"
            tick={{ fontSize: 11, fill: 'var(--faint)' }}
            stroke="var(--chart-grid)"
            interval="preserveStartEnd"
            tickMargin={8}
          />
          <YAxis
            orientation="right"
            tick={{ fontSize: 11, fill: 'var(--faint)' }}
            stroke="var(--chart-grid)"
            tickFormatter={(v) => `${v} km`}
            width={52}
            tickCount={3}
            domain={[0, (max) => (limit != null ? Math.max(max, limit) : max)]}
          />
          <Tooltip content={<WearTooltip />} />
          {limit != null && (
            <ReferenceLine
              y={limit}
              stroke="var(--warning)"
              strokeDasharray="4 3"
              label={{ value: `limit ${limit} km`, position: 'insideTopLeft', fontSize: 11, fill: 'var(--faint)' }}
            />
          )}
          <Area
            type="monotone"
            dataKey="cumulative_km"
            stroke={GREEN}
            strokeWidth={2}
            fill="url(#wearFill)"
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
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
        <div className="text-2xs font-bold uppercase tracking-[0.08em] text-faint">How it runs</div>
        {data?.performance?.heuristic && (
          <span className="text-2xs uppercase tracking-[0.08em] text-faint">Heuristic</span>
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
                <div className="font-heading text-base font-bold tabular-nums text-foreground sm:text-lg">
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
