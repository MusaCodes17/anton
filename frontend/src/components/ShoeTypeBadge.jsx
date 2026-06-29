import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { SHOE_TYPE_LABELS, SHOE_TYPE_BADGE_CLASSES } from '@/lib/shoeTypes'

export default function ShoeTypeBadge({ type, className }) {
  if (!type) return null
  const label = SHOE_TYPE_LABELS[type] || type
  const colorClasses = SHOE_TYPE_BADGE_CLASSES[type] || 'bg-muted/50 text-muted-foreground border-border'
  return (
    <Badge className={cn('border text-[10px]', colorClasses, className)}>
      {label}
    </Badge>
  )
}
