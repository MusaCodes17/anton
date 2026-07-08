import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Flag, Footprints, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/toast'
import { ErrorState } from '@/components/StatusViews'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDate, formatDuration } from '@/lib/utils'
import { runSourceVariant, runSourceLabel } from '@/lib/runSource'
import {
  useActivity, useActivityTags, useUpdateActivity, useReassignShoe,
  usePromoteToRace, useOwnedShoes,
} from '@/hooks/useApi'

const NO_TAG = '__none__'

function Figure({ label, value, unit }) {
  return (
    <div className="rounded-[14px] border border-border bg-surface p-4">
      <div className="text-2xs uppercase tracking-[0.08em] text-faint">{label}</div>
      <div className="mt-1 font-heading text-xl font-extrabold tabular-nums text-foreground">
        {value ?? '—'}
        {value != null && unit ? <span className="ml-0.5 text-xs font-normal text-faint">{unit}</span> : null}
      </div>
    </div>
  )
}

export default function ActivityDetail() {
  const { id } = useParams()
  const activityId = Number(id)
  const navigate = useNavigate()
  const { toast } = useToast()

  const activity = useActivity(activityId)
  const tags = useActivityTags()
  const shoes = useOwnedShoes()
  const update = useUpdateActivity(activityId)
  const reassign = useReassignShoe(activityId)
  const promote = usePromoteToRace(activityId)

  const [tag, setTag] = useState(NO_TAG)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  // Seed the form once the activity loads (and re-seed if it changes underneath).
  const d = activity.data
  useEffect(() => {
    if (!d) return
    setTag(d.activity_tag ?? NO_TAG)
    setName(d.name ?? '')
    setDescription(d.description ?? '')
  }, [d])

  if (activity.isLoading) {
    return <div className="space-y-4"><Skeleton className="h-8 w-48" /><Skeleton className="h-64 w-full rounded-2xl" /></div>
  }
  if (activity.isError || !d) {
    return <ErrorState error={activity.error} onRetry={activity.refetch} />
  }

  const dirty = (tag === NO_TAG ? null : tag) !== (d.activity_tag ?? null)
    || name !== (d.name ?? '') || description !== (d.description ?? '')

  const save = () => {
    update.mutate(
      { activity_tag: tag === NO_TAG ? null : tag, name: name || null, description: description || null },
      {
        onSuccess: () => toast({ variant: 'success', title: 'Activity updated' }),
        onError: (e) => toast({ variant: 'destructive', title: 'Update failed', description: e?.response?.data?.detail }),
      },
    )
  }

  const onReassign = (shoeId) => {
    if (shoeId === String(d.shoe?.id)) return
    reassign.mutate(Number(shoeId), {
      onSuccess: () => toast({ variant: 'success', title: 'Shoe reassigned' }),
      onError: (e) => toast({ variant: 'destructive', title: 'Reassign failed', description: e?.response?.data?.detail }),
    })
  }

  const onPromote = () => {
    promote.mutate(undefined, {
      onSuccess: () => { toast({ variant: 'success', title: 'Added to races' }); navigate('/training#races') },
      onError: (e) => toast({ variant: 'destructive', title: 'Could not add race', description: e?.response?.data?.detail }),
    })
  }

  return (
    <div className="space-y-6">
      <Link to="/training#activities" className="focus-ring inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Activities
      </Link>

      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-heading text-2xl font-extrabold tracking-tight text-foreground">
          {d.name || 'Run'}
        </h1>
        <Badge variant={runSourceVariant(d.source)} className="text-[10px]">{runSourceLabel(d.source)}</Badge>
        {d.activity_tag && <Badge variant="secondary" className="text-[10px]">{d.activity_tag}</Badge>}
        <span className="text-sm text-muted-foreground">{d.run_date ? formatDate(d.run_date) : '—'}</span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <Figure label="Distance" value={d.distance_km != null ? d.distance_km.toFixed(2) : null} unit="km" />
        <Figure label="Pace" value={d.avg_pace} />
        <Figure label="Moving" value={d.moving_time_s != null ? formatDuration(d.moving_time_s) : null} />
        <Figure label="Elapsed" value={d.elapsed_time_s != null ? formatDuration(d.elapsed_time_s) : null} />
        <Figure label="Avg HR" value={d.avg_hr} unit="bpm" />
        <Figure label="Elevation" value={d.elevation_gain_m != null ? Math.round(d.elevation_gain_m) : null} unit="m" />
        <Figure label="Cadence" value={d.avg_cadence != null ? Math.round(d.avg_cadence) : null} />
        <Figure label="Calories" value={d.calories != null ? Math.round(d.calories) : null} />
        {d.training_load != null && <Figure label="Training load" value={Math.round(d.training_load)} />}
        {d.training_focus && <Figure label="Focus" value={d.training_focus} />}
      </div>

      {/* Edit */}
      <div className="space-y-4 rounded-2xl border border-border bg-card p-5">
        <h2 className="font-heading text-md-plus font-bold text-foreground">Edit</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Tag</Label>
            <Select value={tag} onValueChange={setTag}>
              <SelectTrigger><SelectValue placeholder="No tag" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_TAG}>No tag</SelectItem>
                {(tags.data || []).map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Shoe</Label>
            <Select value={d.shoe ? String(d.shoe.id) : undefined} onValueChange={onReassign} disabled={reassign.isPending}>
              <SelectTrigger><SelectValue placeholder="No shoe — pick one" /></SelectTrigger>
              <SelectContent>
                {(shoes.data || []).map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>{s.nickname || `${s.brand} ${s.model}`}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label>Name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Activity name" />
        </div>
        <div className="space-y-1.5">
          <Label>Notes</Label>
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} placeholder="Notes about this run" />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={save} disabled={!dirty || update.isPending}>
            <Save className="mr-1.5 h-4 w-4" /> Save
          </Button>
          {tag === 'Race' && (
            <Button variant="secondary" onClick={onPromote} disabled={promote.isPending}>
              <Flag className="mr-1.5 h-4 w-4" /> Add to races
            </Button>
          )}
          {d.shoe && (
            <Link to={`/shoes/${d.shoe.id}`} className="focus-ring inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
              <Footprints className="h-4 w-4" /> {d.shoe.nickname || d.shoe.model}
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}
