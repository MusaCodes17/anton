import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ExternalLink, ShoppingBag } from 'lucide-react'
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
import OwnedShoeForm from '@/components/OwnedShoeForm'
import {
  useShoePrices,
  useDeactivateDeal,
  usePurchaseDraft,
  useCreateOwnedShoe,
  useDeleteShoe,
} from '@/hooks/useApi'
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
  const qc = useQueryClient()

  // "Bought it" (R5.3): null -> 'form' (prefilled add-shoe dialog) -> 'stop'
  // (optional "stop watching?" prompt). Nothing is deleted without the explicit click.
  const [boughtStep, setBoughtStep] = useState(null)
  const [boughtName, setBoughtName] = useState('')
  const draft = usePurchaseDraft(deal?.id, { enabled: open && boughtStep === 'form' })
  const createOwned = useCreateOwnedShoe()
  const stopWatching = useDeleteShoe()

  if (!deal) return null

  const watchlistShoeId = deal.shoe_id ?? shoe.id

  const handleBought = (payload) => {
    createOwned.mutate(payload, {
      onSuccess: () => {
        toast({ variant: 'success', title: 'Added to your rotation' })
        setBoughtName([payload.brand, payload.model].join(' '))
        setBoughtStep(watchlistShoeId != null ? 'stop' : null)
      },
      onError: (err) =>
        toast({ variant: 'destructive', title: 'Save failed', description: err.message }),
    })
  }

  const handleStopWatching = () => {
    stopWatching.mutate(watchlistShoeId, {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['deals'] })
        qc.invalidateQueries({ queryKey: ['watchlist'] })
        toast({ variant: 'success', title: 'Stopped watching' })
        setBoughtStep(null)
        onOpenChange(false)
      },
      onError: (err) =>
        toast({ variant: 'destructive', title: 'Failed', description: err.message }),
    })
  }

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
    <>
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
          {deal.target_price != null && (
            <Metric label="Target" value={formatCurrency(deal.target_price)} />
          )}
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
            <PriceChart records={prices.data} targetPrice={deal.target_price} msrp={shoe.msrp} />
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
          <Button variant="outline" onClick={() => setBoughtStep('form')}>
            <ShoppingBag className="h-4 w-4" /> Bought it
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

    {/* Bought it: prefilled add-shoe form */}
    <Dialog open={boughtStep === 'form'} onOpenChange={(o) => !o && setBoughtStep(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add to your rotation</DialogTitle>
          <DialogDescription>
            Prefilled from this deal. Adjust anything before saving.
          </DialogDescription>
        </DialogHeader>
        {draft.isError ? (
          <div className="space-y-3">
            <p className="text-sm text-destructive">
              Couldn't load purchase details{draft.error?.message ? `: ${draft.error.message}` : ''}
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => setBoughtStep(null)}>
                Close
              </Button>
              <Button onClick={() => draft.refetch()}>Retry</Button>
            </DialogFooter>
          </div>
        ) : draft.isLoading || !draft.data ? (
          <div className="h-48 animate-pulse rounded-md bg-muted" />
        ) : (
          <OwnedShoeForm
            prefill={draft.data}
            submitting={createOwned.isPending}
            onSubmit={handleBought}
            onCancel={() => setBoughtStep(null)}
          />
        )}
      </DialogContent>
    </Dialog>

    {/* Bought it: optional follow-up. Only the explicit button deletes. */}
    <Dialog open={boughtStep === 'stop'} onOpenChange={(o) => !o && setBoughtStep(null)}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Stop watching {boughtName}?</DialogTitle>
          <DialogDescription>
            It's in your rotation now. Stopping removes it from your watchlist along with its
            price history and deals.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={handleStopWatching} disabled={stopWatching.isPending}>
            {stopWatching.isPending ? 'Removing…' : 'Stop watching'}
          </Button>
          <Button autoFocus onClick={() => setBoughtStep(null)}>
            Keep watching
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
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
