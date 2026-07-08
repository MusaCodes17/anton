import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Flag, Plus, Pencil, Trash2, Check, ChevronDown, Footprints, MapPin } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { useToast } from '@/components/ui/toast'
import RaceForm from '@/components/training/RaceForm'
import {
  useRaces,
  useOwnedShoes,
  useCreateRace,
  useUpdateRace,
  useDeleteRace,
} from '@/hooks/useApi'
import { formatDate, formatDuration, parseDuration, cn } from '@/lib/utils'

const URGENT_DAYS = 14

function Countdown({ race }) {
  const { days_remaining, weeks_remaining } = race
  if (days_remaining === 0)
    return <span className="font-bold text-warning">Race day</span>
  if (days_remaining <= URGENT_DAYS)
    return (
      <span className="font-bold text-warning tabular-nums">
        {days_remaining} day{days_remaining === 1 ? '' : 's'}
      </span>
    )
  return (
    <span className="font-semibold text-foreground tabular-nums">
      {weeks_remaining} week{weeks_remaining === 1 ? '' : 's'}
      <span className="text-faint"> · {days_remaining} days</span>
    </span>
  )
}

function ShoeChip({ shoe }) {
  if (!shoe) return null
  return (
    <Link
      to={`/shoes/${shoe.id}`}
      className="focus-ring inline-flex min-w-0 items-center gap-1 rounded-full border border-border bg-secondary px-2 py-0.5 text-2xs font-medium text-secondary-foreground hover:border-primary/40"
      title={`${shoe.brand} ${shoe.model}`}
    >
      <Footprints className="h-3 w-3 shrink-0" />
      <span className="truncate">{shoe.nickname || shoe.model}</span>
    </Link>
  )
}

// One upcoming race row.
function UpcomingRow({ race, onEdit, onDone, onDelete }) {
  return (
    <div className="flex flex-col gap-3 rounded-[12px] border border-border bg-surface p-3.5 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-bold text-foreground">{race.name}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          <span>{formatDate(race.race_date)}</span>
          {race.distance_km != null && <span className="tabular-nums">{race.distance_km} km</span>}
          {race.location && (
            <span className="inline-flex items-center gap-0.5">
              <MapPin className="h-3 w-3" />
              {race.location}
            </span>
          )}
        </div>
      </div>

      <div className="text-sm sm:w-[150px]">
        <Countdown race={race} />
      </div>

      <div className="flex items-center gap-4 sm:w-[150px]">
        {race.target_time_s != null && (
          <div className="text-xs tabular-nums">
            <div className="font-semibold text-foreground">{formatDuration(race.target_time_s)}</div>
            {race.target_pace && <div className="text-2xs text-faint">{race.target_pace}</div>}
          </div>
        )}
        <ShoeChip shoe={race.planned_shoe} />
      </div>

      <div className="flex items-center gap-1 sm:justify-end">
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onDone(race)} title="Mark complete">
          <Check className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onEdit(race)} title="Edit">
          <Pencil className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-destructive"
          onClick={() => onDelete(race)}
          title="Delete"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

// Delta of result vs target for a completed race.
function ResultDelta({ race }) {
  if (race.result_time_s == null || race.target_time_s == null) return null
  const delta = race.result_time_s - race.target_time_s
  const faster = delta < 0
  return (
    <span className={cn('tabular-nums', faster ? 'text-primary' : 'text-warning')}>
      {faster ? '−' : '+'}
      {formatDuration(Math.abs(delta))} vs target
    </span>
  )
}

function PastRow({ race }) {
  const label = race.status === 'skipped' ? 'Skipped' : null
  // T7: a completed race linked to its Activity deep-links to the run's full stats.
  const Wrapper = race.activity_id
    ? ({ children }) => (
        <Link
          to={`/activities/${race.activity_id}`}
          className="focus-ring flex items-center justify-between gap-3 rounded-[10px] border border-border/60 bg-surface/60 px-3.5 py-2.5 text-xs transition-colors hover:border-primary/40 hover:bg-surface"
          title="Open activity"
        >
          {children}
        </Link>
      )
    : ({ children }) => (
        <div className="flex items-center justify-between gap-3 rounded-[10px] border border-border/60 bg-surface/60 px-3.5 py-2.5 text-xs">
          {children}
        </div>
      )
  return (
    <Wrapper>
      <div className="min-w-0">
        <span className="font-semibold text-foreground">{race.name}</span>
        <span className="ml-2 text-faint">{formatDate(race.race_date)}</span>
      </div>
      <div className="flex items-center gap-3 text-muted-foreground">
        {race.result_time_s != null && (
          <span className="font-semibold text-foreground tabular-nums">
            {formatDuration(race.result_time_s)}
          </span>
        )}
        <ResultDelta race={race} />
        {label && <span className="text-faint">{label}</span>}
      </div>
    </Wrapper>
  )
}

/**
 * Planned races card — sits above Trends on /training because the next race is
 * the most time-sensitive thing on the page. Upcoming races soonest-first,
 * past races collapsed below.
 */
