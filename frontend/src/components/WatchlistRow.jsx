import { Link } from 'react-router-dom'
import { Footprints, Pencil, ExternalLink } from 'lucide-react'
import ShoeTypeBadge from '@/components/ShoeTypeBadge'
import { formatCurrency, formatRelativeTime } from '@/lib/utils'

// A small labelled figure — "MSRP $220". Muted dash when we have no value.
function Stat({ label, children }) {
  return (
    <div className="min-w-[64px]">
      <div className="text-2xs font-bold uppercase tracking-[0.08em] text-faint">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-foreground tabular-nums">{children ?? '—'}</div>
    </div>
  )
}

/**
 * One compact row on the Deals watchlist for a tracked shoe that is NOT on
 * sale: identity, MSRP/target, best-ever price (and when), and the last-seen
 * price at each retailer. The target price links to /settings/tracking to
 * edit it — the watchlist is a read surface, tracking config lives there.
 */
export default function WatchlistRow({ item }) {
  const { brand, model, shoe_type, msrp, target_price, image_url, best_ever_price, best_ever_at, last_seen } = item

  return (
    <div className="flex flex-col gap-4 rounded-[14px] border border-border bg-surface p-4 sm:flex-row sm:items-center">
      {/* Identity */}
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-[10px] border border-border bg-secondary">
          {image_url ? (
            <img src={image_url} alt="" className="h-full w-full object-cover" />
          ) : (
            <Footprints className="h-5 w-5 text-faint" />
          )}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-bold text-foreground">{model}</div>
          <div className="mt-0.5 flex items-center gap-2">
            <span className="truncate text-xs text-muted-foreground">{brand}</span>
            {shoe_type && <ShoeTypeBadge type={shoe_type} />}
          </div>
        </div>
      </div>

      {/* Figures */}
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <Stat label="MSRP">{msrp != null ? formatCurrency(msrp) : null}</Stat>
        <Stat label="Target">
          <Link
            to="/settings/tracking"
            className="focus-ring inline-flex items-center gap-1 rounded text-primary hover:underline"
            title="Edit target price"
          >
            {formatCurrency(target_price)}
            <Pencil className="h-3 w-3" />
          </Link>
        </Stat>
        <Stat label="Best ever">
          {best_ever_price != null ? (
            <span title={best_ever_at ? `Seen ${formatRelativeTime(best_ever_at)}` : undefined}>
              {formatCurrency(best_ever_price)}
              {best_ever_at && (
                <span className="ml-1 text-2xs font-normal text-faint">
                  {formatRelativeTime(best_ever_at)}
                </span>
              )}
            </span>
          ) : null}
        </Stat>
      </div>

      {/* Last-seen per retailer */}
      <div className="flex min-w-0 flex-col gap-1.5 sm:w-[220px]">
        <div className="text-2xs font-bold uppercase tracking-[0.08em] text-faint">Last seen</div>
        {last_seen && last_seen.length ? (
          <div className="flex flex-wrap gap-1.5">
            {last_seen.map((ls) => (
              <a
                key={ls.retailer_id}
                href={ls.product_url}
                target="_blank"
                rel="noreferrer"
                className={
                  'focus-ring inline-flex items-center gap-1 rounded-full border border-border bg-secondary px-2 py-0.5 text-2xs font-medium hover:border-primary/40 ' +
                  (ls.in_stock ? 'text-secondary-foreground' : 'text-faint line-through')
                }
                title={`${ls.retailer_name} — ${ls.in_stock ? 'in stock' : 'out of stock'}`}
              >
                {ls.retailer_name} {formatCurrency(ls.price)}
                <ExternalLink className="h-2.5 w-2.5" />
              </a>
            ))}
          </div>
        ) : (
          <span className="text-xs text-faint">No price seen yet</span>
        )}
      </div>
    </div>
  )
}
