import { NavLink, Outlet } from 'react-router-dom'
import { Footprints, Store, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

// Settings is a control room, not a primary domain. It re-homes the former
// top-level "Tracked Shoes" and "Retailers" pages plus a new sync/scraping
// status view, each a deep-linkable sub-route so mobile nav stays URL-driven.
const subNav = [
  { to: '/settings/tracking', label: 'Tracking', icon: Footprints },
  { to: '/settings/retailers', label: 'Retailers', icon: Store },
  { to: '/settings/sync', label: 'Sync & Scraping', icon: RefreshCw },
]

export default function Settings() {
  return (
    <div>
      <div className="mb-6">
        <div className="font-mono text-xs font-semibold tracking-[0.14em] text-accent-foreground">
          SETTINGS
        </div>
        <h1 className="mt-1.5 font-heading text-[30px] font-extrabold tracking-tight text-foreground">
          Settings
        </h1>
      </div>

      {/* Sub-nav — horizontal scroll on narrow viewports rather than wrapping */}
      <nav className="mb-7 flex gap-1.5 overflow-x-auto border-b border-border pb-px">
        {subNav.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'focus-ring -mb-px flex shrink-0 items-center gap-2 rounded-t-lg border-b-2 px-3.5 py-2.5 text-sm transition-colors',
                isActive
                  ? 'border-primary font-bold text-foreground'
                  : 'border-transparent font-medium text-muted-foreground hover:text-foreground'
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  )
}
