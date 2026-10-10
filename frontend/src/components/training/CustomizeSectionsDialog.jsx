import { useEffect, useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { SECTION_LABELS, TRAINING_SECTIONS } from '@/lib/trainingLayout'

/** Reorder / hide Training sections. Draft is re-copied from `layout` on each open. */
export default function CustomizeSectionsDialog({ open, onOpenChange, layout, onSave, saving }) {
  const [order, setOrder] = useState(layout.order)
  const [hidden, setHidden] = useState(layout.hidden)

  useEffect(() => {
    if (open) { setOrder(layout.order); setHidden(layout.hidden) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const move = (i, d) => {
    const next = [...order]
    ;[next[i], next[i + d]] = [next[i + d], next[i]]
    setOrder(next)
  }
  const visible = order.filter((id) => !hidden.includes(id))
  const toggle = (id, show) =>
    setHidden(show ? hidden.filter((h) => h !== id) : [...hidden, id])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Customize Training</DialogTitle>
          <DialogDescription>Reorder or hide sections. Saved for all your devices.</DialogDescription>
        </DialogHeader>

        <ul className="space-y-2">
          {order.map((id, i) => {
            const isHidden = hidden.includes(id)
            const label = SECTION_LABELS[id]
            return (
              <li
                key={id}
                className="flex items-center gap-2 rounded-[12px] border border-border bg-surface px-2 py-1"
              >
                <div className="flex shrink-0">
                  <Button
                    type="button" variant="ghost" size="icon"
                    className="h-11 w-11" aria-label={`Move ${label} up`}
                    disabled={i === 0} onClick={() => move(i, -1)}
                  >
                    <ChevronUp />
                  </Button>
                  <Button
                    type="button" variant="ghost" size="icon"
                    className="h-11 w-11" aria-label={`Move ${label} down`}
                    disabled={i === order.length - 1} onClick={() => move(i, 1)}
                  >
                    <ChevronDown />
                  </Button>
                </div>
                <span className={'min-w-0 flex-1 truncate text-sm font-semibold ' + (isHidden ? 'text-faint' : 'text-foreground')}>
                  {label}
                </span>
                <Switch
                  checked={!isHidden}
                  onCheckedChange={(v) => toggle(id, v)}
                  disabled={!isHidden && visible.length <= 1}
                  aria-label={`Show ${label}`}
                />
              </li>
            )
          })}
        </ul>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button" variant="ghost" className="sm:mr-auto"
            onClick={() => { setOrder([...TRAINING_SECTIONS]); setHidden([]) }}
          >
            Reset to default
          </Button>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="button" disabled={saving} onClick={() => onSave({ order, hidden })}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
