import { forwardRef, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Plus, Footprints, RefreshCw, ChevronDown, AlertTriangle, Tag } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import FilterDisclosure from '@/components/FilterDisclosure'
import OwnedShoeForm from '@/components/OwnedShoeForm'
import MileageProgressBar from '@/components/MileageProgressBar'
import ShoeTypeBadge from '@/components/ShoeTypeBadge'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { ErrorState, EmptyState, CardSkeletonGrid } from '@/components/StatusViews'
import { useToast } from '@/components/ui/toast'
import {
  useOwnedShoes,
  useRotationOverview,
  useCreateOwnedShoe,
  useCorosStatus,
  useShoeTypes,
} from '@/hooks/useApi'
import { formatShoeType } from '@/lib/shoeTypes'
import { cn } from '@/lib/utils'
import { forecastLabel } from '@/lib/forecast'

const ALL = '__all__'

const MILEAGE_BUCKETS = [
  { value: 'under_200', label: 'Under 200 km', test: (km) => km < 200 },
  { value: '200_500', label: '200–500 km', test: (km) => km >= 200 && km < 500 },
  { value: '500_800', label: '500–800 km', test: (km) => km >= 500 && km < 800 },
  { value: 'over_800', label: 'Over 800 km', test: (km) => km >= 800 },
]

const SORTS = {
  name_asc: { label: 'Name (A–Z)', fn: (a, b) => `${a.brand} ${a.model}`.localeCompare(`${b.brand} ${b.model}`) },
  mileage_desc: { label: 'Most mileage', fn: (a, b) => b.current_mileage - a.current_mileage },
  mileage_asc: { label: 'Least mileage', fn: (a, b) => a.current_mileage - b.current_mileage },
  newest: { label: 'Newest added', fn: (a, b) => new Date(b.created_at) - new Date(a.created_at) },
}

// Untyped shoes fall into a trailing "Uncategorized" group. The by-type group
// order follows the fetched vocabulary (see `typeOrder` in the component).
const UNTYPED = '__untyped__'

const statusVariant = {
  active: 'success',
  retired: 'secondary',
  for_sale: 'warning',
}

const statusLabel = {
  active: 'Active',
  retired: 'Retired',
  for_sale: 'For sale',
}

