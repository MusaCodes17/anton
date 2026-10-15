import { cn } from '@/lib/utils'

function Skeleton({ className, ...props }) {
  return (
    <div
      className={cn('animate-pulse rounded-[10px] bg-surface', className)}
      {...props}
    />
  )
}

export { Skeleton }
