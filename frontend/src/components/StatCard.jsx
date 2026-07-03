import { Skeleton } from '@/components/ui/skeleton'

/** Compact metric tile for the dashboard ("Velocity" stat-tile style). */
export default function StatCard({ label, value, hint, loading }) {
  return (
    <div className="rounded-[13px] border border-border bg-surface p-[17px]">
      <div className="text-2xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">
        {label}
      </div>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-16" />
      ) : (
        <div className="mt-2 font-heading text-[32px] font-extrabold leading-none tabular-nums text-foreground">
          {value}
        </div>
      )}
      {hint && !loading && <div className="mt-1.5 text-xs text-muted-foreground">{hint}</div>}
    </div>
  )
}
