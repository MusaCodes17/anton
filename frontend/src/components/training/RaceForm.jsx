import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { DialogFooter } from '@/components/ui/dialog'
import { formatDuration, parseDuration } from '@/lib/utils'

const NONE = '__none__'

/** Controlled form for creating/editing a planned race. Target time is entered
 *  as "H:MM:SS" / "M:SS" and converted to seconds on submit. */
export default function RaceForm({ initial, shoes = [], onSubmit, onCancel, submitting }) {
  const [values, setValues] = useState(() => ({
    name: initial?.name ?? '',
    race_date: initial?.race_date ?? '',
    distance_km: initial?.distance_km != null ? String(initial.distance_km) : '',
    target_time: initial?.target_time_s != null ? formatDuration(initial.target_time_s) : '',
    planned_shoe_id: initial?.planned_shoe_id != null ? String(initial.planned_shoe_id) : NONE,
    location: initial?.location ?? '',
    notes: initial?.notes ?? '',
  }))
  const [errors, setErrors] = useState({})

  const set = (key) => (e) => setValues((v) => ({ ...v, [key]: e.target.value }))

  const validate = () => {
    const next = {}
    if (!values.name.trim()) next.name = 'Name is required'
    if (!values.race_date) next.race_date = 'Race date is required'
    if (values.target_time && parseDuration(values.target_time) == null)
      next.target_time = 'Use H:MM:SS or M:SS'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!validate()) return
    const dist = parseFloat(values.distance_km)
    onSubmit({
      name: values.name.trim(),
      race_date: values.race_date,
      distance_km: Number.isNaN(dist) ? null : dist,
      target_time_s: values.target_time ? parseDuration(values.target_time) : null,
      planned_shoe_id: values.planned_shoe_id === NONE ? null : Number(values.planned_shoe_id),
      location: values.location.trim() || null,
      notes: values.notes.trim() || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <Label>Race name</Label>
        <Input value={values.name} onChange={set('name')} placeholder="Chicago Marathon" />
        {errors.name && <p className="text-xs text-destructive">{errors.name}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Date</Label>
          <Input type="date" value={values.race_date} onChange={set('race_date')} />
          {errors.race_date && <p className="text-xs text-destructive">{errors.race_date}</p>}
        </div>
        <div className="space-y-1.5">
          <Label>Distance (km)</Label>
          <Input type="number" min="0" step="0.001" value={values.distance_km}
            onChange={set('distance_km')} placeholder="42.195" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Target time</Label>
          <Input value={values.target_time} onChange={set('target_time')} placeholder="3:15:00" />
          {errors.target_time && <p className="text-xs text-destructive">{errors.target_time}</p>}
        </div>
        <div className="space-y-1.5">
          <Label>Planned shoe</Label>
          <Select
            value={values.planned_shoe_id}
            onValueChange={(v) => setValues((s) => ({ ...s, planned_shoe_id: v }))}
          >
            <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>None</SelectItem>
              {shoes.map((s) => (
                <SelectItem key={s.id} value={String(s.id)}>
                  {s.nickname || `${s.brand} ${s.model}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>Location</Label>
        <Input value={values.location} onChange={set('location')} placeholder="Chicago, IL" />
      </div>

      <div className="space-y-1.5">
        <Label>Notes</Label>
        <Textarea value={values.notes} onChange={set('notes')} rows={2}
          placeholder="Goal race for the fall block" />
      </div>

      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Saving…' : initial ? 'Save changes' : 'Add race'}
        </Button>
      </DialogFooter>
    </form>
  )
}