export default function PlannedRacesCard() {
  const races = useRaces()
  const shoes = useOwnedShoes()
  const createRace = useCreateRace()
  const updateRace = useUpdateRace()
  const deleteRace = useDeleteRace()
  const { toast } = useToast()

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [doneRace, setDoneRace] = useState(null)
  const [resultTime, setResultTime] = useState('')
  const [deleting, setDeleting] = useState(null)
  const [pastOpen, setPastOpen] = useState(false)

  const { upcoming, past } = useMemo(() => {
    const list = races.data || []
    const up = list.filter((r) => r.status === 'planned' && r.days_remaining >= 0)
    const pa = list
      .filter((r) => !(r.status === 'planned' && r.days_remaining >= 0))
      .sort((a, b) => new Date(b.race_date) - new Date(a.race_date)) // most recent past first
    return { upcoming: up, past: pa }
  }, [races.data])

  const openAdd = () => { setEditing(null); setFormOpen(true) }
  const openEdit = (race) => { setEditing(race); setFormOpen(true) }

  const submitForm = (payload) => {
    const onDone = () => {
      setFormOpen(false)
      toast({ variant: 'success', title: editing ? 'Race updated' : 'Race added' })
    }
    const onError = (e) =>
      toast({ variant: 'destructive', title: 'Could not save', description: e?.message })
    if (editing) updateRace.mutate({ id: editing.id, data: payload }, { onSuccess: onDone, onError })
    else createRace.mutate(payload, { onSuccess: onDone, onError })
  }

  const confirmDone = () => {
    const secs = parseDuration(resultTime)
    updateRace.mutate(
      { id: doneRace.id, data: { status: 'completed', result_time_s: secs || null } },
      {
        onSuccess: () => {
          setDoneRace(null)
          setResultTime('')
          toast({ variant: 'success', title: 'Race completed 🎉' })
        },
        onError: (e) => toast({ variant: 'destructive', title: 'Could not save', description: e?.message }),
      }
    )
  }

  const confirmDelete = () => {
    deleteRace.mutate(deleting.id, {
      onSuccess: () => { setDeleting(null); toast({ title: 'Race removed' }) },
      onError: (e) => toast({ variant: 'destructive', title: 'Could not delete', description: e?.message }),
    })
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2.5">
          <Flag className="h-4 w-4 text-primary" />
          <span className="font-heading text-md-plus font-bold text-foreground">Races</span>
        </div>
        <Button size="sm" variant="outline" onClick={openAdd}>
          <Plus className="h-4 w-4" /> Add race
        </Button>
      </div>

      <div className="p-4">
        {races.isLoading ? (
          <div className="h-16 animate-pulse rounded-[12px] bg-muted" />
        ) : upcoming.length === 0 && past.length === 0 ? (
          <p className="py-2 text-center text-sm text-muted-foreground">
            No races planned —{' '}
            <button onClick={openAdd} className="focus-ring rounded font-semibold text-primary hover:underline">
              add one
            </button>
          </p>
        ) : (
          <div className="space-y-2.5">
            {upcoming.map((race) => (
              <UpcomingRow
                key={race.id}
                race={race}
                onEdit={openEdit}
                onDone={(r) => { setDoneRace(r); setResultTime('') }}
                onDelete={setDeleting}
              />
            ))}

            {upcoming.length === 0 && (
              <p className="py-1 text-sm text-muted-foreground">No upcoming races.</p>
            )}

            {past.length > 0 && (
              <div className="pt-1">
                <button
                  type="button"
                  onClick={() => setPastOpen((o) => !o)}
                  className="focus-ring flex items-center gap-1.5 rounded text-2xs font-bold uppercase tracking-[0.08em] text-faint hover:text-muted-foreground"
                  aria-expanded={pastOpen}
                >
                  <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', !pastOpen && '-rotate-90')} />
                  Past races · {past.length}
                </button>
                {pastOpen && (
                  <div className="mt-2 space-y-1.5">
                    {past.map((race) => <PastRow key={race.id} race={race} />)}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Add / edit dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit race' : 'Add a race'}</DialogTitle>
            <DialogDescription>
              {editing ? 'Update the details for this race.' : 'Plan a race to train toward.'}
            </DialogDescription>
          </DialogHeader>
          <RaceForm
            initial={editing}
            shoes={shoes.data || []}
            onSubmit={submitForm}
            onCancel={() => setFormOpen(false)}
            submitting={createRace.isPending || updateRace.isPending}
          />
        </DialogContent>
      </Dialog>

      {/* Mark complete dialog */}
      <Dialog open={!!doneRace} onOpenChange={(o) => !o && setDoneRace(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Mark complete</DialogTitle>
            <DialogDescription>
              {doneRace?.name} — enter your finish time to see how you did against target.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label>Result time</Label>
            <Input
              value={resultTime}
              onChange={(e) => setResultTime(e.target.value)}
              placeholder="3:12:45"
              autoFocus
            />
            {doneRace?.target_time_s != null && (
              <p className="text-xs text-faint">Target was {formatDuration(doneRace.target_time_s)}.</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDoneRace(null)}>Cancel</Button>
            <Button onClick={confirmDone} disabled={updateRace.isPending}>Mark complete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove race?</DialogTitle>
            <DialogDescription>
              “{deleting?.name}” will be permanently removed. This can’t be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(null)}>Cancel</Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={deleteRace.isPending}>
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
