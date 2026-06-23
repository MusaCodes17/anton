/** Consistent page title + optional eyebrow label, count, and right-aligned actions. */
export default function PageHeader({ eyebrow, title, count, description, children }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && (
          <div className="font-mono text-xs font-semibold tracking-[0.14em] text-accent-foreground">
            {eyebrow}
          </div>
        )}
        <h1 className="mt-1.5 font-heading text-[30px] font-extrabold tracking-tight text-foreground">
          {title}
          {count != null && (
            <span className="ml-2 text-[22px] font-semibold text-faint">{count}</span>
          )}
        </h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {children && <div className="flex items-center gap-3">{children}</div>}
    </div>
  )
}
