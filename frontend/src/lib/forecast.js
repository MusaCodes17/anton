import { formatDate } from '@/lib/utils'

// R6.2: presentation only. The numbers (weeks_to_limit, projected_limit_date,
// forecast_status) are computed server-side in rotation.usage_forecast — never
// recompute them here.
export function forecastLabel(f) {
  if (!f) return null
  if (f.forecast_status === 'on_track' && f.weeks_to_limit != null) {
    const wks = f.weeks_to_limit < 1 ? '<1 wk' : `~${Math.round(f.weeks_to_limit)} wk${Math.round(f.weeks_to_limit) === 1 ? '' : 's'}`
    return `${wks} to limit`
  }
  if (f.forecast_status === 'idle') return 'not run lately'
  return null // overdue already shows "Over limit"
}

// Full line for the detail card, e.g. "~5 wks to limit · around Nov 12, 2026".
export function forecastDetail(f) {
  const label = forecastLabel(f)
  if (!label) return null
  return f.projected_limit_date ? `${label} · around ${formatDate(f.projected_limit_date)}` : label
}
