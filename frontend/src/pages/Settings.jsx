import { NavLink, Outlet } from 'react-router-dom'
import { Footprints, Store, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { LogoutButton } from '@/components/layout/Layout'

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
      <div className="mb-3 sm:mb-6">
        <div className="hidden font-mono text-xs font-semibold tracking-[0.14em] text-accent-foreground sm:block">
          SETTINGS
        </div>
        <h1 className="text-2xl font-heading font-extrabold tracking-tight text-foreground sm:mt-1.5 sm:text-[30px]">
          Settings
        </h1>
      </div>

      {/* Sub-nav — horizontal scroll on narrow viewports rather than wrapping */}
      <nav className="mb-4 flex sm:mb-7 gap-1.5 overflow-x-auto border-b border-border pb-px">
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

      {/* Phones have no sidebar, so Sign out lives here (desktop keeps it in
          the sidebar footer). */}
      <div className="mt-6 md:mt-10 border-t border-border pt-3 md:hidden">
        <LogoutButton />
      </div>
    </div>
  )
}
