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

THESIS: Anton reads like a calm instrument for one athlete's own data. The template's language (deep ink, one cool signal accent, light grotesque display, mono figures) is applied to a working app shell. It refuses the generic green-on-charcoal SaaS dashboard of stacked, same-weight cards.

OWN-WORLD: Ink ground #070a13 with ink-2/ink-3 layers and hairlines in blue-tinted alpha. One signal blue (#8db5ff, deep #2b56c9) for actions, links, active nav and chart lines. Green, amber and red appear only as ok/warn/alert. Bricolage Grotesque light (200–300) for display and stat values, Hanken Grotesk for body, IBM Plex Mono for labels, units, dates and tabular figures. Panels: near-black, 16px radius, a soft signal glow rising behind the top edge, and divided rows. Pill buttons; the primary is a deep-blue pill that lights up with a glow on hover.

STORY: Within one glance the runner sees the week, the shoe that needs attention and any deal worth acting on. Every action they can take sits on a lit pill.

FIRST VIEWPORT: Desktop: a 236px ink sidebar with a mono status line and a live dot; the page title set in light display type at about 40px, with mono meta beneath. On Home only, the WebGL iridescence (CSS-glow fallback) blooms behind the top-right of the content. Phone: a glass top bar, then the page, then a glass tab bar with signal-blue active state.

FORM: Pinned by the user (template = visual source of truth). No roll, no seed key: brief-pinned direction. Code-led (no image generation available). Signature move: the glowing panel plus the lit signal pill. Live data points pulse as signal dots.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
