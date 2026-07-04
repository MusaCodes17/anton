import { Activity } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import { EmptyState } from '@/components/StatusViews'

/**
 * Training tab placeholder. The real Trends / Records / Activities surface
 * lands in Phase 3 (it depends on the union activities endpoints). Until
 * then this is an honest, deep-linkable empty state so the nav item is real.
 */
export default function Training() {
  return (
    <div>
      <PageHeader
        eyebrow="TRAIN"
        title="Training"
        description="Volume trends, personal records, and your full activity history."
      />
      <EmptyState
        icon={Activity}
        title="Coming in Phase 3"
        description="Trends, records, and a unified activity feed (COROS + Strava) will live here."
      />
    </div>
  )
}
