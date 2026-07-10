import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { DialogFooter } from '@/components/ui/dialog'
import { useShoeTypes } from '@/hooks/useApi'
import { formatShoeType } from '@/lib/shoeTypes'

const empty = {
  brand: '',
  model: '',
  nickname: '',
  shoe_type: '',
  purchase_date: '',
  purchase_price: '',
  starting_mileage: '0',
  status: 'active',
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
          purchase_price: initial.purchase_price != null ? String(initial.purchase_price) : '',
          starting_mileage: String(initial.starting_mileage ?? 0),
          status: initial.status ?? 'active',
          image_url: initial.image_url ?? '',
        }
      : {}),
  }))
  const [errors, setErrors] = useState({})
  const { data: shoeTypes = [] } = useShoeTypes()

  const set = (key) => (e) => setValues((v) => ({ ...v, [key]: e.target.value }))

  const validate = () => {
    const next = {}
    if (!values.brand.trim()) next.brand = 'Brand is required'
    if (!values.model.trim()) next.model = 'Model is required'
    const startMileage = parseFloat(values.starting_mileage)
    if (values.starting_mileage !== '' && (Number.isNaN(startMileage) || startMileage < 0))
      next.starting_mileage = 'Enter a mileage of 0 or more'
    if (values.purchase_price !== '') {
      const price = parseFloat(values.purchase_price)
      if (Number.isNaN(price) || price <= 0) next.purchase_price = 'Enter a price greater than 0'
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
      purchase_price: values.purchase_price === '' ? null : parseFloat(values.purchase_price),
      starting_mileage: values.starting_mileage === '' ? 0 : parseFloat(values.starting_mileage),
      status: values.status,
      image_url: values.image_url.trim() || null,
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
        <Field label="Shoe type" hint="Optional — used for replacement deal suggestions">
          <Select
            value={values.shoe_type || '__none__'}
            onValueChange={(v) => setValues((s) => ({ ...s, shoe_type: v === '__none__' ? '' : v }))}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select type…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">Untagged</SelectItem>
              {shoeTypes.map((t) => (
                <SelectItem key={t} value={t}>{formatShoeType(t)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Purchase date" hint="Optional">
          <Input type="date" value={values.purchase_date} onChange={set('purchase_date')} />
        </Field>
        <Field label="Purchase price ($)" error={errors.purchase_price} hint="Optional">
          <Input
            type="number"
            step="0.01"
            min="0"
            value={values.purchase_price}
            onChange={set('purchase_price')}
            placeholder="225.00"
          />
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
