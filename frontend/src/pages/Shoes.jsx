import { useMemo, useState } from 'react'
import {
  Plus,
  Pencil,
  Trash2,
  LineChart as LineChartIcon,
  Footprints,
  Search,
  Download,
  FlaskConical,
} from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import ShoeForm from '@/components/ShoeForm'
import PriceChart from '@/components/PriceChart'
import ScrapabilityTestModal from '@/components/ScrapabilityTestModal'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { ErrorState, EmptyState, CardSkeletonGrid } from '@/components/StatusViews'
import { useToast } from '@/components/ui/toast'
import {
  useShoes,
  useShoesSummary,
  useShoePrices,
  useDeals,
  useCreateShoe,
  useUpdateShoe,
  useDeleteShoe,
} from '@/hooks/useApi'
import { exportApi, shoesApi, scrapeApi } from '@/services/api'
import { cn, formatCurrency } from '@/lib/utils'

export default function Shoes() {
  const [search, setSearch] = useState('')
  const [formState, setFormState] = useState(null) // null | { shoe?: shoe }
  const [deleting, setDeleting] = useState(null) // shoe pending delete
  const [historyShoe, setHistoryShoe] = useState(null)

  const shoes = useShoes()
  const summaries = useShoesSummary()
  const activeDeals = useDeals({ is_active: true })
  const create = useCreateShoe()
  const update = useUpdateShoe()
  const remove = useDeleteShoe()
  const { toast } = useToast()

  // On-demand "Test" button per card — never runs automatically, only when clicked.
  const [testShoe, setTestShoe] = useState(null)
  const [testState, setTestState] = useState(null) // { loading, error, result }

  const runTest = (shoe) => {
    setTestShoe(shoe)
    setTestState({ loading: true, error: null, result: null })
    shoesApi
      .testScrapability(shoe.brand, shoe.model)
      .then((result) => setTestState({ loading: false, error: null, result }))
      .catch((err) => setTestState({ loading: false, error: err.message, result: null }))
  }

  // Per-shoe summary derived from currently active deals: whether it's on
  // sale, the lowest active price, and a representative image.
  const dealSummaryByShoe = useMemo(() => {
    const map = new Map()
    for (const d of activeDeals.data || []) {
      const entry = map.get(d.shoe_id) || { lowest: null, image: null }
      if (entry.lowest == null || d.current_price < entry.lowest) {
        entry.lowest = d.current_price
        entry.image = d.image_url || entry.image
      }
      map.set(d.shoe_id, entry)
    }
    return map
  }, [activeDeals.data])

  // Bulk per-shoe fallback (default price / image / retailer count) from the
  // latest scrape, regardless of deal status — so cards for shoes that
  // aren't currently on sale still show a real price, image, and retailer
  // count instead of blanks.
  const summaryByShoe = useMemo(() => {
    const map = new Map()
    for (const s of summaries.data || []) map.set(s.shoe_id, s)
    return map
  }, [summaries.data])

  const filtered = (shoes.data || []).filter((s) => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return s.brand.toLowerCase().includes(q) || s.model.toLowerCase().includes(q)
  })

  const handleSubmit = (payload, opts = {}) => {
    const editing = formState?.shoe
    const mutation = editing ? update : create
    const args = editing ? { id: editing.id, data: payload } : payload
    mutation.mutate(args, {
      onSuccess: (savedShoe) => {
        toast({ variant: 'success', title: editing ? 'Shoe updated' : 'Shoe added' })
        setFormState(null)
        if (opts.scrapeAfterSave) {
          scrapeApi
            .shoe(savedShoe.id)
            .then((res) =>
              toast({
                variant: 'success',
                title: 'Scrape complete',
                description: `${res.results?.deals_found ?? 0} deal(s) found.`,
              })
            )
            .catch((err) =>
              toast({ variant: 'destructive', title: 'Scrape failed', description: err.message })
            )
        }
      },
      onError: (err) =>
        toast({ variant: 'destructive', title: 'Save failed', description: err.message }),
    })
  }

  const [exporting, setExporting] = useState(false)
  const handleExport = async () => {
    setExporting(true)
    try {
      const source = await exportApi.seedData()
      const blob = new Blob([source], { type: 'text/x-python' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'seed_data.py'
      a.click()
      URL.revokeObjectURL(url)
      toast({ variant: 'success', title: 'Exported seed_data.py' })
    } catch (err) {
      toast({ variant: 'destructive', title: 'Export failed', description: err.message })
    } finally {
      setExporting(false)
    }
  }

  const confirmDelete = () => {
    remove.mutate(deleting.id, {
      onSuccess: () => {
        toast({ variant: 'success', title: 'Shoe deleted' })
        setDeleting(null)
      },
      onError: (err) =>
        toast({ variant: 'destructive', title: 'Delete failed', description: err.message }),
    })
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="SHOES" title="Tracked shoes" count={shoes.data?.length}>
        <Button variant="outline" onClick={handleExport} disabled={exporting}>
          <Download className="h-4 w-4" /> {exporting ? 'Exporting…' : 'Export seed data'}
        </Button>
        <Button onClick={() => setFormState({})}>
          <Plus className="h-4 w-4" /> Add shoe
        </Button>
      </PageHeader>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder="Search by brand or model…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {shoes.isLoading ? (
        <CardSkeletonGrid count={6} />
      ) : shoes.isError ? (
        <ErrorState error={shoes.error} onRetry={shoes.refetch} />
      ) : filtered.length ? (
        <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((shoe) => {
            const dealSummary = dealSummaryByShoe.get(shoe.id)
            const fallback = summaryByShoe.get(shoe.id)
            const onSale = !!dealSummary
            const displayPrice = onSale ? dealSummary.lowest : fallback?.default_price
            const image = dealSummary?.image || fallback?.image_url
            const retailersScraped = fallback?.retailers_scraped
            return (
              <div
                key={shoe.id}
                className="flex flex-col overflow-hidden rounded-[14px] border border-border bg-surface"
              >
                <div className="flex gap-3.5 p-4">
                  <div className="flex h-[74px] w-[74px] shrink-0 items-center justify-center overflow-hidden rounded-[11px] bg-[repeating-linear-gradient(135deg,#202327,#202327_6px,#26292E_6px,#26292E_12px)]">
                    {image ? (
                      <img src={image} alt={shoe.model} className="h-full w-full object-contain" />
                    ) : (
                      <Footprints className="h-6 w-6 text-faint" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[11px] font-bold uppercase tracking-[0.08em] text-accent-foreground">
                      {shoe.brand}
                    </div>
                    <div className="mt-0.5 truncate font-heading text-base font-bold leading-tight text-foreground">
                      {shoe.model}
                    </div>
                    <div
                      className={cn(
                        'mt-2 inline-flex items-center gap-1.5 rounded-[6px] px-2 py-[3px]',
                        onSale ? 'bg-primary/[0.13]' : 'bg-secondary'
                      )}
                    >
                      <span
                        className={cn('h-1.5 w-1.5 rounded-full', onSale ? 'bg-primary' : 'bg-faint')}
                      />
                      <span
                        className={cn(
                          'text-[11px] font-bold',
                          onSale ? 'text-accent-foreground' : 'text-muted-foreground'
                        )}
                      >
                        {onSale ? 'On sale now' : shoe.is_active ? 'No deal yet' : 'Paused'}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex border-t border-border">
                  <div className="flex-1 border-r border-border px-4 py-3">
                    <div className="text-[11px] uppercase tracking-[0.06em] text-faint">
                      {onSale ? 'Lowest active' : 'Current price'}
                    </div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="mt-0.5 font-heading text-lg font-extrabold text-foreground">
                        {displayPrice != null ? formatCurrency(displayPrice) : '—'}
                      </span>
                      {shoe.msrp != null && (
                        <span
                          className="text-xs text-faint line-through"
                          title={`Retail price ${formatCurrency(shoe.msrp)}`}
                        >
                          {formatCurrency(shoe.msrp)}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex-1 px-4 py-3">
                    <div className="text-[11px] uppercase tracking-[0.06em] text-faint">
                      Retailers
                    </div>
                    <div className="mt-0.5 font-heading text-lg font-extrabold text-foreground">
                      {retailersScraped ?? '—'}
                    </div>
                  </div>
                </div>
                <div className="flex border-t border-border text-[13px] font-bold">
                  <button
                    type="button"
                    onClick={() => setHistoryShoe(shoe)}
                    className="flex flex-1 items-center justify-center gap-1.5 border-r border-border py-2.5 text-secondary-foreground hover:bg-secondary"
                  >
                    <LineChartIcon className="h-3.5 w-3.5" /> History
                  </button>
                  <button
                    type="button"
                    onClick={() => runTest(shoe)}
                    className="flex flex-1 items-center justify-center gap-1.5 border-r border-border py-2.5 text-secondary-foreground hover:bg-secondary"
                  >
                    <FlaskConical className="h-3.5 w-3.5" /> Test
                  </button>
                  <button
                    type="button"
                    onClick={() => setFormState({ shoe })}
                    className="flex flex-1 items-center justify-center gap-1.5 border-r border-border py-2.5 text-secondary-foreground hover:bg-secondary"
                  >
                    <Pencil className="h-3.5 w-3.5" /> Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleting(shoe)}
                    className="flex flex-1 items-center justify-center gap-1.5 py-2.5 text-muted-foreground hover:bg-secondary hover:text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> Remove
                  </button>
                </div>
              </div>
            )
          })}

          <button
            type="button"
            onClick={() => setFormState({})}
            className="flex min-h-[200px] flex-col items-center justify-center gap-2.5 rounded-[14px] border-[1.5px] border-dashed border-[#2E3239] text-faint hover:border-primary/40 hover:text-muted-foreground"
          >
            <span className="flex h-[42px] w-[42px] items-center justify-center rounded-[11px] border border-border bg-surface text-xl leading-none text-accent-foreground">
              +
            </span>
            <span className="text-sm font-bold text-secondary-foreground">Add a shoe to track</span>
            <span className="text-xs text-faint">Brand + model, then pick retailers</span>
          </button>
        </div>
      ) : (
        <EmptyState
          icon={Footprints}
          title={search ? 'No matching shoes' : 'No shoes tracked yet'}
          description={search ? 'Try a different search.' : 'Add a shoe to start tracking prices and deals.'}
          action={
            !search && (
              <Button onClick={() => setFormState({})}>
                <Plus className="h-4 w-4" /> Add shoe
              </Button>
            )
          }
        />
      )}

      {/* Create / edit dialog */}
      <Dialog open={!!formState} onOpenChange={(o) => !o && setFormState(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{formState?.shoe ? 'Edit shoe' : 'Add a shoe'}</DialogTitle>
            <DialogDescription>
              {formState?.shoe
                ? 'Update the details for this tracked shoe.'
                : 'Track a new shoe and set the price you want to pay.'}
            </DialogDescription>
          </DialogHeader>
          {formState && (
            <ShoeForm
              initial={formState.shoe}
              submitting={create.isPending || update.isPending}
              onSubmit={handleSubmit}
              onCancel={() => setFormState(null)}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Price history dialog */}
      <PriceHistoryDialog shoe={historyShoe} onOpenChange={(o) => !o && setHistoryShoe(null)} />

      {/* On-demand scrapability test dialog */}
      <ScrapabilityTestModal
        open={!!testShoe}
        onOpenChange={(o) => !o && setTestShoe(null)}
        shoeLabel={testShoe && `${testShoe.brand} ${testShoe.model}`}
        loading={!!testState?.loading}
        error={testState?.error}
        result={testState?.result}
        onRetest={() => testShoe && runTest(testShoe)}
      />

      {/* Delete confirmation */}
      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Delete shoe?</DialogTitle>
            <DialogDescription>
              {deleting &&
                `This removes "${deleting.brand} ${deleting.model}" and its price history. This cannot be undone.`}
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

function PriceHistoryDialog({ shoe, onOpenChange }) {
  const prices = useShoePrices(shoe?.id)
  return (
    <Dialog open={!!shoe} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Price history{shoe ? ` — ${shoe.brand} ${shoe.model}` : ''}</DialogTitle>
          <DialogDescription>
            {shoe &&
              [
                `Target ${formatCurrency(shoe.target_price)}`,
                shoe.msrp != null && `Retail price ${formatCurrency(shoe.msrp)}`,
              ]
                .filter(Boolean)
                .join(' · ')}
          </DialogDescription>
        </DialogHeader>
        {prices.isError ? (
          <ErrorState error={prices.error} onRetry={prices.refetch} />
        ) : prices.isLoading ? (
          <div className="h-[300px] animate-pulse rounded-md bg-muted" />
        ) : (
          <PriceChart records={prices.data} targetPrice={shoe?.target_price} />
        )}
      </DialogContent>
    </Dialog>
  )
}
