import { Suspense, useEffect, useRef } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Home, Activity, Tag, Sparkles, Settings as SettingsIcon, LogOut } from 'lucide-react'
import { cn } from '@/lib/utils'
import { authApi, UNAUTHENTICATED_EVENT } from '@/services/api'
import { useDashboardStats } from '@/hooks/useApi'
import { formatRelativeTime } from '@/lib/utils'
import BrandMark from '@/components/layout/BrandMark'
import ShoeIcon from '@/components/icons/ShoeIcon'
import { RowSkeleton } from '@/components/StatusViews'
import OfflineIndicator from '@/components/pwa/OfflineIndicator'
import { useKeyboardViewport } from '@/hooks/useKeyboardViewport'
import { useResumeRefresh } from '@/hooks/useResumeRefresh'

// `short` is the bottom tab bar label (five tabs at 380px leave ~76px each);
// `also` lists child routes that should light the tab, e.g. an activity
// opened from Training keeps Training active.
const navItems = [
  { to: '/', label: 'Home', short: 'Home', icon: Home, end: true, also: ['/new-runs'] },
  { to: '/training', label: 'Training', short: 'Training', icon: Activity, also: ['/activities'] },
  { to: '/shoes', label: 'Shoes', short: 'Shoes', icon: ShoeIcon },
  { to: '/deals', label: 'Deals', short: 'Deals', icon: Tag },
  { to: '/assistant', label: 'Son of Anton', short: 'Anton', icon: Sparkles },
]

// Sidebar scrape-status dot: green within two days of the last scrape, amber
// once it's older (the schedule is nightly), muted when never scraped.
const SCRAPE_FRESH_MS = 48 * 36e5
function scrapeDot(lastScrape) {
  if (!lastScrape) return 'bg-faint'
  return Date.now() - new Date(lastScrape).getTime() <= SCRAPE_FRESH_MS
    ? 'bg-success shadow-[0_0_8px_var(--success)]'
    : 'bg-warning shadow-[0_0_8px_var(--warning)]'
}

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
              // Template .tab[aria-selected]: the active row is a raised ink-3
              // pill with a hairline inset; its dot is lit signal.
              'focus-ring flex items-center gap-3 rounded-full px-3.5 py-[10px] text-sm font-medium transition-colors duration-300 ease-signal',
              isActive
                ? 'bg-secondary text-foreground shadow-[inset_0_0_0_1px_var(--input)]'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            )
          }
        >
          {({ isActive }) => (
            <>
              <span
                className={cn(
                  'h-1.5 w-1.5 shrink-0 rounded-full transition-colors duration-300',
                  isActive ? 'bg-primary shadow-[0_0_8px_var(--primary)]' : 'bg-nav-inactive'
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
          'focus-ring flex items-center gap-3 rounded-full px-3.5 py-[10px] text-sm font-medium transition-colors duration-300 ease-signal',
          isActive
            ? 'bg-secondary text-foreground shadow-[inset_0_0_0_1px_var(--input)]'
            : 'text-muted-foreground hover:bg-accent hover:text-foreground'
        )
      }
    >
      <Icon className="h-[15px] w-[15px] shrink-0" />
      {label}
    </NavLink>
  )
}

