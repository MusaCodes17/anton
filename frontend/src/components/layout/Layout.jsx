import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Home, Activity, Tag, PersonStanding, Sparkles, Settings as SettingsIcon, Menu, X, LogOut } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { authApi, UNAUTHENTICATED_EVENT } from '@/services/api'
import { useDashboardStats } from '@/hooks/useApi'
import { formatRelativeTime } from '@/lib/utils'
import BrandMark from '@/components/layout/BrandMark'
import OfflineIndicator from '@/components/pwa/OfflineIndicator'

const navItems = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/training', label: 'Training', icon: Activity },
  { to: '/shoes', label: 'Shoes', icon: PersonStanding },
  { to: '/deals', label: 'Deals', icon: Tag },
  { to: '/assistant', label: 'Son of Anton', icon: Sparkles },
]

const settingsItem = { to: '/settings', label: 'Settings', icon: SettingsIcon }

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
              'focus-ring flex items-center gap-3 rounded-[9px] px-3 py-[11px] text-sm transition-colors',
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
                  isActive ? 'bg-primary' : 'bg-nav-inactive'
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

// Settings is plumbing, not a primary destination — pinned apart from the
// main nav with a gear icon (the standard mobile "behind a gear" pattern).
function SettingsLink({ onNavigate }) {
  const { to, label, icon: Icon } = settingsItem
  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'focus-ring flex items-center gap-3 rounded-[9px] px-3 py-[11px] text-sm transition-colors',
          isActive
            ? 'bg-accent font-bold text-accent-foreground'
            : 'font-medium text-muted-foreground hover:bg-secondary hover:text-foreground'
        )
      }
    >
      <Icon className="h-[15px] w-[15px] shrink-0" />
      {label}
    </NavLink>
  )
}

// RA2.1 logout — clears the session cookie server-side, then fires the app-wide
// unauthenticated event so AuthGate drops back to the login view. Dispatches the
// event even if the request fails, so a click always returns the user to login.
function LogoutButton({ onNavigate }) {
  const handleLogout = async () => {
    try {
      await authApi.logout()
    } catch {
      // ignore — we're logging out regardless
    } finally {
      onNavigate?.()
      window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT))
    }
  }
  return (
    <button
      type="button"
      onClick={handleLogout}
      className="focus-ring flex w-full items-center gap-3 rounded-[9px] px-3 py-[11px] text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
    >
      <LogOut className="h-[15px] w-[15px] shrink-0" />
      Sign out
    </button>
  )
}

function Brand() {
  return (
    <div className="flex items-center gap-[11px] px-2">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary text-background">
        <BrandMark className="h-[19px] w-[19px]" />
      </span>
      <span className="font-heading text-[19px] font-extrabold tracking-tight text-foreground">
        Anton
      </span>
    </div>
  )
}

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const stats = useDashboardStats()
  const location = useLocation()
  // Chat manages its own internal scroll regions and needs the full
  // viewport height with no page padding — every other route gets the
  // standard padded, naturally-scrolling page wrapper.
  const isFullBleed = location.pathname === '/assistant'

  return (
    // RA2.2 (R5.1) — flex column so the mobile header is always a non-shrinking
    // child and the full-bleed child fills only the height left under it, not the
    // whole viewport. 100dvh (not 100vh) so iOS toolbars don't hide the header.
    <div className="flex min-h-[100dvh] flex-col bg-background">
      {/* RA2.2 §3 — offline banner sits above all sticky chrome. */}
      <div className="sticky top-0 z-40 shrink-0">
        <OfflineIndicator />
      </div>

      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[236px] flex-none flex-col bg-sidebar p-4 pt-6 md:flex">
        <div className="pb-[30px]">
          <Brand />
        </div>
        <NavLinks />
        <div className="mt-auto border-t border-border pt-3">
          <SettingsLink />
          <LogoutButton />
        </div>
        <div className="mt-3 flex items-center gap-[9px] border-t border-border px-2.5 pt-3">
          <span className="relative flex h-2 w-2 shrink-0 rounded-full bg-primary shadow-[0_0_0_3px_oklch(0.74_0.17_153_/_0.18)]" />
          <span className="text-xs text-faint">
            {stats.data?.last_scrape
              ? `Last scraped ${formatRelativeTime(stats.data.last_scrape)}`
              : 'Not scraped yet'}
          </span>
        </div>
      </aside>

      {/* Mobile top bar — a non-shrinking flex child so it stays reachable even
          on the full-bleed chat route (the "can't get back" bug). */}
      <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between border-b border-border bg-sidebar px-4 md:hidden">
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
        <div className="sticky top-16 z-20 border-b border-border bg-sidebar p-3 md:hidden">
          <NavLinks onNavigate={() => setMobileOpen(false)} />
          <div className="mt-1 border-t border-border pt-1">
            <SettingsLink onNavigate={() => setMobileOpen(false)} />
            <LogoutButton onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}

      {/* Main content. Full-bleed (chat) gets a definite height equal to the
          space left under the mobile header (h-16 = 4rem), so its inner scroll
          regions resolve without pushing the header off-screen; on md+ the header
          is hidden, so it's the full viewport. Padded routes just fill remaining
          column height and scroll the body. */}
      <main
        className={cn(
          'md:pl-[236px]',
          isFullBleed ? 'h-[calc(100dvh-4rem)] md:h-[100dvh]' : 'flex-1'
        )}
      >
        {isFullBleed ? (
          <Outlet />
        ) : (
          // pb clears the Son-of-Anton FAB (+ home indicator) on mobile; sm:p-6
          // restores normal padding on wider screens.
          <div className="p-4 pb-[calc(6rem+env(safe-area-inset-bottom))] sm:p-6 lg:px-[34px] lg:py-[30px]">
            <Outlet />
          </div>
        )}
      </main>
    </div>
  )
}
