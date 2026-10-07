import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Watch, RefreshCw, Check, X, Heart, AlertTriangle } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { ErrorState } from '@/components/StatusViews'
import { useToast } from '@/components/ui/toast'
import { useOnline } from '@/hooks/useOnline'
import {
  useCorosPending, useCorosStatus, useOwnedShoes, useSyncCoros,
  useConfirmPendingRun, useDismissPendingRun,
} from '@/hooks/useApi'
import { formatDate, formatRelativeTime } from '@/lib/utils'

const OFFLINE_MSG = "You're offline — this needs a connection."

/**
 * New runs — the COROS inbox (R5.7 §6). The poller queues runs server-side;
 * here the runner confirms each against live state (C9). The shoe picker is
 * pre-filled with the server's suggestion and changeable with one tap. Confirm
 * and Dismiss are online-only (RA2.2 §4: disabled with the offline message, no
 * queue); the list itself is a GET and renders from cache with a "last synced"
 * label.
 */
export default function NewRuns() {
  const pending = useCorosPending()
  const status = useCorosStatus()
  const shoes = useOwnedShoes()
  const sync = useSyncCoros()
  const { toast } = useToast()
  const { online } = useOnline()

  const activeShoes = (shoes.data ?? []).filter((s) => s.status === 'active')
  const runs = pending.data?.runs ?? []
  const lastSync = pending.data?.last_success_at
  const conn = status.data?.status

  function syncNow() {
    sync.mutate(undefined, {
      onSuccess: (r) =>
        toast({
          title: r.ok ? 'Synced with COROS' : 'Sync finished with problems',
          description: r.ok
            ? r.queued ? `${r.queued} new run${r.queued === 1 ? '' : 's'} found.` : 'No new runs.'
            : r.errors?.[0],
          variant: r.ok ? undefined : 'destructive',
        }),
      onError: (err) =>
        toast({ variant: 'destructive', title: 'Sync failed', description: err.message }),
    })
  }

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="COROS" title="New runs" count={runs.length}>
        {conn === 'connected' && (
          <Button variant="outline" onClick={syncNow}
            disabled={!online || sync.isPending} title={!online ? OFFLINE_MSG : undefined}>
            <RefreshCw className={sync.isPending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} /> Sync now
          </Button>
        )}
      </PageHeader>

      {conn && conn !== 'connected' && (
        <div className="flex items-start gap-3 rounded-2xl border border-border bg-card p-4 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div className="space-y-1">
            <p className="font-semibold text-foreground">
              {conn === 'reauth_required' ? 'COROS needs to be reconnected' : 'COROS is not connected'}
            </p>
            <p className="text-muted-foreground">
              New runs only arrive while connected.{' '}
              <Link to="/settings/sync" className="font-semibold text-primary underline-offset-4 hover:underline">
                Open sync settings
              </Link>
            </p>
          </div>
        </div>
      )}

      {pending.isError ? (
        <ErrorState error={pending.error} onRetry={pending.refetch} />
      ) : pending.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-36 w-full rounded-2xl" />
          <Skeleton className="h-36 w-full rounded-2xl" />
        </div>
      ) : runs.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-8 text-center">
          <Watch className="mx-auto h-8 w-8 text-faint" />
          <p className="mt-3 font-heading font-bold text-foreground">You're all caught up</p>
          <p className="mt-1 text-sm text-muted-foreground">
            New runs from your watch show up here within about 15 minutes of syncing to COROS.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => (
            <PendingRunCard key={run.id} run={run} activeShoes={activeShoes} online={online} />
          ))}
        </div>
      )}

      <p className="text-xs text-faint">
        {lastSync ? `Last synced ${formatRelativeTime(lastSync)}.` : 'Not synced yet.'}
        {!online && ' Showing the last loaded list.'}
      </p>
    </div>
  )
}

