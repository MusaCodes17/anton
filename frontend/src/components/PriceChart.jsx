import { useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import {
  SIGNAL, MUTED, axisProps, gridProps, lineCursor, thresholdProps, ChartTooltip, ChartLegend,
} from '@/components/charts/signal'
import { formatCurrency, formatDate } from '@/lib/utils'
import { EmptyState } from '@/components/StatusViews'
import { LineChart as LineChartIcon } from 'lucide-react'

// Distinct colors per retailer line — the --chart-N tokens in index.css (signal
// blue is reserved for actions and the Target marker, so they start at cyan).
const COLORS = [1, 2, 3, 4, 5, 6].map((n) => `var(--chart-${n})`)

/**
 * Line chart of price over time, one line per retailer.
 * `records` is the array returned by GET /api/shoes/{id}/prices.
 */
export default function PriceChart({ records = [], targetPrice, msrp }) {
  const { data, retailers } = useMemo(() => {
    if (!records.length) return { data: [], retailers: [] }

    const retailerSet = new Map() // name -> color index
    const byTime = new Map() // timestamp -> { date, [retailer]: price }

    const sorted = [...records].sort(
      (a, b) => new Date(a.scraped_at) - new Date(b.scraped_at)
    )

    for (const rec of sorted) {
      const name = rec.retailer_name || `Retailer ${rec.retailer_id}`
      if (!retailerSet.has(name)) retailerSet.set(name, retailerSet.size)
      const key = rec.scraped_at
      if (!byTime.has(key)) {
        byTime.set(key, { date: formatDate(rec.scraped_at), ts: key })
      }
      byTime.get(key)[name] = rec.price
    }

    return {
      data: Array.from(byTime.values()),
      retailers: Array.from(retailerSet.keys()),
    }
  }, [records])

  if (!data.length) {
    return (
      <EmptyState
        icon={LineChartIcon}
        title="No price history yet"
        description="Run a scrape to start collecting prices for this shoe."
      />
    )
  }

  // Template chart language (components/charts/signal): hairline grid, mono
  // axes, retailer series in the --chart-N hues, MSRP and Target as labelled
  // dashed markers, and a mono legend with drawn swatches.
  return (
    <div>
      <div className="h-[260px] sm:h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="date" {...axisProps} interval="preserveStartEnd" minTickGap={32} tickMargin={8} />
            <YAxis {...axisProps} tickFormatter={(v) => `$${v}`} width={52} />
            <Tooltip
              cursor={lineCursor}
              content={
                <ChartTooltip
                  render={(d, payload) => (
                    <>
                      <div className="mb-1 font-sans font-semibold text-foreground">{d.date}</div>
                      {payload.map((p) => (
                        <div key={p.dataKey} className="flex items-center justify-between gap-4">
                          <span className="inline-flex items-center gap-1.5">
                            <i className="inline-block h-[2px] w-2.5 rounded-full" style={{ background: p.color }} />
                            {p.dataKey}
                          </span>
                          <span className="text-foreground">{formatCurrency(p.value)}</span>
                        </div>
                      ))}
                    </>
                  )}
                />
              }
            />
            {/* MSRP labels left and Target right, so equal values never overprint. */}
            {msrp != null && (
              <ReferenceLine
                y={msrp}
                {...thresholdProps(`MSRP ${formatCurrency(msrp)}`, { color: MUTED, position: 'insideTopLeft' })}
              />
            )}
            {targetPrice != null && (
              <ReferenceLine y={targetPrice} {...thresholdProps(`target ${formatCurrency(targetPrice)}`, { color: SIGNAL })} />
            )}
            {retailers.map((name, i) => (
              <Line
                key={name}
                // Prices change in steps between scrapes; a smoothed curve would
                // draw dips and peaks that never happened.
                type="stepAfter"
                dataKey={name}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                strokeLinecap="round"
                connectNulls
                dot={false}
                activeDot={{ r: 4, stroke: 'var(--card)', strokeWidth: 2 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <ChartLegend
        className="mt-3"
        items={[
          ...retailers.map((name, i) => ({ kind: 'line', color: COLORS[i % COLORS.length], label: name })),
          ...(msrp != null ? [{ kind: 'threshold', color: MUTED, label: 'MSRP (sale below)' }] : []),
          ...(targetPrice != null ? [{ kind: 'threshold', color: SIGNAL, label: 'Target' }] : []),
        ]}
      />
    </div>
  )
}