export default function MyShoes() {
  const navigate = useNavigate()
  const [brand, setBrand] = useState(ALL)
  const [shoeType, setShoeType] = useState(ALL)
  const [mileageBucket, setMileageBucket] = useState(ALL)
  const [sort, setSort] = useState('name_asc')
  const [adding, setAdding] = useState(false)
  const [retiredCollapsed, setRetiredCollapsed] = useState(true)
  // Mobile-only: filters collapse behind a toggle (as on Deals) so the
  // rotation is above the fold; always inline on md+.
  const [filtersOpen, setFiltersOpen] = useState(false)

  const shoes = useOwnedShoes()
  const { data: shoeTypes = [] } = useShoeTypes()
  const overview = useRotationOverview()
  const create = useCreateOwnedShoe()
  const corosStatus = useCorosStatus()
  const { toast } = useToast()

  const brands = useMemo(() => {
    const set = new Set((shoes.data || []).map((s) => s.brand))
    return [...set].sort()
  }, [shoes.data])

  const activeFilters = [brand !== ALL, shoeType !== ALL, mileageBucket !== ALL, sort !== 'name_asc'].filter(Boolean).length
  const hasFilters = activeFilters > 0

  const resetFilters = () => {
    setBrand(ALL)
    setShoeType(ALL)
    setMileageBucket(ALL)
    setSort('name_asc')
  }

  const filtered = useMemo(() => {
    let list = shoes.data || []
    if (brand !== ALL) list = list.filter((s) => s.brand === brand)
    if (shoeType !== ALL) list = list.filter((s) => s.shoe_type === shoeType)
    if (mileageBucket !== ALL) {
      const bucket = MILEAGE_BUCKETS.find((b) => b.value === mileageBucket)
      if (bucket) list = list.filter((s) => bucket.test(s.current_mileage))
    }
    return [...list].sort(SORTS[sort]?.fn ?? SORTS.name_asc.fn)
  }, [shoes.data, brand, shoeType, mileageBucket, sort])

  const activeShoes = filtered.filter((s) => s.status !== 'retired')
  const retiredShoes = filtered.filter((s) => s.status === 'retired')

  // Active rotation grouped by shoe type, groups ordered like the type filter,
  // "Uncategorized" last. Within a group, the active `sort` ordering is
  // preserved (filtered is already sorted).
  const activeGroups = useMemo(() => {
    const byType = new Map()
    for (const shoe of activeShoes) {
      const key = shoe.shoe_type || UNTYPED
      if (!byType.has(key)) byType.set(key, [])
      byType.get(key).push(shoe)
    }
    const order = [...shoeTypes, UNTYPED]
    return [...byType.entries()]
      .sort(([a], [b]) => order.indexOf(a) - order.indexOf(b))
      .map(([type, list]) => ({
        type,
        label: type === UNTYPED ? 'Uncategorized' : formatShoeType(type),
        shoes: list,
        totalKm: list.reduce((sum, s) => sum + (s.current_mileage || 0), 0),
      }))
  }, [activeShoes, shoeTypes])

  // Server-computed retirement pipeline (shoes ≥75% of limit + replacement-deal
  // counts), intersected with the current filters and joined to full shoe rows.
  const pipeline = useMemo(() => {
    const entries = overview.data?.pipeline || []
    const activeById = new Map(activeShoes.map((s) => [s.id, s]))
    return entries
      .map((e) => ({ ...e, shoe: activeById.get(e.owned_shoe_id) }))
      .filter((e) => e.shoe) // drop entries filtered out client-side
  }, [overview.data, activeShoes])

  const handleSubmit = (payload) => {
    create.mutate(payload, {
      onSuccess: () => {
        toast({ variant: 'success', title: 'Shoe added' })
        setAdding(false)
      },
      onError: (err) =>
        toast({ variant: 'destructive', title: 'Save failed', description: err.message }),
    })
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="MY SHOES" title="Shoe rotation" count={shoes.data?.filter((s) => s.status !== 'retired').length}>
        {/* md+ only — phones get the same two actions as icon buttons in the
            filter row below, so the header doesn't eat a whole row. */}
        <div className="hidden items-center gap-3 md:flex">
          <Button variant="outline" asChild>
            <NewRunsLink corosStatus={corosStatus}>New runs</NewRunsLink>
          </Button>
          <Button onClick={() => setAdding(true)}>
            <Plus className="h-4 w-4" /> Add shoe
          </Button>
        </div>
      </PageHeader>

      <div className="flex gap-2 md:hidden">
        <FilterDisclosure
          className="min-w-0 flex-1"
          open={filtersOpen}
          onToggle={() => setFiltersOpen((o) => !o)}
          count={activeFilters}
        />
        <Button variant="outline" asChild className="h-auto w-12 shrink-0 px-0">
          <NewRunsLink corosStatus={corosStatus} aria-label="New runs" />
        </Button>
        <Button onClick={() => setAdding(true)} className="h-auto w-12 shrink-0 px-0" aria-label="Add shoe">
          <Plus className="h-5 w-5" />
        </Button>
      </div>

      <Card className={`md:block ${filtersOpen ? '' : 'hidden'}`}>
        <CardContent className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label>Brand</Label>
            <Select value={brand} onValueChange={setBrand}>
              <SelectTrigger>
                <SelectValue placeholder="All brands" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All brands</SelectItem>
                {brands.map((b) => (
                  <SelectItem key={b} value={b}>{b}</SelectItem>
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
                  <SelectItem key={t} value={t}>{formatShoeType(t)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>Mileage</Label>
            <Select value={mileageBucket} onValueChange={setMileageBucket}>
              <SelectTrigger>
                <SelectValue placeholder="All mileage" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All mileage</SelectItem>
                {MILEAGE_BUCKETS.map((b) => (
                  <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>Sort by</Label>
            <Select value={sort} onValueChange={setSort}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(SORTS).map(([key, { label }]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
        {hasFilters && (
          <div className="border-t border-border px-4 py-2">
            <button
              type="button"
              onClick={resetFilters}
              className="focus-ring rounded text-xs text-muted-foreground hover:text-foreground"
            >
              Reset filters
            </button>
          </div>
        )}
      </Card>

      {shoes.isLoading ? (
        <CardSkeletonGrid count={6} />
      ) : shoes.isError ? (
        <ErrorState error={shoes.error} onRetry={shoes.refetch} />
      ) : filtered.length ? (
        <div className="space-y-8">
          {pipeline.length > 0 && <RetirementPipeline entries={pipeline} onOpenDetail={(id) => navigate(`/shoes/${id}`)} />}

          {activeGroups.map((group) => (
            <section key={group.type}>
              <div className="mb-3.5 flex items-center gap-2 text-2xs font-bold uppercase tracking-[0.08em] text-faint">
                <span>{group.label}</span>
                <span className="text-edge">·</span>
                <span>{group.shoes.length}</span>
                <span className="text-edge">·</span>
                <span className="tabular-nums">{Math.round(group.totalKm)} km</span>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:gap-3.5 lg:grid-cols-3">
                {group.shoes.map((shoe) => (
                  <ShoeCard key={shoe.id} shoe={shoe} />
                ))}
              </div>
            </section>
          ))}

          <button
            type="button"
            onClick={() => setAdding(true)}
            className="focus-ring flex w-full items-center justify-center gap-2 rounded-[14px] border-[1.5px] border-dashed border-edge py-4 text-sm font-bold text-secondary-foreground hover:border-primary/40 hover:text-foreground"
          >
            <Plus className="h-4 w-4" /> Add a shoe
          </button>

          {retiredShoes.length > 0 && (
            <div className="border-t border-border pt-6">
              <button
                type="button"
                onClick={() => setRetiredCollapsed((c) => !c)}
                className="focus-ring rounded flex items-center gap-2 text-2xs font-bold uppercase tracking-[0.08em] text-faint hover:text-muted-foreground transition-colors mb-3.5"
              >
                <ChevronDown
                  className={`h-3.5 w-3.5 transition-transform duration-200 ${retiredCollapsed ? '-rotate-90' : ''}`}
                />
                Retired · {retiredShoes.length}
              </button>
              {!retiredCollapsed && (
                <div className="grid grid-cols-2 gap-3 sm:gap-3.5 lg:grid-cols-3">
                  {retiredShoes.map((shoe) => (
                    <ShoeCard key={shoe.id} shoe={shoe} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <EmptyState
          icon={Footprints}
          title={hasFilters ? 'No matching shoes' : 'No shoes in rotation yet'}
          description={
            hasFilters
              ? 'Try adjusting the filters.'
              : 'Add a shoe to start tracking mileage and run history.'
          }
          action={
            hasFilters ? (
              <Button variant="outline" onClick={resetFilters}>Reset filters</Button>
            ) : (
              <Button onClick={() => setAdding(true)}>
                <Plus className="h-4 w-4" /> Add shoe
              </Button>
            )
          }
        />
      )}

      {/* Add dialog */}
      <Dialog open={adding} onOpenChange={(o) => !o && setAdding(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add a shoe</DialogTitle>
            <DialogDescription>Add a shoe to your personal rotation.</DialogDescription>
          </DialogHeader>
          {adding && (
            <OwnedShoeForm
              submitting={create.isPending}
              onSubmit={handleSubmit}
              onCancel={() => setAdding(false)}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function RetirementPipeline({ entries, onOpenDetail }) {
  return (
    <section className="rounded-[14px] border border-warning/30 bg-warning/5 p-4">
      <div className="mb-1.5 flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-warning" />
        <h2 className="font-heading text-sm font-bold text-foreground">Retirement pipeline</h2>
        <Badge variant="warning">{entries.length}</Badge>
      </div>
      <p className="mb-3.5 text-xs text-muted-foreground">
        Past 75% of their mileage limit — worst first. Time to plan a replacement.
      </p>
      <div className="space-y-2.5">
        {entries.map((entry) => (
          <PipelineRow key={entry.owned_shoe_id} entry={entry} onOpenDetail={onOpenDetail} />
        ))}
      </div>
    </section>
  )
}

function PipelineRow({ entry, onOpenDetail }) {
  const { shoe, pct, current_mileage, mileage_limit, replacement_deals } = entry
  const forecast = forecastLabel(entry)
  const image = shoe.image_url || shoe.matched_image_url
  const overLimit = pct >= 1

  return (
    <div className="flex flex-col gap-3 rounded-[11px] border border-border bg-surface p-3 sm:flex-row sm:items-center">
      <button
        type="button"
        onClick={() => onOpenDetail(shoe.id)}
        className="focus-ring flex min-w-0 flex-1 items-center gap-3 rounded-lg text-left"
      >
        <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-[9px] bg-placeholder-stripes">
          {image ? (
            <img src={image} alt={shoe.model} className="h-full w-full object-contain" />
          ) : (
            <Footprints className="h-5 w-5 text-faint" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-heading text-sm font-bold text-foreground">
              {shoe.nickname || `${shoe.brand} ${shoe.model}`}
            </span>
            <Badge variant={overLimit ? 'destructive' : 'warning'}>{Math.round(pct * 100)}%</Badge>
          </div>
          <div className="mt-1.5 max-w-[240px]">
            <MileageProgressBar mileage={current_mileage} limit={mileage_limit} />
          </div>
          {forecast && <div className="mt-1 text-2xs text-muted-foreground">{forecast}</div>}
        </div>
      </button>
      <div className="shrink-0 sm:pl-2">
        {replacement_deals > 0 ? (
          <Button asChild variant="outline" size="sm">
            <Link to="/deals">
              <Tag className="h-3.5 w-3.5" />
              {replacement_deals} replacement deal{replacement_deals === 1 ? '' : 's'}
            </Link>
          </Button>
        ) : (
          <span className="text-2xs text-faint">No replacement deals yet</span>
        )}
      </div>
    </div>
  )
}

// R5.7: runs arrive via the backend poller; this opens the inbox where the
// runner confirms them. Never disabled — the inbox explains connection state.
// Rendered with a label on md+ and icon-only (count as a corner badge) on phones.
const NewRunsLink = forwardRef(function NewRunsLink({ corosStatus, children, className, ...props }, ref) {
  const sync = corosStatus.data?.sync
  const pending = sync?.pending_count ?? 0
  return (
    <Link
      ref={ref}
      to="/new-runs"
      title={sync?.last_success_at ? `Last synced ${new Date(sync.last_success_at).toLocaleString()}` : 'New runs from your COROS watch'}
      className={cn('relative', className)}
      {...props}
    >
      <RefreshCw className="h-4 w-4" />
      {children}
      {pending > 0 && (
        <span
          className={cn(
            'rounded-full bg-primary px-1.5 text-xs font-bold text-primary-foreground',
            children ? 'ml-1' : 'absolute -right-1.5 -top-1.5'
          )}
        >
          {pending}
        </span>
      )}
    </Link>
  )
})

// The whole card is a link to the shoe detail page (/shoes/:id), where logging,
// editing and removing a shoe live. Vertical tile so the rotation runs two-up
// on a phone, like the Deals grid (~165px per tile at 380px).
function ShoeCard({ shoe }) {
  const image = shoe.image_url || shoe.matched_image_url

  return (
    <Link
      to={`/shoes/${shoe.id}`}
      className="focus-ring flex min-w-0 flex-col overflow-hidden rounded-[14px] border border-border bg-surface text-left"
    >
      <div className="relative flex aspect-[4/3] w-full items-center justify-center overflow-hidden bg-placeholder-stripes">
        {image ? (
          <img src={image} alt={shoe.model} className="h-full w-full object-contain p-2" />
        ) : (
          <Footprints className="h-8 w-8 text-faint" />
        )}
        {/* Active is the default state of a card in the rotation, so only
            the exceptions (for sale, retired) earn a badge. */}
        {shoe.status !== 'active' && (
          <Badge variant={statusVariant[shoe.status] || 'secondary'} className="absolute right-2 top-2">
            {statusLabel[shoe.status] || shoe.status}
          </Badge>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2.5 p-3 sm:p-4">
        <div className="min-w-0">
          <div className="truncate text-2xs font-bold uppercase tracking-[0.08em] text-accent-foreground">
            {shoe.brand}
          </div>
          <div className="mt-0.5 line-clamp-2 font-heading text-[15px] font-bold leading-tight text-foreground sm:text-base">
            {shoe.nickname || shoe.model}
          </div>
          {shoe.nickname && <div className="truncate text-xs text-faint">{shoe.model}</div>}
          {shoe.shoe_type && (
            <div className="mt-1.5">
              <ShoeTypeBadge type={shoe.shoe_type} />
            </div>
          )}
        </div>
        <div className="mt-auto">
          <MileageProgressBar mileage={shoe.current_mileage} limit={shoe.mileage_limit ?? 800} compact />
        </div>
      </div>
    </Link>
  )
}
