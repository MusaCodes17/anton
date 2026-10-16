import { useEffect, useState } from 'react'
import { Ruler } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { useToast } from '@/components/ui/toast'
import { usePreferences, useUpdatePreferences } from '@/hooks/useApi'

/**
 * R6.3: the runner's shoe size. The server validates it (half sizes, 3–16) and
 * derives each deal's size_fit from it; this button only edits the preference.
 * Empty clears it, which turns every size behaviour off.
 *
 * The edit form lives in a dialog so the Tracked shoes header stays one line of
 * actions. The form re-syncs from prefs each time the dialog opens, so Cancel
 * discards edits.
 */
export default function SizePreferenceButton() {
  const { toast } = useToast()
  const prefs = usePreferences()
  const update = useUpdatePreferences()
  const [open, setOpen] = useState(false)
  const [size, setSize] = useState('')
  const [hide, setHide] = useState(false)

  // Re-sync on open (discards abandoned edits) and when fresh prefs arrive while open.
  useEffect(() => {
    if (!open || !prefs.data) return
    setSize(prefs.data.preferred_size != null ? String(prefs.data.preferred_size) : '')
    setHide(!!prefs.data.hide_other_sizes)
    update.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, prefs.data])

  const onSave = () =>
    update.mutate(
      { preferred_size: size.trim() || null, hide_other_sizes: hide },
      {
        onSuccess: () => {
          update.reset()
          setOpen(false)
          toast({ title: 'Size saved', description: size.trim() ? `Deals now rank for size ${size.trim()}.` : 'Size filter off.' })
        },
      }
    )

  const error = update.error?.message  // api.js already normalises FastAPI errors to a message
  const label = prefs.data?.preferred_size != null ? `Size ${prefs.data.preferred_size}` : 'Set my size'

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} aria-label={label}>
        <Ruler className="h-4 w-4" />
        <span className="hidden sm:inline">{label}</span>
      </Button>

      <Dialog open={open} onOpenChange={(o) => !update.isPending && setOpen(o)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>My size</DialogTitle>
            <DialogDescription>
              Deals in your size rank first and the alert digest skips the rest. Leave empty to turn off.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="pref-size">US size</Label>
              <Input
                id="pref-size"
                inputMode="decimal"
                placeholder="e.g. 10.5"
                className="w-28"
                value={size}
                onChange={(e) => setSize(e.target.value)}
              />
            </div>
            <div className="flex items-center justify-between gap-4">
              <Label htmlFor="pref-hide" className="text-sm font-medium">
                Hide deals not in my size
              </Label>
              <Switch id="pref-hide" checked={hide} onCheckedChange={setHide} />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={update.isPending}>
              Cancel
            </Button>
            <Button onClick={onSave} disabled={update.isPending || prefs.isLoading}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
