---
version: 1
slug: "frontend-src"
primary_target: "frontend/src"
related_targets: []
---

# Anton app shell (all routes)

Scope: the whole React app in frontend/src, every route, desktop and installed phone PWA. Visitor mode: **Operate**.

Audience and job: one runner. On the phone, fast glances and confirmations right after a run. On desktop, deals, rotation and training analysis. Constraints: preserve all content, routes, behaviour and server-computed numbers. Navigation stays as it is: desktop sidebar plus phone 5-tab bar, restyled. Recharts only. Tokens only, no hex values in components.

## Direction contract

Re-pinned 2026-10-17: the "Horizon" reskin replaces the earlier "Signal" direction (design_decisions E22). DESIGN.md is the system of record; this contract is the surface's thesis.

THESIS: Anton reads like a night ops console for one athlete's own data: warm black, amber readouts, mono labels. The template's language (warm glass panels, one amber accent, bold uppercase display, mono controls) is applied to a working app shell. It refuses the generic green-on-charcoal SaaS dashboard of stacked, same-weight cards, and it refuses pitch black: the dark ground sits one step above the template's near-black.

OWN-WORLD: Warm black ground #141210 with panels #1a1714 and surfaces #221e1a; warm off-white ink #efebe2; hairlines in warm alpha. One Horizon Amber (#ffb45e, deep #b8661f) for actions, links, active nav and chart lines; ice blue #a9caff for secondary readouts. Green, butter yellow and red appear only as ok/warn/alert. Archivo for body and page titles (800, uppercase), Archivo Narrow 700 uppercase as the display voice for card titles and stat figures, JetBrains Mono uppercase for labels, nav, buttons, tags and units. Panels: the template's signature glass, a warm six-gradient mesh with an inset bottom glow, a deep shadow and a 1px gradient rim, 16px radius. Buttons 10px radius, mono uppercase; the primary is filled amber with a soft bloom.

STORY: Within one glance the runner sees the week, the shoe that needs attention and any deal worth acting on. Every action they can take is an amber control.

FIRST VIEWPORT: Desktop: a 236px warm-black sidebar with the mono "ANTON" wordmark on an amber-edged tile, mono uppercase nav with a glowing amber dot on the active item, and a mono status line with a live dot; the page title in Archivo 800 uppercase at about 46px, rising in on load, with mono meta beneath. Behind every page header band, the template's black hole (EventHorizon: one-pass WebGL ray-march, CSS amber glow fallback, none in daylight) sits right of the title, its lensed disc cropped by the band. Phone: a glass top bar, then the page, then a glass tab bar with mono labels and an amber active filament.

FORM: Pinned by the user (template = visual source of truth). No roll, no seed key: brief-pinned direction. Code-led (no image generation). Signature move: the warm glass panel whose amber light sweeps the rim, earned only on hover and on the login card, never on every card at once. Live data points pulse with the latido ring.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance. Review captures (2026-10-17, local throwaway DB copy, animations settled): .impeccable/review/desktop*.jpg at 1280x800, mobile*.jpg at 375x812.
