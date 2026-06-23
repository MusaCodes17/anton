import { ExternalLink } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import PriceChart from '@/components/PriceChart'
import PromoBadge from '@/components/PromoBadge'
import { useShoePrices, useDeactivateDeal } from '@/hooks/useApi'
import { useToast } from '@/components/ui/toast'
import {
  formatCurrency,
  formatPercent,
  formatDate,
  bestPromo,
} from '@/lib/utils'

/** Detail view for a deal, including the shoe's price history chart. */
export default function DealDetailModal({ deal, open, onOpenChange }) {
  const shoe = deal?.shoe || {}
  const retailerObj =
    deal?.retailer && typeof deal.retailer === 'object' ? deal.retailer : null
  const retailerName =
    typeof deal?.retailer === 'string' ? deal.retailer : retailerObj?.name
  const promos = retailerObj?.active_promo_codes || []
  const best = bestPromo(deal?.current_price, promos)
  const prices = useShoePrices(open ? deal?.shoe_id : undefined)
  const deactivate = useDeactivateDeal()
  const { toast } = useToast()

  if (!deal) return null

  const handleDeactivate = () => {
    deactivate.mutate(deal.id, {
      onSuccess: () => {
        toast({ variant: 'success', title: 'Deal archived' })
        onOpenChange(false)
      },
      onError: (err) =>
        toast({ variant: 'destructive', title: 'Failed', description: err.message }),
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {shoe.brand} {shoe.model}
          </DialogTitle>
          <DialogDescription>
            {[deal.colorway, retailerName].filter(Boolean).join(' · ')}
          </DialogDescription>
        </DialogHeader>

        {deal.image_url && (
          <img
            src={deal.image_url}
            alt={`${shoe.brand} ${shoe.model}${deal.colorway ? ` — ${deal.colorway}` : ''}`}
            className="mx-auto max-h-56 w-auto rounded-md object-contain"
          />
        )}

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <Metric label="Current" value={formatCurrency(deal.current_price)} />
          {shoe.msrp != null && (
            <Metric label="Retail price" value={formatCurrency(shoe.msrp)} />
          )}
          <Metric label="Target" value={formatCurrency(deal.target_price)} />
          <Metric label="You save" value={formatCurrency(deal.savings_amount)} />
          <Metric
            label="Discount"
            value={
              <Badge variant={deal.savings_percent >= 30 ? 'success' : 'secondary'}>
                -{formatPercent(deal.savings_percent)}
              </Badge>
            }
          />
        </div>

        {deal.sizes_available?.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-sm font-medium">Sizes in stock</p>
            <div className="flex flex-wrap gap-1.5">
              {deal.sizes_available.map((s) => (
                <Badge key={s} variant="outline">
                  {s}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {promos.length > 0 && (
          <div className="space-y-2 rounded-md border border-success/30 bg-success/5 p-3">
            <p className="text-sm font-medium">Discount codes at {retailerName}</p>
            <div className="space-y-2">
              {promos.map((promo) => (
                <PromoBadge key={promo.id} promo={promo} />
              ))}
            </div>
            {best && (
              <p className="text-sm">
                With{' '}
                <span className="font-mono font-semibold">{best.promo.code}</span>:{' '}
                <span className="font-semibold">
                  {formatCurrency(best.finalPrice)}
                </span>{' '}
                <span className="text-muted-foreground">
                  (save {formatCurrency(best.saved)} more at checkout)
                </span>
              </p>
            )}
          </div>
        )}

        <div className="space-y-2">
          <p className="text-sm font-medium">Price history</p>
          {prices.isError ? (
            <p className="text-sm text-destructive">{prices.error.message}</p>
          ) : prices.isLoading ? (
            <div className="h-[300px] animate-pulse rounded-md bg-muted" />
          ) : (
            <PriceChart records={prices.data} targetPrice={deal.target_price} />
          )}
        </div>

        <p className="text-xs text-muted-foreground">
          Detected {formatDate(deal.detected_at, { hour: 'numeric', minute: '2-digit' })}
        </p>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="outline"
            onClick={handleDeactivate}
            disabled={deactivate.isPending}
          >
            {deactivate.isPending ? 'Archiving…' : 'Archive deal'}
          </Button>
          {deal.product_url && (
            <Button asChild>
              <a href={deal.product_url} target="_blank" rel="noreferrer">
                View at retailer <ExternalLink className="h-4 w-4" />
              </a>
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Metric({ label, value }) {
  return (
    <div className="rounded-md border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  )
}
