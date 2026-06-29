import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Pencil, Trash2, Footprints, PlayCircle, Search, ArrowUpRight, RefreshCw, ChevronDown } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import OwnedShoeForm from '@/components/OwnedShoeForm'
import LogRunDialog from '@/components/LogRunDialog'
import MileageProgressBar from '@/components/MileageProgressBar'
import CorosSyncModal from '@/components/CorosSyncModal'
import ShoeTypeBadge from '@/components/ShoeTypeBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
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
  useOwnedShoes,
  useCreateOwnedShoe,
  useUpdateOwnedShoe,
  useDeleteOwnedShoe,
  useCorosSyncStatus,
} from '@/hooks/useApi'

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
  const [search, setSearch] = useState('')
  const [formState, setFormState] = useState(null) // null | { shoe?: shoe }
  const [deleting, setDeleting] = useState(null)
  const [logRunShoe, setLogRunShoe] = useState(null)
  const [corosSyncOpen, setCorosSyncOpen] = useState(false)
  const [retiredCollapsed, setRetiredCollapsed] = useState(false)

  const shoes = useOwnedShoes()
  const create = useCreateOwnedShoe()
  const update = useUpdateOwnedShoe()
  const remove = useDeleteOwnedShoe()
  const corosStatus = useCorosSyncStatus()
  const { toast } = useToast()

  const filtered = (shoes.data || []).filter((s) => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return (
      s.brand.toLowerCase().includes(q) ||
      s.model.toLowerCase().includes(q) ||
      (s.nickname || '').toLowerCase().includes(q)
    )
  })
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
      <PageHeader eyebrow="MY SHOES" title="Shoe rotation" count={shoes.data?.length}>
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

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder="Search by brand, model, or nickname…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

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
                onOpenDetail={() => navigate(`/my-shoes/${shoe.id}`)}
                onLogRun={() => setLogRunShoe(shoe)}
                onEdit={() => setFormState({ shoe })}
                onDelete={() => setDeleting(shoe)}
              />
            ))}

            <button
              type="button"
              onClick={() => setFormState({})}
              className="flex min-h-[180px] flex-col items-center justify-center gap-2.5 rounded-[14px] border-[1.5px] border-dashed border-[#2E3239] text-faint hover:border-primary/40 hover:text-muted-foreground"
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
                className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.08em] text-faint hover:text-muted-foreground transition-colors mb-3.5"
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
                      onOpenDetail={() => navigate(`/my-shoes/${shoe.id}`)}
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
          title={search ? 'No matching shoes' : 'No shoes in rotation yet'}
          description={
            search
              ? 'Try a different search.'
              : 'Add a shoe to start tracking mileage and run history.'
          }
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
                `This removes "${deleting.brand} ${deleting.model}" and its run history. This cannot be undone.`}
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
      <button type="button" onClick={onOpenDetail} className="flex flex-col gap-3.5 p-4 text-left">
        <div className="flex gap-3.5">
          <div className="flex h-[74px] w-[74px] shrink-0 items-center justify-center overflow-hidden rounded-[11px] bg-[repeating-linear-gradient(135deg,#202327,#202327_6px,#26292E_6px,#26292E_12px)]">
            {image ? (
              <img src={image} alt={shoe.model} className="h-full w-full object-contain" />
            ) : (
              <Footprints className="h-6 w-6 text-faint" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-[0.08em] text-accent-foreground">
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
        <MileageProgressBar mileage={shoe.current_mileage} compact />
      </button>
      <div className="grid grid-cols-2 border-t border-border text-[12px] font-bold">
        <button
          type="button"
          onClick={onOpenDetail}
          className="flex items-center justify-center gap-1.5 border-b border-r border-border py-2 text-secondary-foreground hover:bg-secondary"
        >
          <ArrowUpRight className="h-3.5 w-3.5" /> Details
        </button>
        <button
          type="button"
          onClick={onLogRun}
          className="flex items-center justify-center gap-1.5 border-b border-border py-2 text-secondary-foreground hover:bg-secondary"
        >
          <PlayCircle className="h-3.5 w-3.5" /> Log run
        </button>
        <button
          type="button"
          onClick={onEdit}
          className="flex items-center justify-center gap-1.5 border-r border-border py-2 text-secondary-foreground hover:bg-secondary"
        >
          <Pencil className="h-3.5 w-3.5" /> Edit
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="flex items-center justify-center gap-1.5 py-2 text-muted-foreground hover:bg-secondary hover:text-destructive"
        >
          <Trash2 className="h-3.5 w-3.5" /> Remove
        </button>
      </div>
    </div>
  )
}

