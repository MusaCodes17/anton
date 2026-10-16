import { Link, NavLink } from 'react-router-dom'
import { LogIn } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Brand, ThemeToggle, ScrapeStatus } from '@/components/layout/Layout'

// R9.4: logged-out shell. Same chrome as Layout, reduced to Deals / theme /
// Sign in. HARD RULE: no authed hook may be used here (no useDashboardStats,
// no useResumeRefresh) — a 401 burns the visitor's rate-limit bucket and fires
// UNAUTHENTICATED_EVENT. The scrape line is fed by the caller from the public
// payload's checked_at.
const rowClass =
  'focus-ring flex w-full items-center gap-3 rounded-full px-3.5 py-[10px] text-sm font-medium text-muted-foreground transition-colors duration-300 ease-signal hover:bg-accent hover:text-foreground'

export default function PublicLayout({ children, lastScrape }) {
  return (
    <div className="flex h-[var(--app-height,100dvh)] flex-col bg-background pt-[env(safe-area-inset-top)]">
      {/* Desktop sidebar */}
      <aside className="grain fixed inset-y-0 left-0 z-30 hidden w-[236px] flex-none flex-col border-r border-border bg-sidebar p-4 pt-6 md:flex">
        <div className="pb-[30px]">
          <Brand to="/deals" />
        </div>
        <nav className="flex flex-col gap-1">
          <NavLink
            to="/deals"
            className={({ isActive }) =>
              cn(
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
                Deals
              </>
            )}
          </NavLink>
        </nav>
        <div className="mt-auto border-t border-border pt-3">
          <ThemeToggle />
          {/* Logged-out "/" renders the login view (AuthGate). */}
          <Link to="/" className={rowClass}>
            <LogIn className="h-[15px] w-[15px] shrink-0" />
            Sign in
          </Link>
        </div>
        <ScrapeStatus lastScrape={lastScrape} />
      </aside>

      {/* Mobile top bar — no tab bar on the public shell. */}
      <header className="glass-bar grain relative z-30 flex h-14 shrink-0 items-center justify-between border-b border-border pl-2.5 pr-1.5 md:hidden">
        <Brand to="/deals" />
        <div className="flex items-center">
          <ThemeToggle compact />
          <Link
            to="/"
            aria-label="Sign in"
            className="focus-ring flex h-11 w-11 items-center justify-center rounded-full text-muted-foreground transition-colors duration-300 ease-signal hover:bg-accent hover:text-foreground"
          >
            <LogIn className="h-5 w-5" />
          </Link>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto md:pl-[236px]">
        <div className="p-4 pb-4 sm:pb-8 sm:p-6 lg:px-[34px] lg:py-[30px]">{children}</div>
      </main>
    </div>
  )
}
