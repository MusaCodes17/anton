/**
 * Page title + optional count, meta line, description and right-aligned actions.
 *
 * Signal redesign: the title is the template's display voice (Bricolage
 * Grotesque LIGHT, tight tracking, 0.98 leading). The old mono eyebrow above
 * the title is gone — it only repeated the title. The count reads as a mono
 * figure set beside the title, like the template's stat superscripts.
 */
export default function PageHeader({ title, count, meta, description, children }) {
  const metaItems = (meta || []).filter(Boolean)
  return (
    <div className="mb-5 flex flex-row items-end justify-between gap-3 sm:mb-8 sm:gap-4">
      <div className="min-w-0">
        <h1 className="font-heading text-[34px] font-light leading-[0.98] tracking-display text-foreground sm:text-[46px]">
          {title}
          {count != null && (
            <sup className="ml-2 align-top font-mono text-xs font-normal tracking-normal text-primary sm:text-sm">
              {count}
            </sup>
          )}
        </h1>
        {/* Template .hero-meta: mono facts separated by small signal dots. */}
        {metaItems.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-muted-foreground">
            {metaItems.map((item) => (
              <span key={item} className="inline-flex items-center gap-2">
                <span className="h-1 w-1 rounded-full bg-primary/70" aria-hidden="true" />
                {item}
              </span>
            ))}
          </div>
        )}
        {description && (
          <p className="mt-2 max-w-[60ch] text-sm font-light text-secondary-foreground sm:text-md-plus">{description}</p>
        )}
      </div>
      {children && <div className="flex shrink-0 items-center gap-2.5">{children}</div>}
    </div>
  )
}
