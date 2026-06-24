import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { DialogFooter } from '@/components/ui/dialog'

const empty = {
  brand: '',
  model: '',
  nickname: '',
  shoe_type: '',
  purchase_date: '',
  starting_mileage: '0',
  current_mileage: '',
  status: 'active',
  notes: '',
  image_url: '',
}

export default function OwnedShoeForm({ initial, onSubmit, onCancel, submitting }) {
  const [values, setValues] = useState(() => ({
    ...empty,
    ...(initial
      ? {
          brand: initial.brand ?? '',
          model: initial.model ?? '',
          nickname: initial.nickname ?? '',
          shoe_type: initial.shoe_type ?? '',
          purchase_date: initial.purchase_date ?? '',
          starting_mileage: String(initial.starting_mileage ?? 0),
          current_mileage: String(initial.current_mileage ?? 0),
          status: initial.status ?? 'active',
          notes: initial.notes ?? '',
          image_url: initial.image_url ?? '',
        }
      : {}),
  }))
  const [errors, setErrors] = useState({})

  const set = (key) => (e) => setValues((v) => ({ ...v, [key]: e.target.value }))

  const validate = () => {
    const next = {}
    if (!values.brand.trim()) next.brand = 'Brand is required'
    if (!values.model.trim()) next.model = 'Model is required'
    const startMileage = parseFloat(values.starting_mileage)
    if (values.starting_mileage !== '' && (Number.isNaN(startMileage) || startMileage < 0))
      next.starting_mileage = 'Enter a mileage of 0 or more'
    if (initial && values.current_mileage !== '') {
      const curMileage = parseFloat(values.current_mileage)
      if (Number.isNaN(curMileage) || curMileage < 0)
        next.current_mileage = 'Enter a mileage of 0 or more'
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const buildPayload = () => {
    const payload = {
      brand: values.brand.trim(),
      model: values.model.trim(),
      nickname: values.nickname.trim() || null,
      shoe_type: values.shoe_type.trim() || null,
      purchase_date: values.purchase_date || null,
      starting_mileage: values.starting_mileage === '' ? 0 : parseFloat(values.starting_mileage),
      status: values.status,
      notes: values.notes.trim() || null,
      image_url: values.image_url.trim() || null,
    }
    if (initial && values.current_mileage !== '') {
      payload.current_mileage = parseFloat(values.current_mileage)
    }
    return payload
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!validate()) return
    onSubmit(buildPayload())
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Brand" error={errors.brand}>
          <Input value={values.brand} onChange={set('brand')} placeholder="Adidas" />
        </Field>
        <Field label="Model" error={errors.model}>
          <Input value={values.model} onChange={set('model')} placeholder="Adizero Adios Pro 4" />
        </Field>
        <Field label="Nickname" hint="Optional">
          <Input value={values.nickname} onChange={set('nickname')} placeholder="Race day Adios" />
        </Field>
        <Field label="Shoe type" hint="Optional">
          <Input value={values.shoe_type} onChange={set('shoe_type')} placeholder="Tempo shoe" />
        </Field>
        <Field label="Purchase date" hint="Optional">
          <Input type="date" value={values.purchase_date} onChange={set('purchase_date')} />
        </Field>
        <Field label="Status">
          <Select value={values.status} onValueChange={(v) => setValues((s) => ({ ...s, status: v }))}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="retired">Retired</SelectItem>
              <SelectItem value="for_sale">For sale</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field
          label="Starting mileage (km)"
          error={errors.starting_mileage}
          hint="Mileage already on the shoe when added"
        >
          <Input
            type="number"
            step="0.1"
            min="0"
            value={values.starting_mileage}
            onChange={set('starting_mileage')}
            disabled={!!initial}
          />
        </Field>
        {initial && (
          <Field label="Current mileage (km)" error={errors.current_mileage}>
            <Input
              type="number"
              step="0.1"
              min="0"
              value={values.current_mileage}
              onChange={set('current_mileage')}
            />
          </Field>
        )}
      </div>

      <Field
        label="Image URL"
        hint="Optional — paste a link to a product photo. Falls back to a matched scrape image, then a placeholder."
      >
        <Input
          value={values.image_url}
          onChange={set('image_url')}
          placeholder="https://…"
        />
      </Field>

      <Field label="Notes" hint="Personal notes, feel, observations">
        <Textarea value={values.notes} onChange={set('notes')} placeholder="Optional notes" />
      </Field>

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Saving…' : initial ? 'Save changes' : 'Add shoe'}
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
