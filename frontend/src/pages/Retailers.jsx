import { useMemo, useState } from 'react'
import { Store, ExternalLink, Plus, Pencil, Trash2, Tag } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import RetailerForm from '@/components/RetailerForm'
import PromoManagerDialog from '@/components/PromoManagerDialog'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { ErrorState, EmptyState, RowSkeleton } from '@/components/StatusViews'
import { useToast } from '@/components/ui/toast'
import {
  useRetailers,
  useDeals,
  useCreateRetailer,
  useUpdateRetailer,
  useDeleteRetailer,
} from '@/hooks/useApi'
import { cn, formatRelativeTime } from '@/lib/utils'

// Status is derived from data we actually have — scraping_enabled and
// last_scraped_at — rather than a fabricated health check the backend
// doesn't track. "Stale" means it's enabled but hasn't scraped in >24h.
function retailerStatus(retailer) {
  if (!retailer.scraping_enabled) return { label: 'Disabled', tone: 'muted' }
  if (!retailer.last_scraped_at) return { label: 'Not scraped yet', tone: 'warning' }
  const hours = (Date.now() - new Date(retailer.last_scraped_at).getTime()) / 36e5
  if (hours > 24) return { label: 'Stale', tone: 'warning' }
  return { label: 'Active', tone: 'success' }
}

const STATUS_DOT = {
  success: 'bg-primary shadow-[0_0_0_4px_oklch(0.74_0.17_153_/_0.16)]',
  warning: 'bg-warning shadow-[0_0_0_4px_oklch(0.8_0.15_75_/_0.16)]',
  muted: 'bg-faint shadow-[0_0_0_4px_rgba(106,111,118,0.16)]',
}
const STATUS_PILL = {
  success: 'bg-primary/[0.13] text-accent-foreground',
  warning: 'bg-warning/[0.13] text-warning',
  muted: 'bg-secondary text-muted-foreground',
}