// Mobile primary navigation (UI tab-bar pass). Five destinations in thumb
// reach, replacing the old hamburger + slide-down menu. A static shrink-0
// child of the shell (not position:fixed), so it can't overlap content and
// needs no matching padding on every page. Hidden while the iOS keyboard is
// up (html.keyboard-open) so the chat composer sits directly on the keyboard.
function MobileTabBar({ onReselect }) {
  const { pathname } = useLocation()
  const isActive = ({ to, end, also = [] }) => {
    const hit = (p) => pathname === p || pathname.startsWith(`${p}/`)
    return (end ? pathname === to : hit(to)) || also.some(hit)
  }
  return (
    <nav
      aria-label="Primary"
      className="glass-bar grain relative z-30 grid shrink-0 grid-cols-5 border-t border-border pb-[env(safe-area-inset-bottom)] md:hidden [.keyboard-open_&]:hidden"
    >
      {navItems.map((item) => {
        const active = isActive(item)
        const Icon = item.icon
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            aria-current={active ? 'page' : undefined}
            // Tapping the tab you're already on returns to the top (iOS convention).
            onClick={() => active && onReselect()}
            className={cn(
              'focus-ring relative flex h-14 flex-col items-center justify-center gap-1 text-2xs font-medium transition-colors duration-300 ease-signal',
              active ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {/* Active tab: a lit signal filament on the bar's top edge. */}
            {active && (
              <span className="absolute top-0 h-[2px] w-6 rounded-full bg-primary shadow-[0_0_10px_var(--primary)]" />
            )}
            <Icon className={cn('h-[22px] w-[22px]', active && 'text-primary')} strokeWidth={1.6} />
            {item.short}
          </NavLink>
        )
      })}
    </nav>
  )
}

// RA2.1 logout — clears the session cookie server-side, then fires the app-wide
// unauthenticated event so AuthGate drops back to the login view. Dispatches the
// event even if the request fails, so a click always returns the user to login.
export function LogoutButton({ onNavigate }) {
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
      className="focus-ring flex w-full items-center gap-3 rounded-full px-3.5 py-[10px] text-sm font-medium text-muted-foreground transition-colors duration-300 ease-signal hover:bg-accent hover:text-foreground"
    >
      <LogOut className="h-[15px] w-[15px] shrink-0" />
      Sign out
    </button>
  )
}

// The logo is always a way home: it links to "/" and, because <main> (not the
// document) is the scroll region, also resets that scroll when already there.
function Brand({ onHome }) {
  return (
    <Link
      to="/"
      onClick={onHome}
      aria-label="Anton — home"
      className="focus-ring flex items-center gap-2.5 rounded-full px-2"
    >
      {/* Template .logo-mark: a hairline-framed tile, the mark lit in signal. */}
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px] border border-input text-primary">
        <BrandMark className="h-[17px] w-[17px]" />
      </span>
      <span className="font-heading text-[21px] font-light tracking-display text-foreground">
        Anton
      </span>
    </Link>
  )
}

