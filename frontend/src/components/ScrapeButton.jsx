import { RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useScrapeAll } from '@/hooks/useApi'
import { useToast } from '@/components/ui/toast'
import { cn } from '@/lib/utils'

/** "Scrape Now" button — triggers POST /api/scrape/all and reports results. */
export default function ScrapeButton({ className, ...props }) {
  const scrape = useScrapeAll()
  const { toast } = useToast()

  const handleClick = () => {
    scrape.mutate(undefined, {
      onSuccess: (data) => {
        const r = data?.results || {}
        const deals =
          r.total_deals_found ?? r.deals_found ?? r.total_new_deals ?? 0
        toast({
          variant: 'success',
          title: 'Scrape complete',
          description:
            data?.message ||
            `Found ${deals} deal${deals === 1 ? '' : 's'}.`,
        })
      },
      onError: (err) => {
        toast({
          variant: 'destructive',
          title: 'Scrape failed',
          description: err.message,
        })
      },
    })
  }

  return (
    <Button
      onClick={handleClick}
      disabled={scrape.isPending}
      className={className}
      {...props}
    >
      <RefreshCw className={cn('h-4 w-4', scrape.isPending && 'animate-spin')} />
      {scrape.isPending ? 'Scanning…' : 'Run scan'}
    </Button>
  )
}