export default function Retailers() {
  const retailers = useRetailers()
  const activeDeals = useDeals({ is_active: true })
  const create = useCreateRetailer()
  const update = useUpdateRetailer()
  const remove = useDeleteRetailer()
  const { toast } = useToast()

  const [formState, setFormState] = useState(null) // null | { retailer?: r }
  const [deleting, setDeleting] = useState(null)
  const [promosFor, setPromosFor] = useState(null)

  // Deals currently active per retailer — an honest proxy for "deals found"
  // (we don't persist a separate scrape-run history to count from).
  const dealsByRetailer = useMemo(() => {
    const map = new Map()
    for (const d of activeDeals.data || []) {
      map.set(d.retailer_id, (map.get(d.retailer_id) || 0) + 1)
    }
    return map
  }, [activeDeals.data])

  const statusCounts = useMemo(() => {
    const counts = { success: 0, warning: 0, muted: 0 }
    for (const r of retailers.data || []) counts[retailerStatus(r).tone]++
    return counts
  }, [retailers.data])

  const toggleScraping = (retailer, enabled) => {
    update.mutate(
      { id: retailer.id, data: { scraping_enabled: enabled } },
      {
        onSuccess: () =>
          toast({
            variant: 'success',
            title: enabled ? 'Scraping enabled' : 'Scraping disabled',
            description: retailer.name,
          }),
        onError: (err) =>
          toast({ variant: 'destructive', title: 'Update failed', description: err.message }),
      }
    )
  }

  const handleSubmit = (payload) => {
    const editing = formState?.retailer
    const mutation = editing ? update : create
    const args = editing ? { id: editing.id, data: payload } : payload
    mutation.mutate(args, {
      onSuccess: () => {
        toast({ variant: 'success', title: editing ? 'Retailer updated' : 'Retailer added' })
        setFormState(null)
      },
      onError: (err) =>
        toast({ variant: 'destructive', title: 'Save failed', description: err.message }),
    })
  }

  const confirmDelete = () => {
    remove.mutate(deleting.id, {
      onSuccess: () => {
        toast({ variant: 'success', title: 'Retailer deleted' })
        setDeleting(null)
      },
      onError: (err) =>
        toast({ variant: 'destructive', title: 'Delete failed', description: err.message }),
    })
  }

  // Keep the open promo dialog's data fresh as the retailers query refetches.
  const promoRetailer = promosFor && (retailers.data || []).find((r) => r.id === promosFor.id)

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="RETAILERS" title="Retailers" count={retailers.data?.length}>
        <Button onClick={() => setFormState({})}>
          <Plus className="h-4 w-4" /> Add retailer
        </Button>
      </PageHeader>

      {!retailers.isLoading && !retailers.isError && retailers.data?.length > 0 && (
        <div className="grid grid-cols-3 gap-3.5">
          <StatusTile count={statusCounts.success} label="Active" tone="success" />
          <StatusTile count={statusCounts.warning} label="Stale / not yet scraped" tone="warning" />
          <StatusTile count={statusCounts.muted} label="Disabled" tone="muted" />
        </div>
      )}

      {retailers.isLoading ? (
        <RowSkeleton count={6} />
      ) : retailers.isError ? (
        <ErrorState error={retailers.error} onRetry={retailers.refetch} />
      ) : retailers.data?.length ? (
        <div className="overflow-hidden rounded-[14px] border border-border bg-card">
          <div className="grid grid-cols-[2fr_1.1fr_1fr_1.2fr_1.6fr] gap-3.5 border-b border-border px-5 py-3 font-mono text-[11px] uppercase tracking-[0.08em] text-faint">
            <span>Retailer</span>
            <span>Status</span>
            <span>Active deals</span>
            <span>Last scraped</span>
            <span className="text-right">Actions</span>
          </div>
          {retailers.data.map((retailer) => {
            const status = retailerStatus(retailer)
            const initials = retailer.name
              .split(' ')
              .map((w) => w[0])
              .slice(0, 2)
              .join('')
              .toUpperCase()
            return (
              <div
                key={retailer.id}
                className="grid grid-cols-[2fr_1.1fr_1fr_1.2fr_1.6fr] items-center gap-3.5 border-b border-[#1A1D22] px-5 py-3.5 last:border-b-0"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-[9px] bg-secondary font-heading text-[15px] font-extrabold text-secondary-foreground">
                    {initials}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-[15px] font-bold text-foreground">
                      {retailer.name}
                    </div>
                    {retailer.base_url && (
                      <a
                        href={retailer.base_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 truncate font-mono text-[11px] text-faint hover:text-muted-foreground"
                      >
                        {retailer.base_url.replace(/^https?:\/\//, '')}
                        <ExternalLink className="h-3 w-3 shrink-0" />
                      </a>
                    )}
                  </div>
                </div>
                <div>
                  <span
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-[6px] px-2.5 py-1',
                      STATUS_PILL[status.tone]
                    )}
                  >
                    <span className={cn('h-1.5 w-1.5 rounded-full', STATUS_DOT[status.tone])} />
                    <span className="text-xs font-bold">{status.label}</span>
                  </span>
                </div>
                <div className="font-heading text-base font-extrabold text-foreground">
                  {dealsByRetailer.get(retailer.id) ?? 0}
                </div>
                <div className="font-mono text-xs text-muted-foreground">
                  {formatRelativeTime(retailer.last_scraped_at)}
                </div>
                <div className="flex items-center justify-end gap-3">
                  <Switch
                    checked={retailer.scraping_enabled}
                    disabled={update.isPending}
                    onCheckedChange={(checked) => toggleScraping(retailer, checked)}
                    aria-label="Scraping enabled"
                  />
                  <button
                    type="button"
                    title="Manage discount codes"
                    onClick={() => setPromosFor(retailer)}
                    className="text-secondary-foreground hover:text-foreground"
                  >
                    <Tag className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    title="Edit"
                    onClick={() => setFormState({ retailer })}
                    className="text-secondary-foreground hover:text-foreground"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    title="Delete"
                    onClick={() => setDeleting(retailer)}
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <EmptyState
          icon={Store}
          title="No retailers yet"
          description="Add a retailer to start tracking prices and discount codes."
          action={
            <Button onClick={() => setFormState({})}>
              <Plus className="h-4 w-4" /> Add retailer
            </Button>
          }
        />
      )}

      {/* Create / edit dialog */}
      <Dialog open={!!formState} onOpenChange={(o) => !o && setFormState(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{formState?.retailer ? 'Edit retailer' : 'Add a retailer'}</DialogTitle>
            <DialogDescription>
              {formState?.retailer
                ? 'Update this retailer’s details.'
                : 'Add a new retailer to track. A matching scraper is required for automated scraping.'}
            </DialogDescription>
          </DialogHeader>
          {formState && (
            <RetailerForm
              initial={formState.retailer}
              submitting={create.isPending || update.isPending}
              onSubmit={handleSubmit}
              onCancel={() => setFormState(null)}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Promo manager */}
      <PromoManagerDialog
        retailer={promoRetailer}
        open={!!promosFor}
        onOpenChange={(o) => !o && setPromosFor(null)}
      />

      {/* Delete confirmation */}
      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Delete retailer?</DialogTitle>
            <DialogDescription>
              {deleting &&
                `This removes "${deleting.name}" along with its price records, deals, and codes. This cannot be undone.`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={remove.isPending}>
              {remove.isPending ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function StatusTile({ count, label, tone }) {
  return (
    <div className="flex items-center gap-3.5 rounded-[13px] border border-border bg-surface p-[17px]">
      <span className={cn('h-2.5 w-2.5 shrink-0 rounded-full', STATUS_DOT[tone])} />
      <div>
        <div className="font-heading text-2xl font-extrabold leading-none text-foreground">
          {count}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">{label}</div>
      </div>
    </div>
  )
}
