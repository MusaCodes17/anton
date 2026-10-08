import { useEffect, useState } from 'react'
import { Ruler } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast'
import { usePreferences, useUpdatePreferences } from '@/hooks/useApi'

/**
 * R6.3: the runner's shoe size. The server validates it (half sizes, 3–16) and
 * derives each deal's size_fit from it; this card only edits the preference.
 * Empty clears it, which turns every size behaviour off.
 */
export default function SizePreferenceCard() {
  const { toast } = useToast()
  const prefs = usePreferences()
  const update = useUpdatePreferences()
  const [size, setSize] = useState('')
  const [hide, setHide] = useState(false)

  useEffect(() => {
    if (!prefs.data) return
    setSize(prefs.data.preferred_size != null ? String(prefs.data.preferred_size) : '')
    setHide(!!prefs.data.hide_other_sizes)
  }, [prefs.data])

  const onSave = () =>
    update.mutate(
      { preferred_size: size.trim() || null, hide_other_sizes: hide },
      {
        onSuccess: () => {
          update.reset()
          toast({ title: 'Size saved', description: size.trim() ? `Deals now rank for size ${size.trim()}.` : 'Size filter off.' })
        },
      }
    )

  const error = update.error?.response?.data?.detail || update.error?.message

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Ruler className="h-4 w-4 text-accent-foreground" />
          My size
        </CardTitle>
        <CardDescription>
          Deals in your size rank first and the alert digest skips the rest. Leave empty to turn off.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-end gap-3">
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
          <Button onClick={onSave} disabled={update.isPending || prefs.isLoading}>
            Save
          </Button>
        </div>
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="pref-hide" className="text-sm font-medium">
            Hide deals not in my size
          </Label>
          <Switch id="pref-hide" checked={hide} onCheckedChange={setHide} />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}
