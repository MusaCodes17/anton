import { useMemo, useState } from 'react'
import { Tag, SlidersHorizontal } from 'lucide-react'
import PublicLayout from '@/components/layout/PublicLayout'
import PageHeader from '@/components/PageHeader'
import ShoeProductCard from '@/components/ShoeProductCard'
import PublicDealSheet from '@/components/PublicDealSheet'
import FilterDisclosure from '@/components/FilterDisclosure'
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
// R9.4: the ONLY data hook this tree may use. Anything else calls an authed
// endpoint, burning the visitor's auth-failure bucket and firing
// UNAUTHENTICATED_EVENT (which would bounce them to the login view).
import { usePublicDeals } from '@/hooks/useApi'
import { formatShoeType } from '@/lib/shoeTypes'
import { formatRelativeTime } from '@/lib/utils'

// Duplicated from Deals.jsx on purpose (that page stays untouched for R9.4).
const SORTS = {
  savings_desc: (a, b) => b.savings_percent - a.savings_percent,
  price_asc: (a, b) => a.current_price - b.current_price,
  price_desc: (a, b) => b.current_price - a.current_price,
  recent: (a, b) => new Date(b.detected_at) - new Date(a.detected_at),
}

const ALL = '__all__'

// ShoeProductCard / ColorwaySelector expect the authed DealResponse shape
// (nested shoe + retailer objects); adapt a flat PublicDeal to it. msrp is also
// copied onto `shoe` because the card reads the retail price from there.
function adapt(d) {
  return {
    ...d,
    shoe: { brand: d.brand, model: d.model, shoe_type: d.shoe_type, msrp: d.msrp },
    retailer: { name: d.retailer_name, active_promo_codes: d.promo_codes || [] },
  }
}

/**
 * Logged-out "Musa's picks" page (R9.4). Uses PublicLayout (reduced shell): no app nav, chat
 * drawer, scrape button or Watching section. All filter options are derived
 * from the public payload; filtering and sorting are client-side.
 */
