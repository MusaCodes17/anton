import { useEffect, useRef } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Footprints, Store, RefreshCw, ShieldCheck } from 'lucide-react'
import { cn } from '@/lib/utils'
import { LogoutButton } from '@/components/layout/Layout'
import PageHeader from '@/components/PageHeader'

// Settings is a control room, not a primary domain. It re-homes the former
// top-level "Tracked Shoes" and "Retailers" pages plus a new sync/scraping
// status view, each a deep-linkable sub-route so mobile nav stays URL-driven.
const subNav = [
  { to: '/settings/tracking', label: 'Tracking', icon: Footprints },
  { to: '/settings/retailers', label: 'Retailers', icon: Store },
  { to: '/settings/sync', label: 'Sync & Scraping', icon: RefreshCw },
  { to: '/settings/security', label: 'Security', icon: ShieldCheck },
]

export default function Settings() {
  // On phones the strip scrolls; keep the active tab fully in view.
  const navRef = useRef(null)
  const { pathname } = useLocation()
  useEffect(() => {
    navRef.current
      ?.querySelector('[aria-current="page"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [pathname])

  return (
    <div>
      <PageHeader title="Settings" />

      {/* Sub-nav — the template's segmented .tabs pill; scrolls horizontally on
          narrow viewports rather than wrapping. */}
      <nav
        ref={navRef}
        // Edge fades say "more this way" when the strip overflows.
        className="scrollbar-none mb-5 flex w-fit max-w-full gap-1 overflow-x-auto rounded-full border border-border p-1 [mask-image:linear-gradient(90deg,transparent,#000_18px,#000_calc(100%-24px),transparent)] sm:mb-8 sm:[mask-image:none]"
      >
        {subNav.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'focus-ring flex shrink-0 items-center gap-2 rounded-full px-3.5 py-2 text-sm font-medium transition-colors duration-300 ease-signal',
                isActive
                  ? 'bg-secondary text-foreground shadow-[inset_0_0_0_1px_var(--input)]'
                  : 'text-muted-foreground hover:text-foreground'
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
