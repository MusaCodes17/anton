import { useEffect, useState } from 'react'
import { CheckCircle2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/toast'
import { useFetchCorosRuns, useConfirmCorosRuns } from '@/hooks/useApi'

const SPORT_LABELS = {
  100: 'Outdoor run',
  101: 'Indoor run',
  102: 'Trail run',
  103: 'Track run',
}

function parsePaceToSeconds(pace) {
  if (!pace) return null
  const m = pace.match(/^(\d+):(\d{2})\/km$/)
  return m ? parseInt(m[1]) * 60 + parseInt(m[2]) : null
}

function suggestShoe(run, activeShoes) {
  if (!activeShoes.length) return null
  const paceSeconds = parsePaceToSeconds(run.avg_pace)
  const isRacePace = paceSeconds !== null && paceSeconds < 250 // < 4:10/km

  const sorted = [...activeShoes].sort((a, b) => a.current_mileage - b.current_mileage)

  if (isRacePace) {
    const raceShoes = sorted.filter((s) => {
      const t = (s.shoe_type || '').toLowerCase()
      return t.includes('race') || t.includes('tempo')
    })
    return (raceShoes.length ? raceShoes : sorted)[0]
  } else {
    const trainingShoes = sorted.filter((s) => {
      const t = (s.shoe_type || '').toLowerCase()
      return t.includes('train') || t.includes('daily') || t.includes('easy')
    })
    return (trainingShoes.length ? trainingShoes : sorted)[0]
  }
}

function formatDate(dateStr) {
  const [y, m, d] = dateStr.split('-')
  return new Date(+y, +m - 1, +d).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export default function CorosSyncModal({ open, onOpenChange, activeShoes, lastSyncAt }) {
  const [step, setStep] = useState('idle') // idle | fetching | assign | confirming | success
  const [runs, setRuns] = useState([])
  const [alreadySynced, setAlreadySynced] = useState(0)
  // Map coros_activity_id → owned_shoe_id string (or 'skip')
  const [assignments, setAssignments] = useState({})
  const [successResult, setSuccessResult] = useState(null)

  const fetchRuns = useFetchCorosRuns()
  const confirmRuns = useConfirmCorosRuns()
  const { toast } = useToast()

  const daysBack = lastSyncAt
    ? Math.max(7, Math.ceil((Date.now() - new Date(lastSyncAt).getTime()) / 86400000) + 1)
    : 30

  useEffect(() => {
    if (!open) {
      setStep('idle')
      setRuns([])
      setAlreadySynced(0)
      setAssignments({})
      setSuccessResult(null)
      return
    }

    setStep('fetching')
    fetchRuns.mutate(daysBack, {
      onSuccess: (data) => {
        if (!data.coros_configured) {
          setStep('not-configured')
          return
        }
        const fetched = data.runs || []
        setRuns(fetched)
        setAlreadySynced(data.already_synced || 0)

        const initial = {}
        fetched.forEach((run) => {
          const suggested = suggestShoe(run, activeShoes)
          initial[run.coros_activity_id] = suggested ? String(suggested.id) : 'skip'
        })
        setAssignments(initial)
        setStep('assign')
      },
      onError: (err) => {
        toast({ variant: 'destructive', title: 'COROS fetch failed', description: err.message })
        onOpenChange(false)
      },
    })
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const assignedCount = Object.values(assignments).filter((v) => v && v !== 'skip').length

  const handleConfirm = () => {
    const payload = runs
      .filter((run) => assignments[run.coros_activity_id] && assignments[run.coros_activity_id] !== 'skip')
      .map((run) => ({
        coros_activity_id: run.coros_activity_id,
        owned_shoe_id: parseInt(assignments[run.coros_activity_id]),
        date: run.date,
        distance_km: run.distance_km,
        avg_pace: run.avg_pace,
        avg_hr: run.avg_hr,
        notes: null,
      }))

    if (!payload.length) {
      onOpenChange(false)
      return
    }

    setStep('confirming')
    confirmRuns.mutate(payload, {
      onSuccess: (result) => {
        setSuccessResult(result)
        setStep('success')
      },
      onError: (err) => {
        toast({ variant: 'destructive', title: 'Sync failed', description: err.message })
        setStep('assign')
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onOpenChange(false)}>
      <DialogContent className="max-w-2xl">
        {step === 'fetching' && (
          <>
            <DialogHeader>
              <DialogTitle>Sync from COROS</DialogTitle>
              <DialogDescription>Fetching recent runs…</DialogDescription>
            </DialogHeader>
            <div className="flex items-center justify-center py-10">
              <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          </>
        )}

        {step === 'not-configured' && (
          <>
            <DialogHeader>
              <DialogTitle>COROS not configured</DialogTitle>
              <DialogDescription>
                Add <code className="font-mono text-xs">COROS_ACCESS_TOKEN</code> and{' '}
                <code className="font-mono text-xs">COROS_OPEN_ID</code> to your backend{' '}
                <code className="font-mono text-xs">.env</code> file to enable sync.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>Close</Button>
            </DialogFooter>
          </>
        )}

        {step === 'assign' && (
          <>
            <DialogHeader>
              <DialogTitle>Assign runs to shoes</DialogTitle>
              <DialogDescription>
                {runs.length > 0
                  ? `${runs.length} new ${runs.length === 1 ? 'run' : 'runs'} found${alreadySynced ? ` · ${alreadySynced} already logged` : ''}.
                     Choose a shoe for each run, or skip it.`
                  : alreadySynced > 0
                  ? `No new runs — ${alreadySynced} already logged.`
                  : 'No new runs found in the selected time window.'}
              </DialogDescription>
            </DialogHeader>

            {runs.length > 0 && (
              <div className="max-h-[420px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs font-bold uppercase tracking-wider text-faint">
                      <th className="pb-2 pr-3">Date</th>
                      <th className="pb-2 pr-3">Distance</th>
                      <th className="pb-2 pr-3">Pace</th>
                      <th className="pb-2 pr-3">HR</th>
                      <th className="pb-2">Assign to shoe</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((run) => (
                      <tr key={run.coros_activity_id} className="border-b border-border/50">
                        <td className="py-2.5 pr-3">
                          <div className="font-medium text-foreground">{formatDate(run.date)}</div>
                          <div className="text-2xs text-faint">{SPORT_LABELS[run.sport_type] || 'Run'}</div>
                        </td>
                        <td className="py-2.5 pr-3 font-mono text-foreground">
                          {run.distance_km.toFixed(2)} km
                        </td>
                        <td className="py-2.5 pr-3 font-mono text-foreground">
                          {run.avg_pace || '—'}
                        </td>
                        <td className="py-2.5 pr-3 text-foreground">
                          {run.avg_hr ? `${run.avg_hr} bpm` : '—'}
                        </td>
                        <td className="py-2.5">
                          <Select
                            value={assignments[run.coros_activity_id] || 'skip'}
                            onValueChange={(v) =>
                              setAssignments((prev) => ({
                                ...prev,
                                [run.coros_activity_id]: v,
                              }))
                            }
                          >
                            <SelectTrigger className="h-8 w-48 text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="skip">
                                <span className="text-muted-foreground">Skip this run</span>
                              </SelectItem>
                              {activeShoes.map((shoe) => (
                                <SelectItem key={shoe.id} value={String(shoe.id)}>
                                  {shoe.nickname || shoe.model}
                                  <span className="ml-1.5 text-faint">
                                    ({shoe.current_mileage.toFixed(0)}km)
                                  </span>
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <DialogFooter className="mt-2">
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button onClick={handleConfirm} disabled={assignedCount === 0 && runs.length > 0}>
                {assignedCount > 0
                  ? `Sync ${assignedCount} ${assignedCount === 1 ? 'run' : 'runs'}`
                  : runs.length === 0
                  ? 'Close'
                  : 'All skipped — close'}
              </Button>
            </DialogFooter>
          </>
        )}

        {step === 'confirming' && (
          <>
            <DialogHeader>
              <DialogTitle>Logging runs…</DialogTitle>
            </DialogHeader>
            <div className="flex items-center justify-center py-10">
              <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          </>
        )}

        {step === 'success' && successResult && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-green-500" />
                {successResult.logged} {successResult.logged === 1 ? 'run' : 'runs'} logged
              </DialogTitle>
            </DialogHeader>

            {successResult.updated_shoes?.length > 0 && (
              <div className="space-y-2">
                {successResult.updated_shoes.map((shoe) => (
                  <div
                    key={shoe.id}
                    className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2.5 text-sm"
                  >
                    <span className="font-medium text-foreground">
                      {shoe.nickname || shoe.model}
                    </span>
                    <div className="flex items-center gap-2 text-faint">
                      <span className="font-mono">{shoe.current_mileage.toFixed(2)} km total</span>
                      <Badge variant="secondary">Updated</Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>Done</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
