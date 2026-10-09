import { SlidersHorizontal, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Mobile-only "Filters" toggle for a page's filter deck (Deals, Shoes). The
 * deck itself stays inline on md+; on phones it is collapsed by default so
 * the content is above the fold. Pair with `hidden md:block` on the deck
 * when `open` is false. `count` is the number of non-default filters.
 */
export default function FilterDisclosure({ open, onToggle, count = 0, className }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        'focus-ring flex w-full items-center gap-2 rounded-[12px] border border-border bg-card px-4 py-3 text-left md:hidden',
        className
      )}
      aria-expanded={open}
    >
      <SlidersHorizontal className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="font-medium text-foreground">Filters</span>
      {/* Solid chip: Tailwind's /15 opacity modifier doesn't generate for the
          var()-based colour tokens, so a tinted chip would render bare. */}
      {count > 0 && (
        <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-bold text-primary-foreground">
          {count}
        </span>
      )}
      <ChevronDown
        className={`ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 ${
          open ? '' : '-rotate-90'
        }`}
      />
    </button>
  )
}
