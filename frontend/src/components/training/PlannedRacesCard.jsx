import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Flag, Plus, Pencil, Trash2, Check, Footprints, MapPin, Link2, Ban } from 'lucide-react'
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
  useLinkRaceActivity,
  useActivities,
} from '@/hooks/useApi'
import { formatDate, formatDuration, parseDuration, cn } from '@/lib/utils'

const URGENT_DAYS = 14
const VISIBLE_LIMIT = 2

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

/**
 * A past race. Planned races still open past their date (the prune kept them
 * because a run exists that day — R8.3) get Link run / Skipped. A completed
 * race with no run attached can be linked too, so it counts as a Race PB
 * (R8.1). Every real race row can be deleted. Activity-synthesized rows stay
 * deep-link only.
 */
function PastRow({ race, onLink, onSkip, onDelete }) {
  const unresolved = race.status === 'planned'
  const label = race.status === 'skipped' ? 'Skipped' : unresolved ? 'Not marked' : null
  const body = (
    <>
      <div className="min-w-0">
        <span className="font-semibold text-foreground">{race.name}</span>
        <span className="ml-2 text-faint">{formatDate(race.race_date)}</span>
      </div>
      <div className="flex shrink-0 items-center gap-3 text-muted-foreground">
        {race.result_time_s != null && (
          <span className="font-semibold text-foreground tabular-nums">
            {formatDuration(race.result_time_s)}
          </span>
        )}
        <ResultDelta race={race} />
        {label && <span className={unresolved ? 'text-warning' : 'text-faint'}>{label}</span>}
      </div>
    </>
  )
  const bodyClass = 'flex min-w-0 flex-1 items-center justify-between gap-3 px-3.5 py-2.5'
  return (
    <div className="flex items-center rounded-[10px] border border-border/60 bg-surface/60 text-xs">
      {race.activity_id ? (
        <Link
          to={`/activities/${race.activity_id}`}
          className={cn(bodyClass, 'focus-ring rounded-[10px] transition-colors hover:bg-surface')}
          title="Open activity"
        >
          {body}
        </Link>
      ) : (
        <div className={bodyClass}>{body}</div>
      )}
      {!race.from_activity && (
        <div className="flex shrink-0 items-center pr-1.5">
          {race.activity_id == null && race.status !== 'skipped' && (
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onLink(race)} title="Link the run">
              <Link2 className="h-4 w-4" />
            </Button>
          )}
          {unresolved && (
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onSkip(race)} title="Mark skipped">
              <Ban className="h-4 w-4" />
            </Button>
          )}
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
      )}
    </div>
  )
}

/** Runs logged on the race's date — mounted only while the link dialog is open. */
function RunPicker({ race, onPick, picking }) {
  const runs = useActivities({ date_from: race.race_date, date_to: race.race_date })
  if (runs.isLoading) return <div className="h-12 animate-pulse rounded-[10px] bg-muted" />
  const list = (runs.data || []).filter((a) => a.activity_id != null)
  if (list.length === 0)
    return (
      <p className="text-sm text-muted-foreground">
        No runs are logged on this date. If you didn't race, mark it skipped instead.
      </p>
    )
  return (
    <div className="space-y-1.5">
      {list.map((a) => (
        <button
          key={a.activity_id}
          type="button"
          disabled={picking}
          onClick={() => onPick(a.activity_id)}
          className="focus-ring flex w-full items-center justify-between gap-3 rounded-[10px] border border-border bg-surface px-3.5 py-2.5 text-left text-sm transition-colors hover:border-primary/40 disabled:opacity-60"
        >
          <span className="min-w-0 truncate font-semibold text-foreground">{a.name || 'Run'}</span>
          <span className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground tabular-nums">
            <span>{a.distance_km} km</span>
            {a.moving_time_s != null && <span>{formatDuration(a.moving_time_s)}</span>}
          </span>
        </button>
      ))}
    </div>
  )
}

function ViewAllButton({ count, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="focus-ring rounded text-2xs font-bold uppercase tracking-[0.08em] text-faint hover:text-muted-foreground"
    >
      View all · {count}
    </button>
  )
}

/**
 * Planned races card — Races · Upcoming (max 2 inline, overflow in dialog) +
 * Past (max 2 inline, overflow in dialog). Fixed card height like RecordsCard.
 * Past races include both PlannedRace completed/skipped rows and Activity rows
 * tagged 'Race'/'Parkrun' (from_activity=true — deep-link only, no CRUD).
 */
