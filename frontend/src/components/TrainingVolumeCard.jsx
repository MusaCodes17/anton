import { useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { Activity } from 'lucide-react'
import { useTrainingSummary } from '@/hooks/useApi'
import { ErrorState, EmptyState } from '@/components/StatusViews'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// "2026-07" → { label: "Jul", year: "2026" }
function parsePeriod(period) {
  const [year, month] = period.split('-')
  return { label: MONTHS[parseInt(month, 10) - 1] ?? period, year }
}

function TrainingTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-[10px] border border-border bg-popover px-3 py-2 text-xs tabular-nums">
      <div className="font-semibold text-foreground">
        {d.label} {d.year}
      </div>
      <div className="text-muted-foreground">
        {d.total_km.toFixed(1)} km · {d.run_count} run{d.run_count === 1 ? '' : 's'}
      </div>
    </div>
  )
}

/**
 * Monthly training volume (km) for the last 12 months, from the imported
 * Strava history. Bars are total distance; the tooltip also shows run count.
 */
export default function TrainingVolumeCard() {
  const { data, isLoading, isError, error, refetch } = useTrainingSummary('monthly')

  const chartData = useMemo(() => {
    if (!data) return []
    // API returns newest-first: take the last 12 months, reverse to chronological.
    return [...data]
      .slice(0, 12)
      .reverse()
      .map((d) => ({ ...d, ...parsePeriod(d.period) }))
  }, [data])

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
        <div className="flex items-center gap-2.5">
          <Activity className="h-4 w-4 text-primary" />
          <span className="font-heading text-md-plus font-bold text-foreground">Training volume</span>
        </div>
        <span className="font-mono text-2xs text-faint">monthly · last 12 mo</span>
      </div>
      <div className="p-4">
        {isLoading ? (
          <div className="h-[220px] animate-pulse rounded-md bg-muted" />
        ) : isError ? (
          <ErrorState error={error} onRetry={refetch} />
        ) : chartData.length ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1E2126" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11, fill: '#6A6F76' }}
                stroke="#1E2126"
                fontFamily="JetBrains Mono, monospace"
              />
              <YAxis
                tick={{ fontSize: 11, fill: '#6A6F76' }}
                stroke="#1E2126"
                fontFamily="JetBrains Mono, monospace"
                tickFormatter={(v) => `${v}`}
                width={40}
              />
              <Tooltip cursor={{ fill: 'oklch(0.74 0.17 153 / 0.08)' }} content={<TrainingTooltip />} />
              <Bar dataKey="total_km" fill="oklch(0.74 0.17 153)" radius={[4, 4, 0, 0]} maxBarSize={44} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState
            icon={Activity}
            title="No training history"
            description="Import your Strava history to see monthly volume here."
          />
        )}
      </div>
    </section>
  )
}
