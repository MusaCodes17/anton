import { RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast'
import { useOnline } from '@/hooks/useOnline'
import { useCorosStatus, useSyncCoros } from '@/hooks/useApi'

const OFFLINE_MSG = "You're offline — this needs a connection."

/**
 * "Sync runs" button — triggers a manual COROS sync (POST /api/coros/sync) and
 * reports the outcome as a toast. Shared by the Training and New runs page
 * headers so both surfaces run the same sync and show the same feedback.
 * Renders nothing unless COROS is connected: a reconnect prompt lives on the
 * page itself, not in the header.
 */
export default function SyncRunsButton({ label = 'Sync runs' }) {
  const status = useCorosStatus()
  const sync = useSyncCoros()
  const { toast } = useToast()
  const { online } = useOnline()

  if (status.data?.status !== 'connected') return null

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
    <Button onClick={syncNow}
      disabled={!online || sync.isPending} title={!online ? OFFLINE_MSG : undefined}>
      <RefreshCw className={sync.isPending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} /> {label}
    </Button>
  )
}