export default function PublicDeals() {
  const [size, setSize] = useState(ALL)
  const [brand, setBrand] = useState(ALL)
  const [retailerId, setRetailerId] = useState(ALL)
  const [shoeType, setShoeType] = useState(ALL)
  const [minSavings, setMinSavings] = useState('')
  const [sort, setSort] = useState('savings_desc')
  const [selected, setSelected] = useState(null)
  // Mobile: the whole filter deck (Size included) collapses behind "Filters".
  const [filtersOpen, setFiltersOpen] = useState(false)

  const query = usePublicDeals()
  const all = useMemo(() => (query.data?.deals || []).map(adapt), [query.data])
  const checkedAt = query.data?.checked_at

  const brands = useMemo(() => Array.from(new Set(all.map((d) => d.brand))).sort(), [all])
  const types = useMemo(
    () => Array.from(new Set(all.map((d) => d.shoe_type).filter(Boolean))).sort(),
    [all]
  )
  const retailers = useMemo(() => {
    const m = new Map()
    for (const d of all) m.set(d.retailer_id, d.retailer_name)
    return Array.from(m, ([id, name]) => ({ id, name })).sort((a, b) =>
      String(a.name).localeCompare(String(b.name))
    )
  }, [all])
  const sizes = useMemo(() => {
    const set = new Set()
    for (const d of all) for (const s of d.sizes_available || []) set.add(s)
    return Array.from(set).sort((a, b) => parseFloat(a) - parseFloat(b))
  }, [all])

  const visible = useMemo(() => {
    let list = all
    if (brand !== ALL) list = list.filter((d) => d.brand === brand)
    if (retailerId !== ALL) list = list.filter((d) => String(d.retailer_id) === retailerId)
    if (shoeType !== ALL) list = list.filter((d) => d.shoe_type === shoeType)
    if (size !== ALL) list = list.filter((d) => (d.sizes_available || []).includes(size))
    const min = parseFloat(minSavings)
    if (!Number.isNaN(min) && min > 0) list = list.filter((d) => d.savings_percent >= min)
    return [...list].sort(SORTS[sort])
  }, [all, brand, retailerId, shoeType, size, minSavings, sort])

  // One card per shoe, in the sorted order of `visible` (as on Deals.jsx).
  const groups = useMemo(() => {
    const map = new Map()
    for (const d of visible) {
      if (!map.has(d.shoe_id)) map.set(d.shoe_id, { shoeId: d.shoe_id, shoe: d.shoe, deals: [] })
      map.get(d.shoe_id).deals.push(d)
    }
    return Array.from(map.values())
  }, [visible])

  const resetFilters = () => {
    setSize(ALL)
    setBrand(ALL)
    setRetailerId(ALL)
    setShoeType(ALL)
    setMinSavings('')
    setSort('savings_desc')
  }

  // Every filter (Size included) lives behind the mobile disclosure, so the badge counts them all.
  const activeFilters = [
    size !== ALL,
    brand !== ALL,
    retailerId !== ALL,
    shoeType !== ALL,
    minSavings !== '',
    sort !== 'savings_desc',
  ].filter(Boolean).length
  const hasFilters = activeFilters > 0

  return (
    <PublicLayout lastScrape={checkedAt}>
      <div className="space-y-4 sm:space-y-6">
        <PageHeader
          title="Musa's picks"
          description={`Shoes I'd actually buy, on sale now at Canadian retailers.`}
        />

        <Card>
          <CardContent className="grid grid-cols-2 gap-3 p-4 sm:gap-4 md:grid-cols-3 lg:grid-cols-6">
            <FilterDisclosure
              className="col-span-2"
              open={filtersOpen}
              onToggle={() => setFiltersOpen((o) => !o)}
              count={activeFilters}
            />

            {/* `contents` makes these grid items on md+; on phones they collapse. */}
            <div className={filtersOpen ? 'contents' : 'hidden md:contents'}>
              <div className="col-span-2 space-y-1.5 md:col-span-1">
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
                    {retailers.map((r) => (
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
                    {types.map((t) => (
                      <SelectItem key={t} value={t}>
                        {formatShoeType(t)}
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
            </div>

            {hasFilters && (
              <div className="col-span-2 flex items-end md:col-span-3 lg:col-span-6">
                <Button variant="ghost" size="sm" onClick={resetFilters}>
                  <SlidersHorizontal className="h-4 w-4" /> Clear filters
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <section className="space-y-4">
          {!query.isLoading && !query.isError && all.length > 0 && (
            <span className="font-mono text-xs text-muted-foreground">
              {groups.length} shoe{groups.length === 1 ? '' : 's'} · {visible.length} deal
              {visible.length === 1 ? '' : 's'}
            </span>
          )}

          {query.isLoading ? (
            <CardSkeletonGrid count={6} />
          ) : query.isError ? (
            <ErrorState error={query.error} onRetry={query.refetch} />
          ) : groups.length ? (
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
              {groups.map((group) => (
                <ShoeProductCard
                  key={group.shoeId}
                  group={group}
                  onViewDetails={(deal) => setSelected(deal)}
                  compactMobile
                />
              ))}
            </div>
          ) : all.length === 0 ? (
            <EmptyState
              icon={Tag}
              title="No picks on sale right now"
              description="Nothing on my list is discounted at the moment. Check back soon."
            />
          ) : (
            <EmptyState
              icon={Tag}
              title="No picks match your filters"
              description="Try a different size or clear the filters."
              action={
                <Button variant="outline" size="sm" onClick={resetFilters}>
                  Clear filters
                </Button>
              }
            />
          )}
        </section>
      </div>

      <PublicDealSheet deal={selected} open={!!selected} onOpenChange={(o) => !o && setSelected(null)} />
    </PublicLayout>
  )
}
