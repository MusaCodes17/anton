import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  // Signal redesign: every button is a pill (template .btn). The primary is
  // the lit pill (.btn-lit in index.css); the rest are quiet outlines that
  // pick up the signal on hover. Transitions use the template's one easing.
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium transition-[background-color,border-color,color,box-shadow] duration-300 ease-signal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'btn-lit',
        destructive:
          'border border-destructive/50 text-destructive hover:bg-destructive hover:text-destructive-foreground',
        outline:
          'border border-input bg-foreground/[0.02] text-secondary-foreground hover:border-primary/50 hover:bg-accent hover:text-foreground',
        secondary:
          'border border-border bg-secondary text-secondary-foreground hover:border-edge hover:text-foreground',
        ghost: 'text-muted-foreground hover:bg-accent hover:text-foreground',
        link: 'text-primary underline-offset-4 hover:underline',
        // Template .btn-outline: signal-edged, floods with signal on hover.
        signal: 'border border-primary/50 text-primary hover:bg-primary hover:text-primary-foreground',
      },
      size: {
        default: 'h-10 px-5 py-2',
        sm: 'h-9 px-3.5',
        lg: 'h-11 px-7 text-md-plus',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

const Button = React.forwardRef(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = 'Button'

export { Button, buttonVariants }
