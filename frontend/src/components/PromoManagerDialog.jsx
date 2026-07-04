import { useState } from 'react'
import { RefreshCw, Trash2, Plus, Tag } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import PromoBadge from '@/components/PromoBadge'
import { EmptyState } from '@/components/StatusViews'
import { useToast } from '@/components/ui/toast'
import {
  useAddPromo,
  useDeletePromo,
  useDetectPromos,
} from '@/hooks/useApi'
import { cn } from '@/lib/utils'

/**
 * Manage a retailer's discount codes: auto-detect from the site, add manually,
 * and remove. Reads the codes from the retailer object (active_promo_codes).
 */
export default function PromoManagerDialog({ retailer, open, onOpenChange }) {
  const detect = useDetectPromos()
  const addPromo = useAddPromo()
  const deletePromo = useDeletePromo()
  const { toast } = useToast()

  const [code, setCode] = useState('')
  const [description, setDescription] = useState('')
  const [percent, setPercent] = useState('')

  if (!retailer) return null
  const promos = retailer.active_promo_codes || []

  const handleDetect = () => {
    detect.mutate(retailer.id, {
      onSuccess: (data) => {
        const r = data?.results || {}
        toast({
          variant: 'success',
          title: 'Detection complete',
          description: `Found ${r.found ?? 0} code(s), ${r.new ?? 0} new.`,
        })
      },
      onError: (err) =>
        toast({ variant: 'destructive', title: 'Detection failed', description: err.message }),
    })
  }

  const handleAdd = (e) => {
    e.preventDefault()
    if (!code.trim()) return
    addPromo.mutate(
      {
        retailerId: retailer.id,
        data: {
          code: code.trim(),
          description: description.trim() || null,
          discount_percent: percent ? parseFloat(percent) : null,
        },
      },
      {
        onSuccess: () => {
          toast({ variant: 'success', title: 'Code added' })
          setCode('')
          setDescription('')
          setPercent('')
        },
        onError: (err) =>
          toast({ variant: 'destructive', title: 'Failed', description: err.message }),
      }
    )
  }

  const handleDelete = (promo) => {
    deletePromo.mutate(promo.id, {
      onSuccess: () => toast({ variant: 'success', title: 'Code removed' }),
      onError: (err) =>
        toast({ variant: 'destructive', title: 'Failed', description: err.message }),
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Discount codes — {retailer.name}</DialogTitle>
          <DialogDescription>
            Auto-detect codes from the retailer's site or add them manually.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">
            {promos.length} active code{promos.length === 1 ? '' : 's'}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={handleDetect}
            disabled={detect.isPending}
          >
            <RefreshCw className={cn('h-4 w-4', detect.isPending && 'animate-spin')} />
            {detect.isPending ? 'Scanning…' : 'Detect from site'}
          </Button>
        </div>

        {promos.length ? (
          <ul className="space-y-2">
            {promos.map((promo) => (
              <li
                key={promo.id}
                className="flex items-start justify-between gap-3 rounded-md border p-3"
              >
                <div className="min-w-0 space-y-1">
                  <PromoBadge promo={promo} compact />
                  {promo.description && (
                    <p className="text-xs text-muted-foreground">
                      {promo.description}
                    </p>
                  )}
                  <p className="text-2xs text-muted-foreground">
                    {promo.discount_percent ? `${promo.discount_percent}% off · ` : ''}
                    {promo.source === 'manual' ? 'added manually' : 'auto-detected'}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-destructive hover:text-destructive"
                  onClick={() => handleDelete(promo)}
                  disabled={deletePromo.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={Tag}
            title="No active codes"
            description="Detect from the site or add one below."
          />
        )}

        <form onSubmit={handleAdd} className="space-y-3 border-t pt-4">
          <p className="text-sm font-medium">Add manually</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Code</Label>
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="20FOR200"
                className="font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Discount %</Label>
              <Input
                type="number"
                min="0"
                max="100"
                value={percent}
                onChange={(e) => setPercent(e.target.value)}
                placeholder="20"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Description</Label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Extra 20% off orders over $200"
            />
          </div>
          <Button type="submit" disabled={addPromo.isPending || !code.trim()}>
            <Plus className="h-4 w-4" />
            {addPromo.isPending ? 'Adding…' : 'Add code'}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
