import { useState } from 'react'
import { FlaskConical } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { DialogFooter } from '@/components/ui/dialog'
import ScrapabilityTestModal from '@/components/ScrapabilityTestModal'
import { useShoeTypes, useTestShoeScrapability } from '@/hooks/useApi'
import { formatShoeType } from '@/lib/shoeTypes'

const empty = {
  brand: '',
  model: '',
  shoe_type: '',
  target_price: '',
  msrp: '',
  notes: '',
  is_active: true,
}

/**
 * Controlled form for creating/editing a shoe.
 * `onSubmit(payload, { scrapeAfterSave })` receives a cleaned object;
 * `submitting` disables it.
 */
export default function ShoeForm({ initial, onSubmit, onCancel, submitting }) {
  const [values, setValues] = useState(() => ({
    ...empty,
    ...(initial
      ? {
          brand: initial.brand ?? '',
          model: initial.model ?? '',
          shoe_type: initial.shoe_type ?? '',
          target_price: initial.target_price ?? '',
          msrp: initial.msrp ?? '',
          notes: initial.notes ?? '',
          is_active: initial.is_active ?? true,
        }
      : {}),
  }))
  const [errors, setErrors] = useState({})
  const [testModalOpen, setTestModalOpen] = useState(false)
  const testMutation = useTestShoeScrapability()
  const { data: shoeTypes = [] } = useShoeTypes()

  const set = (key) => (e) =>
    setValues((v) => ({ ...v, [key]: e.target.value }))

  const validate = () => {
    const next = {}
    if (!values.brand.trim()) next.brand = 'Brand is required'
    if (!values.model.trim()) next.model = 'Model is required'
    const msrp = parseFloat(values.msrp)
    if (!values.msrp || Number.isNaN(msrp) || msrp <= 0)
      next.msrp = 'Enter a price greater than 0'
    if (values.target_price) {
      const price = parseFloat(values.target_price)
      if (Number.isNaN(price) || price <= 0) next.target_price = 'Enter a price greater than 0'
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const buildPayload = () => ({
    brand: values.brand.trim(),
    model: values.model.trim(),
    shoe_type: values.shoe_type || null,
    msrp: parseFloat(values.msrp),
    target_price: values.target_price ? parseFloat(values.target_price) : null,
    notes: values.notes.trim() || null,
    is_active: values.is_active,
  })

  const submit = (scrapeAfterSave = false) => {
    if (!validate()) return
    onSubmit(buildPayload(), { scrapeAfterSave })
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    submit(false)
  }

  const handleTest = () => {
    const next = {}
    if (!values.brand.trim()) next.brand = 'Brand is required'
    if (!values.model.trim()) next.model = 'Model is required'
    setErrors(next)
    if (Object.keys(next).length) return
    setTestModalOpen(true)
    testMutation.mutate({ brand: values.brand.trim(), model: values.model.trim() })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Brand" error={errors.brand}>
          <Input
            value={values.brand}
            onChange={set('brand')}
            placeholder="Nike"
          />
        </Field>
        <Field label="Model" error={errors.model}>
          <Input
            value={values.model}
            onChange={set('model')}
            placeholder="Vaporfly 3"
          />
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
        <Field label="Retail price / MSRP (CAD)" error={errors.msrp} hint="Drives deals — a sale is any price below this">
          <Input
            type="number"
            step="0.01"
            min="0"
            value={values.msrp}
            onChange={set('msrp')}
            placeholder="220"
          />
        </Field>
        <Field label="Target price (CAD)" error={errors.target_price} hint="Optional — a personal 'ping me at' threshold">
          <Input
            type="number"
            step="0.01"
            min="0"
            value={values.target_price}
            onChange={set('target_price')}
            placeholder="180"
          />
        </Field>
      </div>

      <Field label="Notes">
        <Textarea
          value={values.notes}
          onChange={set('notes')}
          placeholder="Optional — e.g. only interested in white colorway"
        />
      </Field>

      <div className="flex items-center justify-between rounded-md border p-3">
        <div>
          <Label className="text-sm font-medium">Actively monitor</Label>
          <p className="text-xs text-muted-foreground">
            Include this shoe in scrapes and deal detection.
          </p>
        </div>
        <Switch
          checked={values.is_active}
          onCheckedChange={(checked) =>
            setValues((v) => ({ ...v, is_active: checked }))
          }
        />
      </div>

      <Button type="button" variant="outline" className="w-full" onClick={handleTest}>
        <FlaskConical className="h-4 w-4" /> Test scrapability
      </Button>

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Saving…' : initial ? 'Save changes' : 'Add shoe'}
        </Button>
      </DialogFooter>

      <ScrapabilityTestModal
        open={testModalOpen}
        onOpenChange={setTestModalOpen}
        shoeLabel={`${values.brand} ${values.model}`.trim()}
        loading={testMutation.isPending}
        error={testMutation.isError ? testMutation.error.message : null}
        result={testMutation.data}
        onModifyName={() => setTestModalOpen(false)}
        onProceedAnyway={() => {
          setTestModalOpen(false)
          submit(false)
        }}
        onSaveAndScrape={() => {
          setTestModalOpen(false)
          submit(true)
        }}
        savingAndScraping={submitting}
      />
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
