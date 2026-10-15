import { ExternalLink, Footprints } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import PromoBadge from '@/components/PromoBadge'
import { formatCurrency, formatPercent } from '@/lib/utils'

/**
 * Read-only deal detail for the logged-out public page (R9.4). Deliberately
 * NOT DealDetailModal, which loads authed price history and carries Archive /
 * Bought it / Stop watching. Takes no hooks and makes no requests: everything
 * shown comes from the PublicDeal already in hand.
 */
export default function PublicDealSheet({ deal, open, onOpenChange }) {
  if (!deal) return null
  // Numeric ascending (payload order is arbitrary); unparseable labels keep
  // their original order at the end. Array.sort is stable.
  const sizes = [...(deal.sizes_available || [])].sort((a, b) => {
    const na = parseFloat(a)
    const nb = parseFloat(b)
    if (Number.isNaN(na) || Number.isNaN(nb)) return Number.isNaN(na) - Number.isNaN(nb)
    return na - nb
  })
  const promos = deal.promo_codes || []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {deal.brand} {deal.model}
          </DialogTitle>
          <DialogDescription>
            {[deal.colorway, deal.retailer_name].filter(Boolean).join(' · ')}
          </DialogDescription>
        </DialogHeader>

        <div className="flex aspect-square w-full items-center justify-center overflow-hidden rounded-[12px] bg-photo">
          {deal.image_url ? (
            <img
              src={deal.image_url}
              alt={`${deal.brand} ${deal.model}${deal.colorway ? ` — ${deal.colorway}` : ''}`}
              className="h-full w-full object-contain"
            />
          ) : (
            <Footprints className="h-12 w-12 text-photo-foreground" />
          )}
        </div>

        <div className="space-y-1">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <p className="font-heading text-3xl font-light tracking-display text-foreground">
              {formatCurrency(deal.current_price)}
            </p>
            {deal.msrp != null && (
              <span className="text-sm text-faint line-through">{formatCurrency(deal.msrp)}</span>
            )}
            {deal.in_stock === false ? (
              <Badge variant="outline" className="border-border text-muted-foreground">
                Out of stock
              </Badge>
            ) : (
              <Badge variant="outline" className="rounded-full border-primary/40 text-accent-foreground">
                In stock
              </Badge>
            )}
          </div>
          {deal.msrp != null && (
            <p className="text-sm text-muted-foreground">
              Retail price {formatCurrency(deal.msrp)}
              {deal.savings_amount != null && deal.savings_percent != null && (
                <>
                  {' · '}
                  <span className="font-medium text-accent-foreground">
                    save {formatCurrency(deal.savings_amount)} ({formatPercent(deal.savings_percent)})
                  </span>
                </>
              )}
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Sizes available
          </p>
          {sizes.length ? (
            <div className="flex flex-wrap gap-1.5">
              {sizes.map((s) => (
                <span
                  key={s}
                  className="rounded-md border border-border px-2 py-0.5 font-mono text-xs text-foreground"
                >
                  {s}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Sizes not listed.</p>
          )}
        </div>

        {promos.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Promo codes
            </p>
            {promos.map((p) => (
              <PromoBadge key={p.code} promo={p} />
            ))}
          </div>
        )}

        {deal.product_url && (
          <Button className="w-full" asChild>
            <a href={deal.product_url} target="_blank" rel="noopener noreferrer">
              View at retailer <ExternalLink className="h-4 w-4" />
            </a>
          </Button>
        )}
      </DialogContent>
    </Dialog>
  )
}
