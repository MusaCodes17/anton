import * as React from 'react'
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  // Template .tags / .state: a small mono tag with a hairline in its own
  // hue over a faint wash of it — status reads by colour AND by word.
  'inline-flex items-center gap-1 rounded-[5px] border px-2 py-[3px] font-mono text-2xs font-medium leading-none tracking-[0.02em] transition-colors focus:outline-none',
  {
    variants: {
      variant: {
        default: 'border-primary/45 bg-primary/10 text-primary',
        secondary: 'border-border bg-secondary text-secondary-foreground',
        destructive: 'border-destructive/50 bg-destructive/10 text-destructive',
        success: 'border-success/45 bg-success/10 text-success',
        warning: 'border-warning/45 bg-warning/10 text-warning',
        strava: 'border-strava/50 bg-strava/10 text-strava',
        outline: 'border-input text-secondary-foreground',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

function Badge({ className, variant, ...props }) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
