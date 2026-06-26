import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useScrapeStream } from '@/hooks/useApi'
import { useToast } from '@/components/ui/toast'
import { cn } from '@/lib/utils'

/**
 * "Run scan" button — kicks off a background scrape (POST /api/scrape/all,
 * returns immediately) and tracks live per-retailer progress via SSE
 * (GET /api/scrape/stream). Each retailer reports in independently; one
 * retailer failing doesn't stop the others from finishing. Only a single
 * summary toast is shown, on overall completion — not one per retailer.
 */
export default function ScrapeButton({ className, ...props }) {
  const { isRunning, connectionLost, start } = useScrapeStream()
  const { toast } = useToast()

  const handleClick = () => {
    let failedRetailers = 0

    start((event) => {
      if (event.type === 'retailer_error') {
        failedRetailers += 1
      } else if (event.type === 'completed') {
        toast({
          variant: failedRetailers > 0 ? 'destructive' : 'success',
          title: 'Scrape complete',
          description:
            `${event.total_deals} deal${event.total_deals === 1 ? '' : 's'} found` +
            (failedRetailers > 0
              ? ` — ${failedRetailers} retailer${failedRetailers === 1 ? '' : 's'} failed`
              : ''),
        })
      }
    })
      .then((data) => {
        if (data && data.started === false) {
          // A scrape was already running (e.g. started before a reload) —
          // useScrapeStream attaches to it anyway, so this is informational,
          // not a failure: the button below is already watching it live.
          toast({
            variant: 'default',
            title: 'Already scraping',
            description: 'Watching the scrape already in progress…',
          })
        }
      })
      .catch((err) => {
        toast({ variant: 'destructive', title: 'Scrape failed', description: err.message })
      })
  }

  return (
    <div className="flex items-center gap-2">
      <Button onClick={handleClick} disabled={isRunning} className={className} {...props}>
        <RefreshCw className={cn('h-4 w-4', isRunning && 'animate-spin')} />
        {isRunning ? 'Scraping…' : 'Run scan'}
      </Button>
      {connectionLost && (
        <span className="inline-flex items-center gap-1.5 text-xs text-warning">
          <AlertTriangle className="h-3.5 w-3.5" />
          Scrape status unknown — refresh to see latest deals
        </span>
      )}
    </div>
  )
}
