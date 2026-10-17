import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  // Horizon redesign: buttons are square-ish (10px) mono-uppercase (template .btn).
  // default = filled amber .btn-lit (template .btn.lleno); outline = amber-edged
  // (template .btn); secondary = ghost-glass (template .btn.fantasma). Transitions
  // use the template's one easing.
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[10px] font-mono text-xs font-medium uppercase tracking-label transition-[background-color,border-color,color,box-shadow] duration-300 ease-signal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'btn-lit',
        destructive:
          'border border-destructive/50 text-destructive hover:bg-destructive hover:text-destructive-foreground',
        outline:
          'border border-primary text-primary bg-background/25 hover:bg-primary hover:text-primary-foreground',
        secondary:
          'border border-edge bg-background/35 text-foreground hover:bg-foreground hover:text-background hover:border-foreground',
        ghost: 'text-muted-foreground hover:bg-accent hover:text-foreground',
        link: 'normal-case tracking-normal font-sans text-sm text-primary underline-offset-4 hover:underline',
        // Same as outline: amber-edged, floods with amber on hover.
        signal: 'border border-primary text-primary bg-background/25 hover:bg-primary hover:text-primary-foreground',
      },
      size: {
        default: 'h-10 px-5',
        sm: 'h-9 px-3.5',
        lg: 'h-12 px-7',
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