export default function Layout() {
  // Not React Query's refetchOnWindowFocus: that fires on every focus (the storm).
  useResumeRefresh()
  const stats = useDashboardStats()
  const location = useLocation()
  // Chat manages its own internal scroll regions and needs the full
  // viewport height with no page padding — every other route gets the
  // standard padded, naturally-scrolling page wrapper.
  const isFullBleed = location.pathname === '/assistant'
  useKeyboardViewport()

  // <main> is the scroll container, so the browser's own scroll reset on
  // navigation never happens — without this, opening Home from halfway down
  // Deals lands halfway down Home.
  const mainRef = useRef(null)
  const scrollToTop = () => mainRef.current?.scrollTo({ top: 0 })
  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0 })
  }, [location.pathname])

  return (
    // RA2.2 (R5.2) — fixed-height app shell. Header + banner are static shrink-0
    // children OUTSIDE the scroll region, and only <main> scrolls (min-h-0 +
    // overflow-y-auto). This replaces the old min-h-[100dvh] document-scroll +
    // sticky-header approach, whose sticky header intermittently scrolls off in
    // iOS standalone mode. 100dvh (not 100vh) so iOS toolbars don't hide chrome.
    // pt reserves the iOS status-bar inset: black-translucent + viewport-fit=cover
    // paint web content UNDER the notch, so the app must inset the top itself —
    // nothing else does. The bottom inset is owned by MobileTabBar on phones.
    // A no-op wherever the inset is 0 (desktop browsers / non-notched devices).
    // --app-height is set only while the iOS keyboard is up (useKeyboardViewport)
    // so the shell shrinks to the space above it instead of being panned away.
    <div className="flex h-[var(--app-height,100dvh)] flex-col bg-background pt-[env(safe-area-inset-top)]">
      {/* Offline banner — static, above the header. */}
      <div className="z-40 shrink-0">
        <OfflineIndicator />
      </div>

      {/* Desktop sidebar */}
      <aside className="grain fixed inset-y-0 left-0 z-30 hidden w-[236px] flex-none flex-col border-r border-border bg-sidebar p-4 pt-6 md:flex">
        <div className="pb-[30px]">
          <Brand onHome={scrollToTop} />
        </div>
        <NavLinks />
        <div className="mt-auto border-t border-border pt-3">
          <SettingsLink />
          <LogoutButton />
        </div>
        {/* Template .header-status: a mono status line with a live dot. */}
        <div className="mt-3 flex items-center gap-2.5 border-t border-border px-3 pt-3">
          {/* Static, coloured by freshness: a pulse would claim live activity
              (surface brief: pulses only on live data). */}
          <span
            aria-hidden="true"
            className={cn('h-1.5 w-1.5 shrink-0 rounded-full', scrapeDot(stats.data?.last_scrape))}
          />
          <span className="font-mono text-2xs text-muted-foreground">
            {stats.data?.last_scrape
              ? `Last scraped ${formatRelativeTime(stats.data.last_scrape)}`
              : 'Not scraped yet'}
          </span>
        </div>
      </aside>

      {/* Mobile top bar — brand + Settings gear (Settings is plumbing, kept out
          of the tab bar). Static shrink-0 child outside the scroll region, so it
          can't scroll off. Hidden on full-bleed chat, whose own header replaces
          it so the phone shows one bar, not two. */}
      <header
        className={cn(
          'glass-bar grain relative z-30 flex h-14 shrink-0 items-center justify-between border-b border-border pl-2.5 pr-1.5 md:hidden',
          isFullBleed && 'hidden'
        )}
      >
        <Brand onHome={scrollToTop} />
        <NavLink
          to="/settings"
          aria-label="Settings"
          className={({ isActive }) =>
            cn(
              'focus-ring flex h-11 w-11 items-center justify-center rounded-full transition-colors duration-300 ease-signal hover:bg-accent',
              isActive ? 'text-primary' : 'text-muted-foreground'
            )
          }
        >
          <SettingsIcon className="h-5 w-5" />
        </NavLink>
      </header>

      {/* Main is the single scroll region for all routes: flex-1 fills the height
          left between header and tab bar, min-h-0 lets it shrink so
          overflow-y-auto scrolls the body rather than the shell. Full-bleed
          (chat) just fills this box and ChatPage's own h-full takes over its
          internal scrolling; padded routes scroll here. */}
      <main ref={mainRef} className="min-h-0 flex-1 overflow-y-auto md:pl-[236px]">
        {/* Suspense sits here, inside the shell, so the header and tab bar stay
            mounted while a lazily-loaded route chunk is fetched (App.jsx). The
            fallback reuses the existing RowSkeleton, in the same padding the
            page itself would use. */}
        <Suspense
          fallback={
            isFullBleed ? (
              <div className="p-4 sm:p-6">
                <RowSkeleton count={5} />
              </div>
            ) : (
              <div className="p-4 sm:p-6 lg:px-[34px] lg:py-[30px]">
                <RowSkeleton count={5} />
              </div>
            )
          }
        >
          {isFullBleed ? (
            <Outlet />
          ) : (
            // pb-8 on mobile: the tab bar sits below <main>, so no FAB or
            // home-indicator clearance is needed any more; sm:p-6 restores
            // normal padding on wider screens.
            <div className="p-4 pb-4 sm:pb-8 sm:p-6 lg:px-[34px] lg:py-[30px]">
              <Outlet />
            </div>
          )}
        </Suspense>
      </main>

      <MobileTabBar onReselect={scrollToTop} />
    </div>
  )
}
