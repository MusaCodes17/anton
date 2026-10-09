import { CheckCircle2, AlertTriangle, XCircle } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import ShoeStatusBadge, { getShoeScrapabilityStatus } from '@/components/ShoeStatusBadge'
import { formatCurrency } from '@/lib/utils'

/**
 * Shared results dialog for a /api/shoes/test call — used both from the shoe
 * form (test-before-save, with Modify/Proceed/Save actions) and from the
 * shoes list (click a status badge, view-only).
 */
export default function ScrapabilityTestModal({
  open,
  onOpenChange,
  shoeLabel,
  loading,
  error,
  result,
  onModifyName,
  onProceedAnyway,
  onSaveAndScrape,
  onRetest,
  savingAndScraping,
}) {
  const { status, foundCount, totalCount } = getShoeScrapabilityStatus(result)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            Scrapability test{shoeLabel ? ` — ${shoeLabel}` : ''}
          </DialogTitle>
          <DialogDescription>
            {loading
              ? 'Checking each retailer for matching products…'
              : error
                ? 'The test could not complete.'
                : result &&
                  `Found on ${foundCount}/${totalCount} retailers`}
          </DialogDescription>
        </DialogHeader>

        {!loading && result && (
          <ShoeStatusBadge status={status} foundCount={foundCount} totalCount={totalCount} />
        )}

        <div className="max-h-80 space-y-2 overflow-y-auto">
          {loading &&
            Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}

          {error && (
            <p className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </p>
          )}

          {!loading && result?.results?.map((r) => <RetailerRow key={r.retailer} r={r} />)}
        </div>

        <DialogFooter className="flex-wrap gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {onRetest && (
            <Button variant="outline" onClick={onRetest} disabled={loading}>
              {loading ? 'Testing…' : 'Re-test'}
            </Button>
          )}
          {onModifyName && (
            <Button variant="outline" onClick={onModifyName}>
              Modify name
            </Button>
          )}
          {onProceedAnyway && (
            <Button variant="secondary" onClick={onProceedAnyway}>
              Proceed anyway
            </Button>
          )}
          {onSaveAndScrape && (
            <Button onClick={onSaveAndScrape} disabled={savingAndScraping}>
              {savingAndScraping ? 'Saving…' : 'Save & scrape now'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RetailerRow({ r }) {
  if (r.status === 'success') {
    return (
      <div className="flex items-start gap-3 rounded-md border p-3">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="text-sm font-medium">{r.retailer}</p>
          <p className="text-xs text-muted-foreground">
            {r.products_found} product{r.products_found === 1 ? '' : 's'} found
            {r.sample_price != null && <> · sample price {formatCurrency(r.sample_price)}</>}
          </p>
          {r.sizes?.length > 0 && (
            <p className="text-xs text-muted-foreground">Sizes: {r.sizes.join(', ')}</p>
          )}
        </div>
      </div>
    )
  }

  if (r.status === 'not_found') {
    return (
      <div className="flex items-start gap-3 rounded-md border border-warning/30 bg-warning/5 p-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="text-sm font-medium">{r.retailer}</p>
          <p className="text-xs text-muted-foreground">Not found</p>
          {r.suggestion && <p className="text-xs text-muted-foreground">{r.suggestion}</p>}
        </div>
      </div>
    )
  }

  // error
  return (
    <div className="flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-3">
      <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-sm font-medium">{r.retailer}</p>
        <p className="text-xs text-muted-foreground">
          Error checking{r.error ? `: ${r.error}` : ''}
        </p>
      </div>
    </div>
  )
}
