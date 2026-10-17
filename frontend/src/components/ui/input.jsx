import * as React from 'react'
import { cn } from '@/lib/utils'

const Input = React.forwardRef(({ className, type, ...props }, ref) => (
  <input
    type={type}
    className={cn(
      'flex h-10 w-full rounded-[10px] border border-input bg-background/55 px-3 py-2 text-sm text-foreground ring-offset-background transition-[border-color,box-shadow] duration-300 ease-signal placeholder:text-faint hover:border-edge focus-visible:outline-none focus-visible:border-primary focus-visible:ring-0 focus-visible:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50 file:border-0 file:bg-transparent file:text-sm file:font-medium',
      className
    )}
    ref={ref}
    {...props}
  />
))
Input.displayName = 'Input'

export { Input }
