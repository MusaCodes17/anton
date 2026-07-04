import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Pencil, Trash2, Footprints, PlayCircle, ArrowUpRight, RefreshCw, ChevronDown, MoreHorizontal } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import OwnedShoeForm from '@/components/OwnedShoeForm'
import LogRunDialog from '@/components/LogRunDialog'
import MileageProgressBar from '@/components/MileageProgressBar'
import CorosSyncModal from '@/components/CorosSyncModal'
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
  DialogFooter,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { ErrorState, EmptyState, CardSkeletonGrid } from '@/components/StatusViews'
import { useToast } from '@/components/ui/toast'
import {
  useOwnedShoes,
  useCreateOwnedShoe,
  useUpdateOwnedShoe,
  useDeleteOwnedShoe,
  useCorosSyncStatus,
} from '@/hooks/useApi'
import { SHOE_TYPES, SHOE_TYPE_LABELS } from '@/lib/shoeTypes'

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
  const [formState, setFormState] = useState(null) // null | { shoe?: shoe }
  const [deleting, setDeleting] = useState(null)
  const [logRunShoe, setLogRunShoe] = useState(null)
  const [corosSyncOpen, setCorosSyncOpen] = useState(false)
  const [retiredCollapsed, setRetiredCollapsed] = useState(true)

  const shoes = useOwnedShoes()
  const create = useCreateOwnedShoe()
  const update = useUpdateOwnedShoe()
  const remove = useDeleteOwnedShoe()
  const corosStatus = useCorosSyncStatus()
  const { toast } = useToast()

  const brands = useMemo(() => {
    const set = new Set((shoes.data || []).map((s) => s.brand))
    return [...set].sort()
  }, [shoes.data])

  const hasFilters = brand !== ALL || shoeType !== ALL || mileageBucket !== ALL || sort !== 'name_asc'

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

  const handleSubmit = (payload) => {
    const editing = formState?.shoe
    const mutation = editing ? update : create
    const args = editing ? { id: editing.id, data: payload } : payload
    mutation.mutate(args, {
      onSuccess: () => {
        toast({ variant: 'success', title: editing ? 'Shoe updated' : 'Shoe added' })
        setFormState(null)
      },
      onError: (err) =>
        toast({ variant: 'destructive', title: 'Save failed', description: err.message }),
    })
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
      <PageHeader eyebrow="MY SHOES" title="Shoe rotation" count={shoes.data?.filter((s) => s.status !== 'retired').length}>
        <Button
          variant="outline"
          onClick={() => setCorosSyncOpen(true)}
          disabled={corosStatus.data && !corosStatus.data.coros_configured}
          title={
            corosStatus.data && !corosStatus.data.coros_configured
              ? 'Add COROS credentials to .env to enable sync'
              : corosStatus.data?.last_sync_at
              ? `Last synced ${new Date(corosStatus.data.last_sync_at).toLocaleString()}`
              : 'Sync runs from COROS watch'
          }
        >
          <RefreshCw className="h-4 w-4" /> Sync from COROS
        </Button>
        <Button onClick={() => setFormState({})}>
          <Plus className="h-4 w-4" /> Add shoe
        </Button>
      </PageHeader>

      <Card>
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
                {SHOE_TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
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
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
            {activeShoes.map((shoe) => (
              <ShoeCard
                key={shoe.id}
                shoe={shoe}
                onOpenDetail={() => navigate(`/shoes/${shoe.id}`)}
                onLogRun={() => setLogRunShoe(shoe)}
                onEdit={() => setFormState({ shoe })}
                onDelete={() => setDeleting(shoe)}
              />
            ))}

            <button
              type="button"
              onClick={() => setFormState({})}
              className="focus-ring flex min-h-[180px] flex-col items-center justify-center gap-2.5 rounded-[14px] border-[1.5px] border-dashed border-edge text-faint hover:border-primary/40 hover:text-muted-foreground"
            >
              <span className="flex h-[42px] w-[42px] items-center justify-center rounded-[11px] border border-border bg-surface text-xl leading-none text-accent-foreground">
                +
              </span>
              <span className="text-sm font-bold text-secondary-foreground">Add a shoe</span>
            </button>
          </div>

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
                <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
                  {retiredShoes.map((shoe) => (
                    <ShoeCard
                      key={shoe.id}
                      shoe={shoe}
                      onOpenDetail={() => navigate(`/shoes/${shoe.id}`)}
                      onLogRun={() => setLogRunShoe(shoe)}
                      onEdit={() => setFormState({ shoe })}
                      onDelete={() => setDeleting(shoe)}
                    />
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
                ? 'Update mileage, purchase price, or status for this shoe.'
                : 'Add a shoe to your personal rotation.'}
            </DialogDescription>
          </DialogHeader>
          {formState && (
            <OwnedShoeForm
              initial={formState.shoe}
              submitting={create.isPending || update.isPending}
              onSubmit={handleSubmit}
              onCancel={() => setFormState(null)}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Log run dialog */}
      <LogRunDialog
        shoe={logRunShoe}
        open={!!logRunShoe}
        onOpenChange={(o) => !o && setLogRunShoe(null)}
      />

      {/* COROS sync modal */}
      <CorosSyncModal
        open={corosSyncOpen}
        onOpenChange={setCorosSyncOpen}
        activeShoes={(shoes.data || []).filter((s) => s.status !== 'retired')}
        lastSyncAt={corosStatus.data?.last_sync_at}
      />

      {/* Delete confirmation */}
      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Delete shoe?</DialogTitle>
            <DialogDescription>
              {deleting &&
                `This removes "${deleting.brand} ${deleting.model}"${
                  deleting.total_runs
                    ? ` and its ${deleting.total_runs} logged run${deleting.total_runs === 1 ? '' : 's'}`
                    : ' and its run history'
                }. This cannot be undone.`}
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

function ShoeCard({ shoe, onOpenDetail, onLogRun, onEdit, onDelete }) {
  const image = shoe.image_url || shoe.matched_image_url

  return (
    <div className="flex flex-col overflow-hidden rounded-[14px] border border-border bg-surface">
      <button type="button" onClick={onOpenDetail} className="focus-ring flex flex-col gap-3.5 p-4 text-left">
        <div className="flex gap-3.5">
          <div className="flex h-[74px] w-[74px] shrink-0 items-center justify-center overflow-hidden rounded-[11px] bg-placeholder-stripes">
            {image ? (
              <img src={image} alt={shoe.model} className="h-full w-full object-contain" />
            ) : (
              <Footprints className="h-6 w-6 text-faint" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-2xs font-bold uppercase tracking-[0.08em] text-accent-foreground">
                  {shoe.brand}
                </div>
                <div className="mt-0.5 truncate font-heading text-base font-bold leading-tight text-foreground">
                  {shoe.nickname || shoe.model}
                </div>
                {shoe.nickname && <div className="truncate text-xs text-faint">{shoe.model}</div>}
                {shoe.shoe_type && (
                  <div className="mt-1">
                    <ShoeTypeBadge type={shoe.shoe_type} />
                  </div>
                )}
              </div>
              <Badge variant={statusVariant[shoe.status] || 'secondary'}>
                {statusLabel[shoe.status] || shoe.status}
              </Badge>
            </div>
          </div>
        </div>
        <MileageProgressBar mileage={shoe.current_mileage} limit={shoe.mileage_limit ?? 800} compact />
      </button>
      <div className="grid grid-cols-[1fr_1fr_auto] border-t border-border text-[12px] font-bold">
        <button
          type="button"
          onClick={onOpenDetail}
          className="focus-ring flex items-center justify-center gap-1.5 border-r border-border py-2 text-secondary-foreground hover:bg-secondary"
        >
          <ArrowUpRight className="h-3.5 w-3.5" /> Details
        </button>
        <button
          type="button"
          onClick={onLogRun}
          className="focus-ring flex items-center justify-center gap-1.5 border-r border-border py-2 text-secondary-foreground hover:bg-secondary"
        >
          <PlayCircle className="h-3.5 w-3.5" /> Log run
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label="More actions"
            className="focus-ring flex items-center justify-center px-3 py-2 text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <MoreHorizontal className="h-4 w-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={onEdit}>
              <Pencil className="h-3.5 w-3.5" /> Edit
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={onDelete}
              className="text-destructive focus:bg-destructive/10 focus:text-destructive"
            >
              <Trash2 className="h-3.5 w-3.5" /> Remove
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}