function fmtDuration(s) {
  if (s == null) return null
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`
}

function PendingRunCard({ run, activeShoes, online }) {
  const { toast } = useToast()
  const confirm = useConfirmPendingRun()
  const dismiss = useDismissPendingRun()
  const suggestedActive = activeShoes.some((s) => s.id === run.suggested_shoe_id)
  // `picked` is null until the runner chooses; until then the server's suggestion is the
  // value. Derived (not seeded into state) because the shoe list loads after first render.
  const [picked, setPicked] = useState(null)
  const shoeId = picked ?? (suggestedActive ? String(run.suggested_shoe_id) : '')
  const [dismissOpen, setDismissOpen] = useState(false)
  const busy = confirm.isPending || dismiss.isPending

  function onConfirm() {
    confirm.mutate(
      { id: run.id, owned_shoe_id: Number(shoeId) },
      {
        onSuccess: (r) => {
          if (r.already_logged) {
            toast({ title: 'Already logged', description: 'This run was already on a shoe.' })
            return
          }
          const extra = [
            r.threshold_crossed ? `${r.shoe.brand} ${r.shoe.model} passed ${r.threshold_crossed} km — ${r.threshold_message}.` : null,
            r.checkpoint_reached ? `Checkpoint reached: ${r.checkpoint_km} km.` : null,
          ].filter(Boolean)
          toast({
            title: `Logged to ${r.shoe.brand} ${r.shoe.model}`,
            description: [`+${run.distance_km.toFixed(1)} km → ${r.shoe.new_mileage} km total.`, ...extra].join(' '),
          })
        },
        onError: (err) => toast({ variant: 'destructive', title: 'Could not log run', description: err.message }),
      }
    )
  }

  function onDismiss() {
    dismiss.mutate(run.id, {
      onSuccess: () => {
        setDismissOpen(false)
        toast({ title: 'Run dismissed', description: 'It will not count toward any shoe.' })
      },
      onError: (err) => toast({ variant: 'destructive', title: 'Could not dismiss', description: err.message }),
    })
  }

  return (
    <article className="rounded-2xl border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-2xs font-bold uppercase tracking-[0.08em] text-faint">
            {formatDate(run.run_date)}
          </div>
          <div className="mt-1 font-heading text-2xl font-extrabold tabular-nums text-foreground">
            {run.distance_km.toFixed(2)}
            <span className="ml-1 text-sm font-semibold text-faint">km</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1 text-sm tabular-nums text-muted-foreground">
          <span>{run.avg_pace}</span>
          {run.moving_time_s != null && <span>{fmtDuration(run.moving_time_s)}</span>}
          {run.avg_hr != null && (
            <span className="inline-flex items-center gap-1">
              <Heart className="h-3.5 w-3.5" />{run.avg_hr}
            </span>
          )}
        </div>
      </div>

      <div className="mt-3 space-y-1.5">
        <Select value={shoeId} onValueChange={setPicked} disabled={busy}>
          <SelectTrigger aria-label="Shoe">
            <SelectValue placeholder="Choose a shoe" />
          </SelectTrigger>
          <SelectContent>
            {activeShoes.map((s) => (
              <SelectItem key={s.id} value={String(s.id)}>
                {s.nickname || `${s.brand} ${s.model}`} · {Math.round(s.current_mileage)} km
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {run.suggestion_reason && (
          <div className="flex items-start gap-1.5 text-xs text-faint">
            {suggestedActive && String(run.suggested_shoe_id) === shoeId && (
              <Badge variant="secondary" className="shrink-0">Suggested</Badge>
            )}
            <span>{run.suggestion_reason}</span>
          </div>
        )}
      </div>

      <div className="mt-3 flex gap-2">
        <Button className="flex-1" onClick={onConfirm}
          disabled={!online || !shoeId || busy} title={!online ? OFFLINE_MSG : undefined}>
          <Check className="h-4 w-4" /> {confirm.isPending ? 'Logging…' : 'Confirm'}
        </Button>
        <Button variant="outline" onClick={() => setDismissOpen(true)}
          disabled={!online || busy} title={!online ? OFFLINE_MSG : undefined}>
          <X className="h-4 w-4" /> Dismiss
        </Button>
      </div>
      {!online && <p className="mt-2 text-xs text-faint">{OFFLINE_MSG}</p>}

      <Dialog open={dismissOpen} onOpenChange={setDismissOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Dismiss this run?</DialogTitle>
            <DialogDescription>
              {formatDate(run.run_date)} · {run.distance_km.toFixed(2)} km won't be added to any shoe,
              and COROS won't offer it again.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDismissOpen(false)}>Keep it</Button>
            <Button variant="destructive" onClick={onDismiss} disabled={dismiss.isPending}>Dismiss run</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </article>
  )
}
