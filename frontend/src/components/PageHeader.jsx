/** Consistent page title + optional eyebrow label, count, and right-aligned actions. */
export default function PageHeader({ eyebrow, title, count, description, children }) {
  return (
    <div className="mb-4 flex flex-row items-end justify-between gap-3 sm:mb-6 sm:gap-4">
      <div className="min-w-0">
        {eyebrow && (
          <div className="hidden font-mono text-xs font-semibold tracking-[0.14em] text-accent-foreground sm:block">
            {eyebrow}
          </div>
        )}
        <h1 className="text-2xl font-heading font-extrabold tracking-tight text-foreground sm:mt-1.5 sm:text-[30px]">
          {title}
          {count != null && (
            <span className="ml-2 text-lg font-semibold text-faint sm:text-[22px]">{count}</span>
          )}
        </h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {children && <div className="flex shrink-0 items-center gap-3">{children}</div>}
    </div>
  )
}