export default function PlannedRacesCard() {
  const races = useRaces()
  const shoes = useOwnedShoes()
  const createRace = useCreateRace()
  const updateRace = useUpdateRace()
  const deleteRace = useDeleteRace()
  const linkRace = useLinkRaceActivity()
  const { toast } = useToast()

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [doneRace, setDoneRace] = useState(null)
  const [resultTime, setResultTime] = useState('')
  const [deleting, setDeleting] = useState(null)
  const [linking, setLinking] = useState(null)
  const [upcomingAllOpen, setUpcomingAllOpen] = useState(false)
  const [pastAllOpen, setPastAllOpen] = useState(false)

  const { upcoming, past } = useMemo(() => {
    const list = races.data || []
    const up = list.filter((r) => r.status === 'planned' && r.days_remaining >= 0)
    const pa = list
      .filter((r) => !(r.status === 'planned' && r.days_remaining >= 0))
      .sort((a, b) => new Date(b.race_date) - new Date(a.race_date))
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
          toast({ variant: 'success', title: 'Race completed' })
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

  const markSkipped = (race) => {
    updateRace.mutate(
      { id: race.id, data: { status: 'skipped' } },
      {
        onSuccess: () => toast({ title: 'Marked skipped' }),
        onError: (e) => toast({ variant: 'destructive', title: 'Could not save', description: e?.message }),
      }
    )
  }

  const confirmLink = (activityId) => {
    linkRace.mutate(
      { id: linking.id, activityId },
      {
        onSuccess: () => { setLinking(null); toast({ variant: 'success', title: 'Race linked to run' }) },
        onError: (e) => toast({ variant: 'destructive', title: 'Could not link', description: e?.message }),
      }
    )
  }

  const pastHandlers = (closeDialog) => ({
    onLink: (r) => { closeDialog?.(); setLinking(r) },
    onSkip: markSkipped,
    onDelete: (r) => { closeDialog?.(); setDeleting(r) },
  })

  const visibleUpcoming = upcoming.slice(0, VISIBLE_LIMIT)
  const visiblePast = past.slice(0, VISIBLE_LIMIT)

  return (
    <div className="rounded-2xl border border-border bg-card">
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
          <div className="space-y-2">
            <div className="h-16 animate-pulse rounded-[12px] bg-muted" />
            <div className="h-8 animate-pulse rounded-[10px] bg-muted" />
          </div>
        ) : upcoming.length === 0 && past.length === 0 ? (
          <p className="py-2 text-center text-sm text-muted-foreground">
            No races planned —{' '}
            <button onClick={openAdd} className="focus-ring rounded font-semibold text-primary hover:underline">
              add one
            </button>
          </p>
        ) : (
          <div className="space-y-3">
            {/* Upcoming */}
            <div className="space-y-2">
              {visibleUpcoming.length > 0 ? (
                visibleUpcoming.map((race) => (
                  <UpcomingRow
                    key={race.id}
                    race={race}
                    onEdit={openEdit}
                    onDone={(r) => { setDoneRace(r); setResultTime('') }}
                    onDelete={setDeleting}
                  />
                ))
              ) : (
                <p className="py-1 text-sm text-muted-foreground">No upcoming races.</p>
              )}
              {upcoming.length > VISIBLE_LIMIT && (
                <ViewAllButton count={upcoming.length} onClick={() => setUpcomingAllOpen(true)} />
              )}
            </div>

            {/* Past */}
            {past.length > 0 && (
              <div className="space-y-1.5 border-t border-border/50 pt-3">
                <div className="flex items-center justify-between pb-1">
                  <span className="text-2xs font-bold uppercase tracking-[0.08em] text-faint">
                    Past races · {past.length}
                  </span>
                  {past.length > VISIBLE_LIMIT && (
                    <ViewAllButton count={past.length} onClick={() => setPastAllOpen(true)} />
                  )}
                </div>
                {visiblePast.map((race) => <PastRow key={race.id} race={race} {...pastHandlers()} />)}
              </div>
            )}
          </div>
        )}
      </div>

      {/* All upcoming dialog */}
      <Dialog open={upcomingAllOpen} onOpenChange={setUpcomingAllOpen}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>All upcoming races</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            {upcoming.map((race) => (
              <UpcomingRow
                key={race.id}
                race={race}
                onEdit={(r) => { setUpcomingAllOpen(false); openEdit(r) }}
                onDone={(r) => { setUpcomingAllOpen(false); setDoneRace(r); setResultTime('') }}
                onDelete={(r) => { setUpcomingAllOpen(false); setDeleting(r) }}
              />
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* All past dialog */}
      <Dialog open={pastAllOpen} onOpenChange={setPastAllOpen}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>All past races</DialogTitle>
          </DialogHeader>
          <div className="space-y-1.5">
            {past.map((race) => (
              <PastRow key={race.id} race={race} {...pastHandlers(() => setPastAllOpen(false))} />
            ))}
          </div>
        </DialogContent>
      </Dialog>

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

      {/* Link a past race to the run that was the race (R8.3) */}
      <Dialog open={!!linking} onOpenChange={(o) => !o && setLinking(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Link the run</DialogTitle>
            <DialogDescription>
              Which run on {linking && formatDate(linking.race_date)} was {linking?.name}? Its elapsed time becomes the result{linking?.result_time_s != null ? ', replacing the time entered' : ''}, and it counts as a Race PB.
            </DialogDescription>
          </DialogHeader>
          {linking && <RunPicker race={linking} onPick={confirmLink} picking={linkRace.isPending} />}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setLinking(null)}>Cancel</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove race?</DialogTitle>
            <DialogDescription>
              "{deleting?.name}" will be permanently removed. This can't be undone.
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
    </div>
  )
}
