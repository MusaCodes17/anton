import { useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { formatCurrency, formatDate } from '@/lib/utils'
import { EmptyState } from '@/components/StatusViews'
import { LineChart as LineChartIcon } from 'lucide-react'

// Distinct colors per retailer line (the first, primary green, is reserved
// visually for the "Velocity" accent elsewhere, so retailer lines start at blue).
const COLORS = ['#3B6FE0', '#E0186E', '#C8F032', '#7c3aed', '#0891b2', '#d97706']

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

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1E2126" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: '#6A6F76' }}
          stroke="#1E2126"
          fontFamily="JetBrains Mono, monospace"
        />
        <YAxis
          tick={{ fontSize: 11, fill: '#6A6F76' }}
          stroke="#1E2126"
          fontFamily="JetBrains Mono, monospace"
          tickFormatter={(v) => `$${v}`}
          width={56}
        />
        <Tooltip
          formatter={(value) => formatCurrency(value)}
          contentStyle={{
            borderRadius: 10,
            border: '1px solid var(--border)',
            background: 'var(--popover)',
            fontSize: 12,
            color: 'var(--foreground)',
          }}
          labelStyle={{ color: 'var(--muted-foreground)' }}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: 'var(--muted-foreground)' }} />
        {msrp != null && (
          <Line
            type="monotone"
            dataKey={() => msrp}
            name="MSRP (sale below)"
            stroke="#6A6F76"
            strokeOpacity={0.6}
            strokeDasharray="2 3"
            dot={false}
            isAnimationActive={false}
          />
        )}
        {targetPrice != null && (
          <Line
            type="monotone"
            dataKey={() => targetPrice}
            name="Target"
            stroke="oklch(0.74 0.17 153)"
            strokeOpacity={0.5}
            strokeDasharray="6 4"
            dot={false}
            isAnimationActive={false}
          />
        )}
        {retailers.map((name, i) => (
          <Line
            key={name}
            type="monotone"
            dataKey={name}
            stroke={COLORS[i % COLORS.length]}
            strokeWidth={2}
            connectNulls
            dot={{ r: 3 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
