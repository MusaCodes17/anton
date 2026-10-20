// From/To date inputs and range presets for a page's date range (T4b). Takes the
// object returned by useDateRange; inputs bind to the drafts, presets apply immediately.
import { Input } from '@/components/ui/input'
import { isoDaysAgo, isoToday } from '@/hooks/useDateRange'

export default function DateRangeControls({ range }) {
  const { draftFrom, draftTo, setDraftFrom, setDraftTo, applyPreset } = range
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Input
        type="date"
        value={draftFrom}
        max={draftTo || undefined}
        onChange={(e) => setDraftFrom(e.target.value)}
        className="h-8 w-[7.5rem] sm:w-[9.5rem] px-2 py-1"
        aria-label="From date"
      />
      <span className="text-muted-foreground">→</span>
      <Input
        type="date"
        value={draftTo}
        min={draftFrom || undefined}
        onChange={(e) => setDraftTo(e.target.value)}
        className="h-8 w-[7.5rem] sm:w-[9.5rem] px-2 py-1"
        aria-label="To date"
      />
      {[['90d', 90], ['6mo', 182], ['1y', 365]].map(([label, days]) => (
        <button
          key={label}
          type="button"
          onClick={() => applyPreset(isoDaysAgo(days), isoToday())}
          className="focus-ring rounded-md border border-border px-2 py-1 font-medium text-muted-foreground hover:text-foreground"
        >
          {label}
        </button>
      ))}
    </div>
  )
}
