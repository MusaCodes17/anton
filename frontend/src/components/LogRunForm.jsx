import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DialogFooter } from '@/components/ui/dialog'

const today = () => new Date().toISOString().slice(0, 10)

export default function LogRunForm({ onSubmit, onCancel, submitting }) {
  const [values, setValues] = useState({ distance_km: '', run_date: today(), notes: '' })
  const [errors, setErrors] = useState({})

  const set = (key) => (e) => setValues((v) => ({ ...v, [key]: e.target.value }))

  const validate = () => {
    const next = {}
    const distance = parseFloat(values.distance_km)
    if (!values.distance_km || Number.isNaN(distance) || distance <= 0)
      next.distance_km = 'Enter a distance greater than 0'
    if (!values.run_date) next.run_date = 'Run date is required'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!validate()) return
    onSubmit({
      distance_km: parseFloat(values.distance_km),
      run_date: values.run_date,
      notes: values.notes.trim() || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Distance (km)" error={errors.distance_km}>
          <Input
            type="number"
            step="0.1"
            min="0"
            value={values.distance_km}
            onChange={set('distance_km')}
            placeholder="10"
          />
        </Field>
        <Field label="Run date" error={errors.run_date}>
          <Input type="date" value={values.run_date} onChange={set('run_date')} />
        </Field>
      </div>
      <Field label="Notes" hint="Optional">
        <Textarea value={values.notes} onChange={set('notes')} placeholder="How did it feel?" />
      </Field>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Logging…' : 'Log run'}
        </Button>
      </DialogFooter>
    </form>
  )
}

function Field({ label, error, hint, children }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : (
        hint && <p className="text-xs text-muted-foreground">{hint}</p>
      )}
    </div>
  )
}
