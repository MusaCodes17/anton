import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tag, SlidersHorizontal, ChevronDown, Eye } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import ShoeProductCard from '@/components/ShoeProductCard'
import DealDetailModal from '@/components/DealDetailModal'
import ScrapeButton from '@/components/ScrapeButton'
import WatchlistRow from '@/components/WatchlistRow'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ErrorState, EmptyState, CardSkeletonGrid } from '@/components/StatusViews'
import { useDeals, useShoes, useRetailers, useWatchlist } from '@/hooks/useApi'
import { formatShoeType } from '@/lib/shoeTypes'

const SORTS = {
  savings_desc: (a, b) => b.savings_percent - a.savings_percent,
  price_asc: (a, b) => a.current_price - b.current_price,
  price_desc: (a, b) => b.current_price - a.current_price,
  recent: (a, b) => new Date(b.detected_at) - new Date(a.detected_at),
}

const ALL = '__all__'

export default function Deals() {
  const [brand, setBrand] = useState(ALL)
  const [retailerId, setRetailerId] = useState(ALL)
  const [shoeType, setShoeType] = useState(ALL)
  const [minSavings, setMinSavings] = useState('')
  const [size, setSize] = useState(ALL)
  const [sort, setSort] = useState('savings_desc')
  const [selected, setSelected] = useState(null)
  const [watchingOpen, setWatchingOpen] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()
  const deepLinkId = searchParams.get('deal')

  // Server-side filters the API supports directly.
  const params = useMemo(() => {
    const p = { is_active: true }
    if (brand !== ALL) p.brand = brand
    const min = parseFloat(minSavings)
    if (!Number.isNaN(min) && min > 0) p.min_savings_percent = min
    return p
  }, [brand, minSavings])

  const deals = useDeals(params)
  const shoes = useShoes()
  const retailers = useRetailers()
  const watchlist = useWatchlist()

  // Deep link from the Dashboard: /deals?deal=<id> opens that deal's modal
  // once the deals are loaded. The param is cleared when the modal closes.
  useEffect(() => {
    if (!deepLinkId || !deals.data) return
    const match = deals.data.find((d) => String(d.id) === deepLinkId)
    if (match) setSelected(match)
  }, [deepLinkId, deals.data])

  const closeModal = () => {
    setSelected(null)
    if (deepLinkId) {
      searchParams.delete('deal')
      setSearchParams(searchParams, { replace: true })
    }
  }

  // Distinct brands for the filter dropdown, derived from tracked shoes.
  const brands = useMemo(() => {
    const set = new Set((shoes.data || []).map((s) => s.brand))
    return Array.from(set).sort()
  }, [shoes.data])

  // Distinct shoe types for the filter dropdown, derived from tracked shoes.
  const shoeTypes = useMemo(() => {
    const set = new Set()
    for (const s of shoes.data || []) {
      if (s.shoe_type) set.add(s.shoe_type)
    }
    return Array.from(set).sort()
  }, [shoes.data])

  // Distinct sizes for the filter dropdown, derived from the deals already
  // fetched (sizes_available is cached at scrape time — picking a size never
  // triggers another scrape). Deals scraped before size tracking was added
  // have no sizes_available and are simply excluded once a size is chosen.
  const sizes = useMemo(() => {
    const set = new Set()
    for (const d of deals.data || []) {
      for (const s of d.sizes_available || []) set.add(s)
    }
    return Array.from(set).sort((a, b) => parseFloat(a) - parseFloat(b))
  }, [deals.data])

  // Retailer/size/shoe-type filtering + sorting happen client-side.
  const visible = useMemo(() => {
    let list = deals.data || []
    if (retailerId !== ALL) {
      list = list.filter((d) => String(d.retailer_id) === retailerId)
    }
    if (shoeType !== ALL) {
      list = list.filter((d) => d.shoe?.shoe_type === shoeType)
    }
    if (size !== ALL) {
      list = list.filter((d) => (d.sizes_available || []).includes(size))
    }
    return [...list].sort(SORTS[sort])
  }, [deals.data, retailerId, shoeType, size, sort])

  // Consolidate colorways/retailers: one card per tracked shoe. Groups inherit
  // the sorted order of `visible`, so each group's first (best) deal also orders
  // the groups by the chosen sort.
  const groups = useMemo(() => {
    const map = new Map()
    for (const d of visible) {
      if (!map.has(d.shoe_id)) {
        map.set(d.shoe_id, { shoeId: d.shoe_id, shoe: d.shoe || {}, deals: [] })
      }
      map.get(d.shoe_id).deals.push(d)
    }
    return Array.from(map.values())
  }, [visible])

  // "Watching" = tracked shoes with no active deal. The brand/retailer/type
  // filters apply here too (savings/size/sort are deal-only and don't).
  const watching = useMemo(() => {
    let list = (watchlist.data || []).filter((it) => !it.on_sale)
    if (brand !== ALL) list = list.filter((it) => it.brand === brand)
    if (shoeType !== ALL) list = list.filter((it) => it.shoe_type === shoeType)
    if (retailerId !== ALL) {
      list = list.filter((it) =>
        (it.last_seen || []).some((ls) => String(ls.retailer_id) === retailerId)
      )
    }
    return list
  }, [watchlist.data, brand, shoeType, retailerId])

  const resetFilters = () => {
    setBrand(ALL)
    setRetailerId(ALL)
    setShoeType(ALL)
    setMinSavings('')
    setSize(ALL)
    setSort('savings_desc')
  }

  const hasFilters =
    brand !== ALL ||
    retailerId !== ALL ||
    shoeType !== ALL ||
    minSavings !== '' ||
    size !== ALL ||
    sort !== 'savings_desc'

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="DEALS" title="Deals" count={groups.length}>
        <ScrapeButton variant="outline" />
      </PageHeader>

      <Card>
        <CardContent className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <div className="space-y-1.5">
            <Label>Brand</Label>
            <Select value={brand} onValueChange={setBrand}>
              <SelectTrigger>
                <SelectValue placeholder="All brands" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All brands</SelectItem>
                {brands.map((b) => (
                  <SelectItem key={b} value={b}>
                    {b}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>Retailer</Label>
            <Select value={retailerId} onValueChange={setRetailerId}>
              <SelectTrigger>
                <SelectValue placeholder="All retailers" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All retailers</SelectItem>
                {(retailers.data || []).map((r) => (
                  <SelectItem key={r.id} value={String(r.id)}>
                    {r.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>Shoe type</Label>
            <Select value={shoeType} onValueChange={setShoeType}>
              <SelectTrigger>
                <SelectValue placeholder="All types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All types</SelectItem>
                {shoeTypes.map((t) => (
                  <SelectItem key={t} value={t}>
                    {formatShoeType(t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>Size</Label>
            <Select value={size} onValueChange={setSize}>
              <SelectTrigger>
                <SelectValue placeholder="All sizes" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All sizes</SelectItem>
                {sizes.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>Min. savings %</Label>
            <Input
              type="number"
              min="0"
              max="100"
              placeholder="e.g. 20"
              value={minSavings}
              onChange={(e) => setMinSavings(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label>Sort by</Label>
            <Select value={sort} onValueChange={setSort}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="savings_desc">Highest savings</SelectItem>
                <SelectItem value="price_asc">Lowest price</SelectItem>
                <SelectItem value="price_desc">Highest price</SelectItem>
                <SelectItem value="recent">Most recent</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {hasFilters && (
            <div className="flex items-end xl:col-span-6">
              <Button variant="ghost" size="sm" onClick={resetFilters}>
                <SlidersHorizontal className="h-4 w-4" /> Clear filters
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── On sale now ─────────────────────────────────────────── */}
      <section className="space-y-4">
        <div className="flex items-baseline gap-2">
          <h2 className="font-heading text-lg font-extrabold tracking-tight text-foreground">
            On sale now
          </h2>
          {!deals.isLoading && !deals.isError && (
            <span className="text-sm text-faint">
              {groups.length} shoe{groups.length === 1 ? '' : 's'} · {visible.length} deal
              {visible.length === 1 ? '' : 's'}
            </span>
          )}
        </div>

        {deals.isLoading ? (
          <CardSkeletonGrid count={6} />
        ) : deals.isError ? (
          <ErrorState error={deals.error} onRetry={deals.refetch} />
        ) : groups.length ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {groups.map((group) => (
              <ShoeProductCard
                key={group.shoeId}
                group={group}
                onViewDetails={(deal) => setSelected(deal)}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Tag}
            title={hasFilters ? 'No deals match your filters' : 'No active deals'}
            description={
              hasFilters
                ? 'Try widening or clearing the filters — the shoes you track are below.'
                : 'Nothing on sale right now. Everything you track is in Watching below.'
            }
            action={
              hasFilters ? (
                <Button variant="outline" size="sm" onClick={resetFilters}>
                  Clear filters
                </Button>
              ) : (
                <ScrapeButton />
              )
            }
          />
        )}
      </section>

      {/* ── Watching (not on sale) ──────────────────────────────── */}
      {(watching.length > 0 || watchlist.isLoading) && (
        <section className="space-y-4 border-t border-border pt-6">
          <button
            type="button"
            onClick={() => setWatchingOpen((o) => !o)}
            className="focus-ring flex items-center gap-2 rounded text-left"
            aria-expanded={watchingOpen}
          >
            <ChevronDown
              className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 ${
                watchingOpen ? '' : '-rotate-90'
              }`}
            />
            <Eye className="h-4 w-4 shrink-0 text-accent-foreground" />
            <span className="font-heading text-lg font-extrabold tracking-tight text-foreground">
              Watching
            </span>
            <span className="text-sm text-faint">
              · {watching.length} shoe{watching.length === 1 ? '' : 's'} not on sale
            </span>
          </button>

          {watchingOpen &&
            (watchlist.isError ? (
              <ErrorState error={watchlist.error} onRetry={watchlist.refetch} />
            ) : (
              <div className="space-y-3">
                {watching.map((item) => (
                  <WatchlistRow key={item.shoe_id} item={item} />
                ))}
              </div>
            ))}
        </section>
      )}

      <DealDetailModal
        deal={selected}
        open={!!selected}
        onOpenChange={(o) => !o && closeModal()}
      />
    </div>
  )
}
