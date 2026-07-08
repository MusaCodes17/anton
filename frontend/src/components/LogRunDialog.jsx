import { useState } from 'react'
import LogRunForm from '@/components/LogRunForm'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { useToast } from '@/components/ui/toast'
import {
  useLogRun,
  useAddShoeNote,
  useCheckpointPrompts,
  useMarkCheckpointPrompted,
} from '@/hooks/useApi'

/**
 * Log-run dialog shared between the My Shoes list and the shoe detail page.
 * After a successful log, if the run crossed an un-prompted 100km
 * checkpoint, switches to a "how are they feeling?" note prompt instead of
 * closing immediately.
 */
export default function LogRunDialog({ shoe, open, onOpenChange }) {
  const [checkpointKm, setCheckpointKm] = useState(null)
  const [noteBody, setNoteBody] = useState('')
  const logRun = useLogRun()
  const addNote = useAddShoeNote()
  const { toast } = useToast()
  // Checkpoint-prompt state is server-side since R2.6 (was localStorage). The
  // set is fetched once; marking is a mutation that invalidates it.
  const { data: promptedCheckpoints } = useCheckpointPrompts()
  const markCheckpoint = useMarkCheckpointPrompted()

  const hasPromptedCheckpoint = (shoeId, km) =>
    (promptedCheckpoints ?? []).some(
      (p) => p.owned_shoe_id === shoeId && p.checkpoint_km === km
    )

  const close = () => {
    setCheckpointKm(null)
    setNoteBody('')
    onOpenChange(false)
  }

  const handleLogRun = (payload) => {
    logRun.mutate(
      { id: shoe.id, data: payload },
      {
        onSuccess: (data) => {
          toast({ variant: 'success', title: 'Run logged' })
          if (data.checkpoint_reached && !hasPromptedCheckpoint(shoe.id, data.checkpoint_km)) {
            setCheckpointKm(data.checkpoint_km)
          } else {
            close()
          }
        },
        onError: (err) =>
          toast({ variant: 'destructive', title: 'Failed to log run', description: err.message }),
      }
    )
  }

  const skipCheckpoint = () => {
    markCheckpoint.mutate({ ownedShoeId: shoe.id, checkpointKm })
    close()
  }

  const saveCheckpointNote = () => {
    if (!noteBody.trim()) return
    addNote.mutate(
      { id: shoe.id, data: { body: noteBody.trim(), triggered_by: 'checkpoint' } },
      {
        onSuccess: () => {
          markCheckpoint.mutate({ ownedShoeId: shoe.id, checkpointKm })
          toast({ variant: 'success', title: 'Note added' })
          close()
        },
        onError: (err) =>
          toast({ variant: 'destructive', title: 'Failed to save note', description: err.message }),
      }
    )
  }

  if (!shoe) return null

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent>
        {checkpointKm == null ? (
          <>
            <DialogHeader>
              <DialogTitle>Log run — {shoe.nickname || shoe.model}</DialogTitle>
            </DialogHeader>
            <LogRunForm submitting={logRun.isPending} onSubmit={handleLogRun} onCancel={close} />
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Checkpoint reached 🎯</DialogTitle>
              <DialogDescription>
                Your {shoe.nickname || shoe.model} just hit {checkpointKm}km. Add a note about how
                they're feeling?
              </DialogDescription>
            </DialogHeader>
            <Textarea
              value={noteBody}
              onChange={(e) => setNoteBody(e.target.value)}
              placeholder="Still feel fresh, no signs of wear…"
              autoFocus
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={skipCheckpoint}>
                Skip
              </Button>
              <Button type="button" onClick={saveCheckpointNote} disabled={addNote.isPending || !noteBody.trim()}>
                {addNote.isPending ? 'Saving…' : 'Save'}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
