import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft,
  Footprints,
  PlayCircle,
  Pencil,
  Plus,
  Trash2,
  Sparkles,
} from 'lucide-react'
import MileageProgressBar from '@/components/MileageProgressBar'
import OwnedShoeForm from '@/components/OwnedShoeForm'
import LogRunDialog from '@/components/LogRunDialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { ErrorState, EmptyState } from '@/components/StatusViews'
import { useToast } from '@/components/ui/toast'
import {
  useOwnedShoe,
  useUpdateOwnedShoe,
  useShoeRuns,
  useDeleteShoeRun,
  useShoeNotes,
  useAddShoeNote,
  useDeleteShoeNote,
} from '@/hooks/useApi'
import { cn, formatDate, formatCurrency } from '@/lib/utils'

const statusVariant = { active: 'success', retired: 'secondary', for_sale: 'warning' }
const statusLabel = { active: 'Active', retired: 'Retired', for_sale: 'For sale' }

export default function ShoeDetail() {
  const { id } = useParams()
  const shoeId = Number(id)
  const navigate = useNavigate()
  const shoeQuery = useOwnedShoe(shoeId)
  const shoe = shoeQuery.data

  const [editing, setEditing] = useState(false)
  const [adjustingMileage, setAdjustingMileage] = useState(false)
  const [loggingRun, setLoggingRun] = useState(false)
  const update = useUpdateOwnedShoe()
  const { toast } = useToast()

  if (shoeQuery.isLoading) {
    return <div className="h-[300px] animate-pulse rounded-lg bg-muted" />
  }
  if (shoeQuery.isError || !shoe) {
    return <ErrorState error={shoeQuery.error} onRetry={shoeQuery.refetch} />
  }

  const image = shoe.image_url || shoe.matched_image_url
  const handleEditSubmit = (payload) => {
    update.mutate(
      { id: shoe.id, data: payload },
      {
        onSuccess: () => {
          toast({ variant: 'success', title: 'Shoe updated' })
          setEditing(false)
        },
        onError: (err) => toast({ variant: 'destructive', title: 'Save failed', description: err.message }),
      }
    )
  }

  return (
    <div className="space-y-8">
      <Link to="/my-shoes" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to My Shoes
      </Link>

      {/* Header */}
      <div className="flex flex-col gap-5 sm:flex-row">
        <div className="flex h-[120px] w-[120px] shrink-0 items-center justify-center overflow-hidden rounded-[14px] bg-[repeating-linear-gradient(135deg,#202327,#202327_6px,#26292E_6px,#26292E_12px)]">
          {image ? (
            <img src={image} alt={shoe.model} className="h-full w-full object-contain" />
          ) : (
            <Footprints className="h-10 w-10 text-faint" />
          )}
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <div className="text-[11px] font-bold uppercase tracking-[0.08em] text-accent-foreground">
                {shoe.brand}
              </div>
              <h1 className="font-heading text-2xl font-extrabold leading-tight text-foreground">
                {shoe.nickname || shoe.model}
              </h1>
              {shoe.nickname && <div className="text-sm text-faint">{shoe.model}</div>}
            </div>
            <Badge variant={statusVariant[shoe.status] || 'secondary'}>{statusLabel[shoe.status] || shoe.status}</Badge>
          </div>

          {shoe.purchase_price ? (
            <div className="text-sm text-muted-foreground">
              Bought for {formatCurrency(shoe.purchase_price)}
              {shoe.cost_per_km != null && ` · ${formatCurrency(shoe.cost_per_km)}/km`}
            </div>
          ) : (
            <div className="text-sm text-faint">
              Purchase price not recorded —{' '}
              <button type="button" onClick={() => setEditing(true)} className="text-accent-foreground underline">
                add it
              </button>
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            <Button size="sm" onClick={() => setLoggingRun(true)}>
              <PlayCircle className="h-3.5 w-3.5" /> Log run
            </Button>
            <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
              <Pencil className="h-3.5 w-3.5" /> Edit
            </Button>
            <Button size="sm" variant="outline" onClick={() => setAdjustingMileage(true)}>
              Adjust mileage
            </Button>
          </div>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 gap-4 rounded-[14px] border border-border bg-surface p-4 sm:grid-cols-3">
        <div className="space-y-1.5">
          <div className="text-[11px] font-bold uppercase tracking-[0.08em] text-faint">Mileage</div>
          <MileageProgressBar mileage={shoe.current_mileage} />
        </div>
        <Stat label="Total runs" value={shoe.total_runs ?? 0} />
        <div className="flex flex-col gap-1">
          {shoe.lifetime_avg_pace && <Stat label="Avg pace" value={shoe.lifetime_avg_pace} />}
          {shoe.lifetime_avg_hr && <Stat label="Avg HR" value={`${shoe.lifetime_avg_hr} bpm`} />}
        </div>
      </div>

      {/* Replacement deals placeholder */}
      <section className="rounded-[14px] border border-dashed border-border bg-surface/50 p-5">
        <div className="mb-1.5 flex items-center gap-2">
          <h2 className="font-heading text-base font-bold text-foreground">Replacement Deals</h2>
          <Badge variant="secondary" className="gap-1 text-[10px]">
            <Sparkles className="h-3 w-3" /> Coming soon
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          When this shoe approaches retirement, we'll surface deals on the same or similar model here.
        </p>
      </section>

      {/* Notes journal */}
      <NotesJournal ownedShoeId={shoe.id} />

      {/* Run history */}
      <RunHistory ownedShoeId={shoe.id} />

      {/* Edit dialog */}
      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit shoe</DialogTitle>
            <DialogDescription>Update mileage, purchase price, or status for this shoe.</DialogDescription>
          </DialogHeader>
          <OwnedShoeForm
            initial={shoe}
            submitting={update.isPending}
            onSubmit={handleEditSubmit}
            onCancel={() => setEditing(false)}
          />
        </DialogContent>
      </Dialog>

      {/* Adjust mileage */}
      <AdjustMileageDialog
        shoe={shoe}
        open={adjustingMileage}
        onOpenChange={setAdjustingMileage}
      />

      {/* Log run */}
      <LogRunDialog shoe={shoe} open={loggingRun} onOpenChange={setLoggingRun} />
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="space-y-1">
      <div className="text-[11px] font-bold uppercase tracking-[0.08em] text-faint">{label}</div>
      <div className="font-heading text-lg font-bold text-foreground">{value}</div>
    </div>
  )
}

function AdjustMileageDialog({ shoe, open, onOpenChange }) {
  const [value, setValue] = useState('')
  const [confirming, setConfirming] = useState(false)
  const update = useUpdateOwnedShoe()
  const { toast } = useToast()

  const reset = () => {
    setValue('')
    setConfirming(false)
    onOpenChange(false)
  }

  const parsed = parseFloat(value)
  const valid = value !== '' && !Number.isNaN(parsed) && parsed >= 0

  const handleConfirm = () => {
    update.mutate(
      { id: shoe.id, data: { current_mileage: parsed } },
      {
        onSuccess: () => {
          toast({ variant: 'success', title: 'Mileage updated' })
          reset()
        },
        onError: (err) => toast({ variant: 'destructive', title: 'Update failed', description: err.message }),
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && reset()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Adjust mileage</DialogTitle>
          <DialogDescription>
            Directly correct this shoe's current mileage. This doesn't log a run.
          </DialogDescription>
        </DialogHeader>
        {!confirming ? (
          <>
            <Input
              type="number"
              step="0.1"
              min="0"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={String(shoe.current_mileage)}
              autoFocus
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={reset}>
                Cancel
              </Button>
              <Button type="button" onClick={() => valid && setConfirming(true)} disabled={!valid}>
                Continue
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <p className="text-sm text-foreground">
              Set mileage to {parsed} km? This will override the current value of {shoe.current_mileage} km.
            </p>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setConfirming(false)}>
                Back
              </Button>
              <Button type="button" onClick={handleConfirm} disabled={update.isPending}>
                {update.isPending ? 'Saving…' : 'Confirm'}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

function NotesJournal({ ownedShoeId }) {
  const notes = useShoeNotes(ownedShoeId)
  const addNote = useAddShoeNote()
  const deleteNote = useDeleteShoeNote()
  const [adding, setAdding] = useState(false)
  const [body, setBody] = useState('')
  const [deleting, setDeleting] = useState(null)
  const { toast } = useToast()

  const handleAdd = () => {
    if (!body.trim()) return
    addNote.mutate(
      { id: ownedShoeId, data: { body: body.trim(), triggered_by: 'manual' } },
      {
        onSuccess: () => {
          toast({ variant: 'success', title: 'Note added' })
          setBody('')
          setAdding(false)
        },
        onError: (err) => toast({ variant: 'destructive', title: 'Failed to add note', description: err.message }),
      }
    )
  }

  const confirmDelete = () => {
    deleteNote.mutate(
      { id: ownedShoeId, noteId: deleting.id },
      {
        onSuccess: () => {
          toast({ variant: 'success', title: 'Note removed' })
          setDeleting(null)
        },
        onError: (err) => toast({ variant: 'destructive', title: 'Failed to remove note', description: err.message }),
      }
    )
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-base font-bold text-foreground">Shoe Notes Journal</h2>
        <Button size="sm" onClick={() => setAdding(true)}>
          <Plus className="h-3.5 w-3.5" /> Add note
        </Button>
      </div>

      {notes.isError ? (
        <ErrorState error={notes.error} onRetry={notes.refetch} />
      ) : notes.isLoading ? (
        <div className="h-[80px] animate-pulse rounded-md bg-muted" />
      ) : notes.data?.length ? (
        <div className="space-y-3 border-l-2 border-border pl-4">
          {notes.data.map((note) => (
            <div key={note.id} className="relative rounded-[10px] border border-border bg-surface p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-[11px] text-faint">
                  <span>{formatDate(note.created_at)}</span>
                  <span>·</span>
                  <span>{Math.round(note.mileage_at_note)} km</span>
                  {note.triggered_by === 'checkpoint' && (
                    <Badge variant="secondary" className="text-[10px]">
                      Checkpoint
                    </Badge>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setDeleting(note)}
                  aria-label="Delete note"
                  className="text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              <p className="mt-1.5 text-sm text-foreground">{note.body}</p>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState title="No notes yet" description="Add your first observation about these shoes." />
      )}

      <Dialog open={adding} onOpenChange={(o) => !o && setAdding(false)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Add note</DialogTitle>
          </DialogHeader>
          <Textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="How are these shoes feeling?"
            autoFocus
          />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setAdding(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={handleAdd} disabled={addNote.isPending || !body.trim()}>
              {addNote.isPending ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Delete this note?</DialogTitle>
            <DialogDescription>This cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button type="button" variant="destructive" onClick={confirmDelete} disabled={deleteNote.isPending}>
              {deleteNote.isPending ? 'Removing…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}

function RunHistory({ ownedShoeId }) {
  const runs = useShoeRuns(ownedShoeId)
  const deleteRun = useDeleteShoeRun()
  const [deletingRun, setDeletingRun] = useState(null)
  const [expandedNoteId, setExpandedNoteId] = useState(null)
  const { toast } = useToast()

  const confirmDeleteRun = () => {
    deleteRun.mutate(deletingRun, {
      onSuccess: () => {
        toast({ variant: 'success', title: 'Run removed' })
        setDeletingRun(null)
      },
      onError: (err) => toast({ variant: 'destructive', title: 'Failed to remove run', description: err.message }),
    })
  }

  return (
    <section className="space-y-3">
      <h2 className="font-heading text-base font-bold text-foreground">Run History</h2>

      {runs.isError ? (
        <ErrorState error={runs.error} onRetry={runs.refetch} />
      ) : runs.isLoading ? (
        <div className="h-[160px] animate-pulse rounded-md bg-muted" />
      ) : runs.data?.length ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Distance (km)</TableHead>
              <TableHead>Avg Pace</TableHead>
              <TableHead>Avg HR</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Notes</TableHead>
              <TableHead className="w-0" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.data.map((run) => {
              const isLong = (run.notes || '').length > 40
              const expanded = expandedNoteId === run.id
              return (
                <TableRow key={run.id}>
                  <TableCell>{formatDate(run.run_date)}</TableCell>
                  <TableCell>{run.distance_km}</TableCell>
                  <TableCell>{run.avg_pace || '—'}</TableCell>
                  <TableCell>{run.avg_hr || '—'}</TableCell>
                  <TableCell>
                    <Badge variant={run.source === 'coros' ? 'default' : 'secondary'} className="text-[10px] capitalize">
                      {run.source}
                    </Badge>
                  </TableCell>
                  <TableCell
                    className={cn('max-w-[200px]', isLong && 'cursor-pointer', !expanded && 'truncate')}
                    onClick={() => isLong && setExpandedNoteId(expanded ? null : run.id)}
                  >
                    {run.notes || '—'}
                  </TableCell>
                  <TableCell>
                    <button
                      type="button"
                      onClick={() => setDeletingRun(run)}
                      aria-label="Remove run"
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      ) : (
        <p className="text-sm text-muted-foreground">No runs logged yet.</p>
      )}

      <Dialog open={!!deletingRun} onOpenChange={(o) => !o && setDeletingRun(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Remove this run?</DialogTitle>
            <DialogDescription>
              {deletingRun && `This will subtract ${deletingRun.distance_km} km from your shoe mileage. This cannot be undone.`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingRun(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDeleteRun} disabled={deleteRun.isPending}>
              {deleteRun.isPending ? 'Removing…' : 'Remove'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
