import { useState } from 'react'
import { ShieldCheck, LogOut } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { useToast } from '@/components/ui/toast'
import { ErrorState } from '@/components/StatusViews'
import { useAuthSecurity, useSignOutEverywhere } from '@/hooks/useApi'

// One read-only status line (same shape as SettingsSync's StatRow): stacks on
// narrow screens, label left / value right otherwise.
function StatRow({ label, children }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 text-right font-medium text-foreground tabular-nums">{children}</span>
    </div>
  )
}

/**
 * Settings → Security (R9.2). Shows how many browser sessions are live and
 * whether the Claude connector holds a token, with a confirmed "Sign out
 * everywhere" that revokes both. On success the hook drops the app to the
 * login view, so this page never has to handle the post-success state.
 */
export default function SettingsSecurity() {
  const { toast } = useToast()
  const security = useAuthSecurity()
  const signOut = useSignOutEverywhere()
  const [confirmOpen, setConfirmOpen] = useState(false)

  const doSignOut = () => {
    signOut.mutate(undefined, {
      onError: (err) => {
        setConfirmOpen(false)
        toast({
          variant: 'destructive',
          title: 'Could not sign out everywhere',
          description: err?.message || 'Something went wrong. Try again.',
        })
      },
    })
  }

  const data = security.data
  const n = data?.active_sessions ?? 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck className="h-4 w-4 text-accent-foreground" />
          Security
        </CardTitle>
        <CardDescription>Where you are signed in, and a way to end it all at once.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {security.isError ? (
          <ErrorState error={security.error} onRetry={() => security.refetch()} />
        ) : security.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-full" />
          </div>
        ) : (
          <div className="divide-y divide-border">
            <StatRow label="Signed in on">{n} {n === 1 ? 'device' : 'devices'}</StatRow>
            <StatRow label="Claude connector">
              <Badge variant={data?.connector_connected ? 'success' : 'secondary'}>
                {data?.connector_connected ? 'Connected' : 'Not connected'}
              </Badge>
            </StatRow>
          </div>
        )}

        <p className="text-sm text-muted-foreground">
          Signing out everywhere ends every browser session, including this one, and disconnects the Claude
          connector. The Desktop app's token is not affected.
        </p>

        <Button variant="destructive" onClick={() => setConfirmOpen(true)}>
          <LogOut className="mr-2 h-4 w-4" />
          Sign out everywhere
        </Button>
      </CardContent>

      <Dialog open={confirmOpen} onOpenChange={(o) => !signOut.isPending && setConfirmOpen(o)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Sign out everywhere?</DialogTitle>
            <DialogDescription>
              You will need to sign in again on every device and reconnect the Claude connector.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={signOut.isPending}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={doSignOut} disabled={signOut.isPending}>
              {signOut.isPending ? 'Signing out…' : 'Sign out everywhere'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
