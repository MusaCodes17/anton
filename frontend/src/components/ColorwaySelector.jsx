import { Footprints } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Horizontal gallery of colorway/retailer options for a shoe. Each option is a
 * deal ({ id, image_url, colorway, current_price, in_stock, retailer, product_url }).
 * Clicking a thumbnail calls onSelect(id). Out-of-stock options are dimmed.
 */
export default function ColorwaySelector({ options, selectedId, onSelect }) {
  if (!options || options.length <= 1) return null

  return (
    <div className="flex flex-wrap gap-[7px]">
      {options.map((opt) => {
        const retailerName =
          typeof opt.retailer === 'string' ? opt.retailer : opt.retailer?.name
        const label = [opt.colorway, retailerName].filter(Boolean).join(' · ')
        const selected = opt.id === selectedId
        return (
          <button
            key={opt.id}
            type="button"
            title={label || 'Colorway'}
            aria-label={label || 'Colorway'}
            aria-pressed={selected}
            onClick={() => onSelect(opt.id)}
            className={cn(
              'relative h-[34px] w-[34px] shrink-0 overflow-hidden rounded-[8px] border bg-secondary transition',
              selected ? 'border-2 border-primary' : 'border-border hover:border-primary/50',
              opt.in_stock === false && 'opacity-50'
            )}
          >
            {opt.image_url ? (
              <img
                src={opt.image_url}
                alt={label || 'Colorway'}
                loading="lazy"
                className="h-full w-full object-contain"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-muted-foreground">
                <Footprints className="h-4 w-4" />
              </div>
            )}
          </button>
        )
      })}
    </div>
  )
}
