import SavannaHeader, { SavannaWarriorsInline } from '@/components/layout/SavannaHeader'

// The full-bleed hero band. Negative margins cancel Layout's page padding so the
// scene reaches the edges of <main>; sticky + opaque keeps the title pinned.
const BAND_CLASSES =
  'isolate sticky top-0 z-20 -mx-4 -mt-4 mb-4 flex flex-row items-end justify-between gap-3 overflow-hidden border-b border-border bg-background px-4 pb-4 pt-6 sm:-mx-6 sm:-mt-6 sm:mb-6 sm:gap-4 sm:px-6 sm:pb-6 sm:pt-10 lg:-mx-[34px] lg:-mt-[30px] lg:px-[34px] lg:pt-14'
const PLAIN_CLASSES = 'mb-5 flex flex-row flex-wrap items-end justify-between gap-3 sm:mb-8 sm:gap-4'

/**
 * Page title + optional count, meta line, description and right-aligned actions.
 *
 * Horizon redesign: the title is the template's h1 voice (Archivo 800 uppercase,
 * tight tracking, 0.94 leading). The old mono eyebrow above the title is gone —
 * it only repeated the title. The count reads as a mono figure set beside the
 * title, like the template's stat superscripts.
 *
 * The outer element is the full-bleed hero band shared by every page: the
 * negative margins cancel Layout's page padding (p-4 sm:p-6 lg:px-[34px]
 * lg:py-[30px]) so the savanna backdrop (SavannaHeader) reaches the edges of <main>. The band
 * is sticky + opaque so the title and actions stay pinned while content scrolls
 * beneath it. This works because <main> is the scroll container — never add
 * overflow to an ancestor. overflow-hidden clips the backdrop to the band.
 *
 * `plain` is for headers nested inside another page's band (Settings sub-pages),
 * so the animation and sticky band appear once.
 */
export default function PageHeader({ title, count, meta, description, plain = false, children }) {
  const metaItems = (meta || []).filter(Boolean)
  return (
    <div className={plain ? PLAIN_CLASSES : BAND_CLASSES}>
      {!plain && <SavannaHeader />}
      <div className="min-w-0">
        <h1 className="font-sans text-[34px] font-extrabold uppercase leading-[0.94] tracking-[-0.03em] animate-rise text-foreground sm:text-[46px]">
          {title}
          {count != null && (
            <sup className="ml-2 align-top font-mono text-xs font-normal tracking-normal text-primary sm:text-sm">
              {count}
            </sup>
          )}
        </h1>
        {/* Mono facts separated by small accent dots. */}
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
      {!plain && <SavannaWarriorsInline />}
      {children && <div className="flex shrink-0 items-center gap-2.5">{children}</div>}
    </div>
  )
}
