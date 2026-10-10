import { useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Footprints } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import RetirementPipeline from '@/components/shoes/RetirementPipeline'
import { ErrorState, EmptyState, CardSkeletonGrid } from '@/components/StatusViews'
import { useOwnedShoes, useRotationOverview } from '@/hooks/useApi'

// Full retirement pipeline (every shoe past 75% of its limit). The Shoes page
// shows a two-shoe preview and links here via "See all N".
export default function ShoePipeline() {
  const navigate = useNavigate()
  const overview = useRotationOverview()
  const shoes = useOwnedShoes()

  // Same join as the Shoes page: active (non-retired) shoes only; pipeline
  // entries whose shoe isn't found are dropped.
  const all = useMemo(() => {
    const activeById = new Map(
      (shoes.data || []).filter((s) => s.status !== 'retired').map((s) => [s.id, s])
    )
    return (overview.data?.pipeline || [])
      .map((e) => ({ ...e, shoe: activeById.get(e.owned_shoe_id) }))
      .filter((e) => e.shoe)
  }, [overview.data, shoes.data])

  const retry = () => {
    overview.refetch()
    shoes.refetch()
  }

  return (
    <div className="space-y-5 sm:space-y-8">
      <Link to="/shoes" className="focus-ring rounded inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to Shoes
      </Link>

      <PageHeader eyebrow="MY SHOES" title="Retirement pipeline" />

      {overview.isLoading || shoes.isLoading ? (
        <CardSkeletonGrid count={3} />
      ) : overview.isError || shoes.isError ? (
        <ErrorState error={overview.error || shoes.error} onRetry={retry} />
      ) : all.length ? (
        <RetirementPipeline entries={all} total={all.length} onOpenDetail={(id) => navigate(`/shoes/${id}`)} />
      ) : (
        <EmptyState
          icon={Footprints}
          title="Nothing in the pipeline"
          description="No shoe is past 75% of its limit."
        />
      )}
    </div>
  )
}
