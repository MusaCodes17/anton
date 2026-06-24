import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { LayoutDashboard, Tag, Footprints, Store, Menu, X, PersonStanding } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { useDashboardStats } from '@/hooks/useApi'
import { formatRelativeTime } from '@/lib/utils'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/deals', label: 'Deals', icon: Tag },
  { to: '/shoes', label: 'Tracked Shoes', icon: Footprints },
  { to: '/retailers', label: 'Retailers', icon: Store },
  { to: '/my-shoes', label: 'My Shoes', icon: PersonStanding },
]

function NavLinks({ onNavigate }) {
  return (
    <nav className="flex flex-col gap-1">
      {navItems.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-[9px] px-3 py-[11px] text-sm transition-colors',
              isActive
                ? 'bg-accent font-bold text-accent-foreground'
                : 'font-medium text-muted-foreground hover:bg-secondary hover:text-foreground'
            )
          }
        >
          {({ isActive }) => (
            <>
              <span
                className={cn(
                  'h-[7px] w-[7px] shrink-0 rotate-45 rounded-[2px]',
                  isActive ? 'bg-primary' : 'bg-[#3A3E44]'
                )}
              />
              {label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

function Brand() {
  return (
    <div className="flex items-center gap-[11px] px-2">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary">
        <span className="h-[11px] w-[11px] rotate-45 rounded-[2px] bg-background" />
      </span>
      <span className="font-heading text-[19px] font-extrabold tracking-tight text-foreground">
        RunDeals
      </span>
    </div>
  )
}

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const stats = useDashboardStats()

  return (
    <div className="min-h-screen bg-background">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[236px] flex-none flex-col bg-[#101215] p-4 pt-6 md:flex">
        <div className="pb-[30px]">
          <Brand />
        </div>
        <NavLinks />
        <div className="mt-auto flex items-center gap-[9px] border-t border-border px-2.5 pt-3">
          <span className="relative flex h-2 w-2 shrink-0 rounded-full bg-primary shadow-[0_0_0_3px_oklch(0.74_0.17_153_/_0.18)]" />
          <span className="text-xs text-faint">
            {stats.data?.last_scrape
              ? `Last scraped ${formatRelativeTime(stats.data.last_scrape)}`
              : 'Not scraped yet'}
          </span>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border bg-[#101215] px-4 md:hidden">
        <Brand />
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setMobileOpen((o) => !o)}
          aria-label="Toggle navigation"
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </Button>
      </header>

      {/* Mobile slide-down menu */}
      {mobileOpen && (
        <div className="sticky top-16 z-20 border-b border-border bg-[#101215] p-3 md:hidden">
          <NavLinks onNavigate={() => setMobileOpen(false)} />
        </div>
      )}

      {/* Main content */}
      <main className="md:pl-[236px]">
        <div className="p-4 sm:p-6 lg:px-[34px] lg:py-[30px]">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
