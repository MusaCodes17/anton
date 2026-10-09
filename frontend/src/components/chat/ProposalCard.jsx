import { useEffect, useState } from 'react'
import { Check, Loader2, Pencil, ShieldCheck, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import LogRunDialog from '@/components/LogRunDialog'
import { useCancelProposal, useChatProposal, useConfirmProposal } from '@/hooks/useApi'
import { useOnline } from '@/hooks/useOnline'
import { cn } from '@/lib/utils'

const OFFLINE_MSG = "You're offline — this needs a connection."

/**
 * A write the assistant proposed (R7.2, decision C12). The server holds the
 * exact tool call; Confirm sends only the proposal id, so what runs is what
 * this card shows. Cancel runs nothing. Edit (log-run only) opens the app's
 * own form prefilled instead.
 *
 * `onResolved(proposal)` reports the new state up to useChatStream, which
 * stores it on the message and sends the decision back to the model.
 * `busy` is true while a reply is streaming: no decisions mid-turn.
 */
export default function ProposalCard({ proposal, onResolved, busy }) {
  const { online } = useOnline()
  const confirm = useConfirmProposal()
  const cancel = useCancelProposal()
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState(null)

  // A long tool (a full scrape) comes back "executing"; poll until it's done.
  const executing = proposal.status === 'executing'
  const poll = useChatProposal(proposal.id, { enabled: executing })
  useEffect(() => {
    if (executing && poll.data && poll.data.status !== 'executing') onResolved(poll.data)
    if (executing && poll.error?.status === 404) onResolved({ id: proposal.id, status: 'expired' })
  }, [executing, poll.data, poll.error])

  // 404 = the server no longer holds it (restart or TTL): expire quietly, no
  // model turn. 409 = it was already decided elsewhere: show that state.
  const handleFailure = (err) => {
    if (err?.status === 404) onResolved({ id: proposal.id, status: 'expired' })
    else if (err?.status === 409) setError(err.message)
    else setError(err?.message || 'Something went wrong.')
  }

  const pending = proposal.status === 'pending'
  const deciding = confirm.isPending || cancel.isPending
  const disabled = !pending || deciding || busy || !online

  const onConfirm = () => {
    setError(null)
    // Don't wait for onSuccess to lock the card: a second tap is ignored here
    // and is idempotent on the server anyway.
    confirm.mutate(proposal.id, { onSuccess: onResolved, onError: handleFailure })
  }
  const onCancel = () => {
    setError(null)
    cancel.mutate({ id: proposal.id }, { onSuccess: onResolved, onError: handleFailure })
  }
  const onLogged = (payload) => {
    setEditing(false)
    cancel.mutate({ id: proposal.id, editedValues: payload }, { onSuccess: onResolved, onError: handleFailure })
  }

  if (!pending && !executing) return <ResolvedLine proposal={proposal} />

  const canEdit = proposal.edit?.kind === 'log_run'

  return (
    <div className="mt-3 rounded-[14px] border border-edge bg-card p-3.5">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 shrink-0 text-primary" />
        <span className="text-2xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">
          Confirm to apply
        </span>
      </div>
      <p className="mt-1.5 font-heading text-md-plus font-extrabold text-foreground">{proposal.title}</p>

      <dl className="mt-2.5 space-y-1.5">
        {proposal.fields.map((f) => (
          <div key={f.label} className="grid grid-cols-[96px_1fr] gap-3 text-sm">
            <dt className="text-muted-foreground">{f.label}</dt>
            <dd className="min-w-0 break-words font-mono text-sm-plus text-foreground">{f.value}</dd>
          </div>
        ))}
      </dl>

      {executing ? (
        <p className="mt-3.5 flex h-11 items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Running…
        </p>
      ) : (
        <div className="mt-3.5 flex flex-wrap gap-2">
          <Button
            className="h-11 flex-1 sm:flex-none sm:px-6"
            onClick={onConfirm}
            disabled={disabled}
            title={!online ? OFFLINE_MSG : undefined}
          >
            {confirm.isPending ? <Loader2 className="animate-spin" /> : <Check />}
            Confirm
          </Button>
          {canEdit && (
            <Button
              variant="outline"
              className="h-11"
              onClick={() => setEditing(true)}
              disabled={disabled}
              title={!online ? OFFLINE_MSG : undefined}
            >
              <Pencil /> Edit
            </Button>
          )}
          <Button variant="ghost" className="h-11" onClick={onCancel} disabled={!pending || deciding || busy}>
            Cancel
          </Button>
        </div>
      )}
      {!online && pending && <p className="mt-2 text-xs text-muted-foreground">{OFFLINE_MSG}</p>}
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}

      {canEdit && (
        <LogRunDialog
          shoe={proposal.edit.shoe}
          open={editing}
          onOpenChange={setEditing}
          initialValues={proposal.edit.values}
          onLogged={onLogged}
        />
      )}
    </div>
  )
}

// After a decision the card collapses to one line, so the thread reads as a
// record ("Log run — done") rather than a stack of stale forms.
function ResolvedLine({ proposal }) {
  const { status, result, title } = proposal
  const failed = status === 'done' && result?.success === false
  const summary = proposal.fields?.slice(0, 2).map((f) => f.value).join(' · ')

  let icon = <Check className="h-3.5 w-3.5 text-primary" strokeWidth={3} />
  let text = `${title} — done`
  if (failed) {
    icon = <X className="h-3.5 w-3.5 text-destructive" strokeWidth={3} />
    text = `${title} — failed${result?.error ? `: ${result.error}` : ''}`
  } else if (status === 'cancelled') {
    icon = <X className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={3} />
    text = proposal.edited_values || proposal.followup_message?.includes('chose Edit')
      ? `${title} — done in the form instead`
      : `${title} — cancelled, nothing changed`
  } else if (status === 'expired') {
    icon = <X className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={3} />
    text = `${title} — expired, ask again`
  }

  return (
    <div
      className={cn(
        'mt-3 flex min-h-9 items-start gap-2 rounded-[10px] border border-divider px-3 py-2 font-mono text-xs',
        failed ? 'text-destructive' : 'text-muted-foreground'
      )}
    >
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span className="min-w-0 break-words">
        {text}
        {summary && status !== 'expired' && !failed && <span className="text-faint"> · {summary}</span>}
      </span>
    </div>
  )
}
