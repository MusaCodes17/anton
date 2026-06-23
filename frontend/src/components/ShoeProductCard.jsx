import { useState } from 'react'
import { ExternalLink, Store, Footprints } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import PromoBadge from '@/components/PromoBadge'
import ColorwaySelector from '@/components/ColorwaySelector'
import { formatCurrency, formatPercent, bestPromo } from '@/lib/utils'

/**
 * One compact card per tracked shoe model. Consolidates every active deal for
 * the model (across colorways and retailers) into a single card with a
 * primary image and a colorway/retailer selector. Selecting a colorway
 * updates the image, price, retailer, and buy link.
 *
 * Props: group = { shoeId, shoe: { brand, model }, deals: DealResponse[] }
 *        onViewDetails(deal) — optional, opens the detail modal.
 */
export default function ShoeProductCard({ group, onViewDetails }) {
  const { shoe, deals } = group
  // Deals arrive pre-sorted (best per the page's sort first), so default to the first.
  const [selectedId, setSelectedId] = useState(deals[0]?.id)
  const selected = deals.find((d) => d.id === selectedId) || deals[0]

  const retailerObj =
    selected.retailer && typeof selected.retailer === 'object' ? selected.retailer : null
  const retailerName =
    typeof selected.retailer === 'string' ? selected.retailer : retailerObj?.name
  const savings = selected.savings_percent
  const promo = bestPromo(selected.current_price, retailerObj?.active_promo_codes)

  return (
    <div className="flex flex-col overflow-hidden rounded-[14px] border border-border bg-card">
      {/* Primary image */}
      <button
        type="button"
        onClick={() => onViewDetails?.(selected)}
        className="group relative block aspect-square w-full overflow-hidden bg-[#F4F4F2]"
        title="View details"
      >
        {selected.image_url ? (
          <img
            src={selected.image_url}
            alt={`${shoe.brand} ${shoe.model}${selected.colorway ? ` — ${selected.colorway}` : ''}`}
            className="h-full w-full object-contain transition-transform group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <Footprints className="h-12 w-12 text-[#B8B8AE]" />
          </div>
        )}
        {savings != null && (
          <Badge className="absolute right-2 top-2 rounded-[7px] bg-primary px-[9px] py-[5px] font-heading text-[13px] font-extrabold text-primary-foreground">
            {formatPercent(savings)} OFF
          </Badge>
        )}
      </button>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-[0.1em] text-accent-foreground">
            {shoe.brand}
          </p>
          <h3 className="truncate font-heading text-base font-extrabold leading-tight text-foreground">
            {shoe.model}
          </h3>
          {selected.colorway && (
            <p className="truncate text-xs text-muted-foreground">{selected.colorway}</p>
          )}
        </div>

        <div className="flex items-end justify-between">
          <div>
            <div className="flex items-baseline gap-2">
              <p className="font-heading text-2xl font-extrabold text-foreground">
                {formatCurrency(selected.current_price)}
              </p>
              {shoe.msrp != null && (
                <span
                  className="text-sm text-faint line-through"
                  title={`Retail price ${formatCurrency(shoe.msrp)}`}
                >
                  {formatCurrency(shoe.msrp)}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {[
                shoe.msrp != null && `Retail price ${formatCurrency(shoe.msrp)}`,
                selected.target_price != null && `Target ${formatCurrency(selected.target_price)}`,
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          </div>
          {selected.in_stock === false ? (
            <Badge variant="outline" className="border-border text-muted-foreground">
              Out of stock
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="rounded-full border-primary/40 text-accent-foreground"
            >
              In stock
            </Badge>
          )}
        </div>

        {promo && (
          <div className="space-y-1.5 rounded-[10px] border border-dashed border-primary/40 bg-primary/[0.07] p-2.5">
            <PromoBadge promo={{ ...promo.promo, description: null }} compact />
            <p className="text-xs text-muted-foreground">
              {formatCurrency(promo.finalPrice)} after code
              <span className="font-bold text-accent-foreground">
                {' '}
                (save {formatCurrency(promo.saved)} more)
              </span>
            </p>
          </div>
        )}

        {/* Colorway / retailer options */}
        <ColorwaySelector options={deals} selectedId={selected.id} onSelect={setSelectedId} />

        <div className="mt-auto flex items-center gap-1 border-t border-border pt-3 text-xs text-muted-foreground">
          <Store className="h-3.5 w-3.5" />
          {retailerName || 'Unknown retailer'}
          {deals.length > 1 && <span className="ml-auto">{deals.length} options</span>}
        </div>

        {selected.product_url && (
          <Button variant="outline" size="sm" className="w-full" asChild>
            <a href={selected.product_url} target="_blank" rel="noreferrer">
              View at retailer <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </Button>
        )}
      </div>
    </div>
  )
}
