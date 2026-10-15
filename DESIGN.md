---
name: Signal
description: A calm dark instrument for one runner's own data, with deep ink, one cool signal-blue accent, light grotesque display type and mono figures.
colors:
  ink: "#070a13"
  panel-ink: "#05070d"
  ink-2: "#0c1121"
  ink-3: "#121933"
  text: "#e9ecf5"
  text-2: "#b8bfd5"
  mute: "#848ba5"
  faint: "#7a819b"
  signal: "#8db5ff"
  signal-deep: "#2b56c9"
  signal-wash: "rgba(141, 181, 255, 0.1)"
  glow: "rgb(176, 222, 255)"
  glow-soft: "rgba(176, 222, 255, 0.45)"
  hairline: "rgba(160, 182, 235, 0.14)"
  hairline-strong: "rgba(160, 182, 235, 0.22)"
  divider: "rgba(160, 182, 235, 0.09)"
  nav-inactive: "#3d4b6d"
  ok: "#4fcf9f"
  warn: "#f0b64e"
  alert: "#ff6b7d"
  strava: "oklch(0.7 0.18 45)"
  photo: "#eef0f5"
  chart-grid: "rgba(160, 182, 235, 0.11)"
  chart-1: "#5ad1d8"
  chart-2: "#ff8a6a"
  chart-3: "#c8f032"
  chart-4: "#b49cff"
  chart-5: "#ff79c6"
  chart-6: "#d9b98a"
typography:
  display:
    fontFamily: "Bricolage Grotesque, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "46px"
    fontWeight: 300
    lineHeight: 0.98
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Bricolage Grotesque, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "24px"
    fontWeight: 300
    lineHeight: 1.25
    letterSpacing: "-0.035em"
  stat:
    fontFamily: "Bricolage Grotesque, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "26px"
    fontWeight: 300
    letterSpacing: "-0.035em"
    fontFeature: "\"tnum\" 1"
  title:
    fontFamily: "Hanken Grotesk, Helvetica Neue, Helvetica, Arial, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.25
  body:
    fontFamily: "Hanken Grotesk, Helvetica Neue, Helvetica, Arial, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "IBM Plex Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "11px"
    fontWeight: 500
    letterSpacing: "0.06em"
  figure:
    fontFamily: "IBM Plex Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
    fontFeature: "\"tnum\" 1"
rounded:
  tag: "5px"
  field: "10px"
  menu: "12px"
  tile: "14px"
  panel: "16px"
  pill: "9999px"
spacing:
  page-phone: "16px"
  page-tablet: "24px"
  page-desktop: "30px 34px"
  panel-phone: "16px"
  panel-desktop: "24px"
  sidebar-width: "236px"
components:
  button-primary:
    backgroundColor: "{colors.signal-deep}"
    textColor: "#ffffff"
    rounded: "{rounded.pill}"
    padding: "8px 20px"
    height: "40px"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.text-2}"
    rounded: "{rounded.pill}"
    padding: "8px 20px"
    height: "40px"
  button-outline-hover:
    backgroundColor: "{colors.signal-wash}"
    textColor: "{colors.text}"
  button-secondary:
    backgroundColor: "{colors.ink-3}"
    textColor: "{colors.text-2}"
    rounded: "{rounded.pill}"
    padding: "8px 20px"
    height: "40px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.mute}"
    rounded: "{rounded.pill}"
    padding: "8px 20px"
    height: "40px"
  button-signal:
    backgroundColor: "transparent"
    textColor: "{colors.signal}"
    rounded: "{rounded.pill}"
    padding: "8px 20px"
    height: "40px"
  button-signal-hover:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.ink}"
  badge-signal:
    backgroundColor: "{colors.signal-wash}"
    textColor: "{colors.signal}"
    typography: "{typography.figure}"
    rounded: "{rounded.tag}"
    padding: "3px 8px"
  card-panel:
    backgroundColor: "{colors.panel-ink}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "24px"
  input-field:
    backgroundColor: "{colors.ink-2}"
    textColor: "{colors.text}"
    rounded: "{rounded.field}"
    padding: "8px 12px"
    height: "40px"
  nav-item-active:
    backgroundColor: "{colors.ink-3}"
    textColor: "{colors.text}"
    rounded: "{rounded.pill}"
    padding: "10px 14px"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.mute}"
    rounded: "{rounded.pill}"
    padding: "10px 14px"
---

# Design System: Signal

## Overview

**Creative North Star: "The Athlete's Instrument"**

Signal is a calm instrument panel for one runner's own data. The ground is deep ink. Panels sit darker than the ground, and a soft signal-blue glow rises behind each panel's top edge. A single cool blue accent marks everything the runner can act on. Display type is a light grotesque set large and tight. Every number, unit and date is set in mono, so data reads like a readout rather than marketing copy. The system was extracted from the user-pinned visual source `frontend/template/redesign-template.html` and adapted to a working app shell. Where the shipped build differs from the template (for example, the panel glow is drawn as a `::before` gradient instead of the template's blurred blob, so panels never clip tooltips), the build is canonical.

There is one look, and it is dark (`color-scheme: dark`). There is no light variant and no theme toggle. Density is moderate: on the phone it supports quick one-handed glances right after a run, and on desktop it holds deeper analysis. Shell chrome stays quiet so the accent stays rare. The system rejects the generic green-on-charcoal SaaS dashboard made of stacked, equal-weight cards.

**Key Characteristics:**
- Deep ink ground with tonal ink layers and blue-tinted alpha hairlines (never neutral greys).
- One signal blue for actions, links, active navigation and chart lines.
- Green, amber and red appear only as ok, warning and alert states.
- Bricolage Grotesque light for display and stat values, Hanken Grotesk for body text, IBM Plex Mono for labels, units, dates and tabular figures.
- The glowing panel and the lit pill are the two signature moves.
- One easing curve. Motion is slow and quiet, and it stops entirely under reduced motion.

## Colors

A near-monochrome ink palette with one cool accent, three reserved status hues and one third-party exception.

### Primary
- **Signal Blue** (`signal`): the only action colour. It is used for links, the active nav dot and the tab-bar indicator, focus rings, the caret, count superscripts beside page titles, the signal button and badge, the price chart's Target line and the live dot. The `signal-wash` (10% alpha) fill is the hover and selected wash for quiet controls.
- **Deep Signal** (`signal-deep`): the body of the lit primary pill and the checked switch track. Nothing else uses it.
- **Glow** (`glow`, `glow-soft`): light only. It is used for the lit pill's hover current, the checked switch's bloom, and the glow behind panels (signal at 5–26% alpha). It is never used as a fill or as a text colour.

### Secondary
- **Status Green** (`ok`), **Status Amber** (`warn`), **Status Red** (`alert`): these mean good, warning and alert. Examples are a fresh vs. stale scrape dot, retirement thresholds and destructive actions. A status badge pairs its hue with a word, so the state never depends on colour alone.

### Tertiary
- **Strava Orange** (`strava`, OKLCH): the single third-party exception, used only to mark runs backfilled from the Strava archive (`source='strava'`). It is a borrowed brand mark and stays outside the signal palette.
- **Retailer series** (`chart-1` … `chart-6`): categorical lines for retailers in price-history charts only. These colours have no meaning outside charts. Signal blue is left out of the series on purpose because it already marks the Target line.

### Neutral
- **Ink** (`ink`): the page ground.
- **Panel Ink** (`panel-ink`): panels, the sidebar and the phone bars. Panels sit *darker* than the ground.
- **Ink 2** (`ink-2`): popovers, input fields, and tiles or rows nested inside a panel.
- **Ink 3** (`ink-3`): raised control fill, used for the secondary button and the active nav pill.
- **Text / Text 2 / Mute / Faint**: primary copy, secondary copy, muted meta (5.7:1 on ink) and field captions or placeholders (≥ 4.5:1 on every ink layer).
- **Hairlines**: blue-tinted alpha. `hairline` (14%) is the default border, `hairline-strong` (22%) is used for input borders, dashed add-borders and hover edges, and `divider` (9%) separates rows inside a panel.
- **Photo** (`photo`): a cool near-white backdrop behind product photos, which are shot on white.

### Named Rules
**The One Signal Rule.** Signal blue means "you can act here" or "this is live." Do not use it for decoration, section tints or illustration.

**The Status-Only Rule.** Green, amber and red appear only when a state is ok, warning or alert. Decorative use of a status hue is a defect.

**The Borrowed Mark Rule.** Strava orange is the only foreign hue in the UI, and it appears only on Strava-sourced runs.

**The Token-Only Rule.** Components take colour from the `index.css` custom properties through Tailwind's `color-mix` token helper (so `/N` alpha modifiers work). Never write hex in a component.

## Typography

**Display Font:** Bricolage Grotesque (with Helvetica Neue, Arial fallback)
**Body Font:** Hanken Grotesk (with Helvetica Neue, system-ui fallback)
**Label/Mono Font:** IBM Plex Mono (with ui-monospace, Menlo fallback)

**Character:** The display face is set light (300) and tight (-0.035em). Large titles therefore read as calm and precise rather than shouted. A plain humanist grotesque carries the working text. Mono marks everything that is data.

### Hierarchy
- **Display** (300, 34px phone / 46px desktop, 0.98 leading, -0.035em): page titles only, via the shared page header. Detail pages scale it down (30px/38px).
- **Headline** (300, 24px): dialog titles and the main heading inside a section.
- **Stat** (300, 20px phone / 26px desktop, tabular): headline numbers in panels, such as fitness, predictions and PBs. Stat values use the display face, not mono.
- **Title** (600, 15px, 1.25): panel titles, in Hanken Grotesk.
- **Body** (400, 14px, 1.55): all working copy. Descriptions are capped at 60ch.
- **Label** (500, 11px, 0.06em, UPPERCASE, faint): field captions directly above a value, and table column headers.
- **Figure** (400, 12px mono, tabular): units, dates, paces, the count superscript beside a page title, and meta lines. The meta line separates its items with 4px signal dots.

### Named Rules
**The Mono-Means-Data Rule.** If it is a number, unit, date or pace, set it in mono with tabular figures (`.font-mono` is always tabular). If it is prose, never set it in mono.

**The Light Display Rule.** Bricolage Grotesque is always weight 300 with -0.035em tracking. A bold display face is off-system.

**The Caption-Not-Kicker Rule.** A mono uppercase label captions a *value* or a table column. It never sits above a heading as an eyebrow.

## Layout

The shell keeps the app's navigation model. On desktop (≥ 768px), a fixed 236px panel-ink sidebar sits on the left. It holds the wordmark, the nav pills, a pinned Settings link and a mono status line with a scrape-freshness dot. On phones, the layout is a glass top bar, then the scrolling page, then a 5-tab glass bar at the bottom. That bar respects `safe-area-inset-bottom` and hides when the keyboard is open.

Page padding steps from `page-phone` to `page-tablet` to `page-desktop`. Panels pad 16px on phones and 24px from `sm` up. The page header sits 20px (phone) or 32px (desktop) above content, with actions aligned to the title's baseline. On Home only, the WebGL iridescence blooms behind the top-right of the content. Without WebGL it falls back to a blurred CSS radial glow. Every surface must work at about 380px.

**The Kept Shell Rule.** The desktop sidebar plus the phone tab bar is the navigation. Restyle it, but do not replace it with a hamburger menu or top tabs.

**The Glass-Where-It-Scrolls Rule.** Translucent glass (78% panel ink, 18px blur) is only used on chrome that content actually scrolls under or beside: the phone top bar and the phone tab bar.

## Elevation & Depth

Depth comes from light, not lift. The page is flat ink. Panels are darker than the ground and are separated by a hairline, a very long, soft black drop shadow, and a signal glow rising from behind the top edge. On hover the glow cross-fades brighter over 0.7s. Floating layers (dialogs, menus, toasts) use the same long, soft black shadow at larger sizes. Brightness, not shadow, signals interactivity.

### Shadow Vocabulary
- **Panel drop** (`0 40px 90px -50px rgba(0,0,0,1)`): every panel.
- **Panel glow** (`radial-gradient(9rem 9rem at 50% 0, signal 16% → 5% → transparent)` at rest, 26% → 8% on hover): the rising light behind each panel's top edge.
- **Dialog** (`0 50px 100px -40px rgba(0,0,0,1)`), **Toast** (`0 30px 70px -30px rgba(0,0,0,1)`), **Menu/Select** (`0 24px 60px -24px rgba(0,0,0,0.9)`): floating layers.
- **Lit pill at rest** (`inset 0 1px 0 rgba(255,255,255,0.16), 0 12px 30px -14px rgba(43,86,201,0.9)`) and **lit** (`inset 0 0 1px glow, inset 0 0 10px glow-soft, 0 0 18px glow-soft, 0 0 52px rgba(43,86,201,0.5)`).
- **Point glow** (`0 0 8px currentColor` / `var(--primary)`): live dots, the active nav dot, status dots, and the tab-bar indicator (10px).

### Named Rules
**The Light-Not-Lift Rule.** Elements never translate upward on hover. Interactivity shows as light: the glow brightens, a hairline sharpens, or a wash appears.

**The Panels-Don't-Clip Rule.** The panel glow is an isolated pseudo-element, so panels never need `overflow: hidden` and never clip chart tooltips, popovers or focus rings.

## Shapes

The shape language is soft and rounded. Corners step down as elements get smaller: panels are 16px, compact panels and image cards 14px, menus and selects 12px, fields and skeletons 10px, and tags 5px. Every button, nav item and segmented control is a full pill. Borders are always 1px blue-tinted hairlines. Dashed hairlines (`hairline-strong`) mark "add" slots. Image slots show 6px diagonal ink hatching until a photo loads. After that, the photo sits on the cool `photo` backdrop.

## Components

### Buttons
Pills throughout. Exactly one is lit.
- **Shape:** full pill (`rounded.pill`). Sizes are 36px (sm), 40px (default) and 44px (lg).
- **Primary (lit pill):** a deep-signal body with white text, a 40% pale-blue border and a top inner highlight. On hover or focus the border turns white and current runs through the pill: a tight inner glow and a short bloom over 0.4s.
- **Outline:** a strong-hairline border on a 2% text-tinted fill, in text-2. On hover the border turns half signal, with a signal wash and text-colour copy.
- **Secondary:** ink-3 fill with a hairline border.
- **Ghost:** mute text. On hover it gets a signal wash and text-colour copy.
- **Signal:** a half-signal border with signal text that floods solid signal on hover.
- **Destructive:** an alert-hued outline that floods solid alert on hover.
- **Focus:** a 2px signal ring offset from the ink. This is shared with custom links through `.focus-ring`.

### Chips
- **Style (Badge):** a small mono tag (5px radius, 11px). Each tag has a hairline in its own hue at about 45%, over a 10% wash of that hue. Variants are signal, ok, warn, alert, strava, secondary (ink-3) and outline.
- **Deal flag:** a solid signal tag with ink text showing "% OFF", with a faint signal point glow. It is used on product images.

### Cards / Containers
- **Corner Style:** 16px (panel) or 14px (compact panel, product card).
- **Background:** panel ink, darker than the ground.
- **Shadow Strategy:** the panel drop plus the panel glow (see Elevation & Depth).
- **Border:** 1px hairline. Proposal cards use the stronger hairline.
- **Internal Padding:** 16px phone, 24px desktop. Content inside a panel is a list of rows separated by `divider` hairlines, or ink-2 tiles. A panel never contains another panel.

### Inputs / Fields
- **Style:** an ink-2 fill with a strong-hairline border, 10px radius, 40px tall and a faint placeholder.
- **Focus:** the border shifts to 60% signal, with a 3px signal halo at 20%. There is no offset ring.
- **Hover:** the border sharpens to `hairline-strong`.
- **Disabled:** 50% opacity, not-allowed cursor.
- **Switch:** an ink-3 track that turns deep signal with a soft glow when checked.

### Navigation
- **Sidebar item:** a pill (10px × 14px padding, 14px medium text) with a 6px leading dot. When inactive, the text is mute and the dot is slate (`nav-inactive`). Hover adds a signal wash. When active, the pill is ink-3 with an inner hairline, the text is text-colour and the dot is lit signal with a point glow.
- **Phone tab bar:** five 56px tabs on glass. When a tab is active, its icon turns signal and a 2px glowing signal bar appears along its top edge. Tapping the active tab again scrolls its page back to the top.
- **Status line:** at the foot of the sidebar, a scrape-freshness dot (ok within 48h, warn after that, faint if the site has never been scraped) followed by mono 11px meta.

### Page Header
A light display title, with an optional mono count set as a signal superscript. Below it is a mono meta line whose items are separated by small signal dots, then an optional light description. Actions sit to the right. There is no eyebrow above the title.

### Live Dot
A 6px current-colour dot with a point glow. A ring expands from it every 2.4s. It marks only data that is live right now, such as the assistant being connected or streaming.

### Motion
- **Easing:** one curve, `cubic-bezier(0.6, 0, 0.2, 1)` (`ease-signal`). Controls transition over 0.3–0.4s and the panel glow over 0.7s.
- **Tick-fade:** three signal dots brighten in sequence (1.2s, staggered 0.2s). This is the "working" indicator, used while the assistant is thinking.
- **Pulse ring:** only on live data, through the live dot.
- **Reduced motion:** under `prefers-reduced-motion: reduce`, every transition collapses and every animation stops. The WebGL bloom renders a single still frame.

## Do's and Don'ts

### Do:
- **Do** route every colour through an `index.css` custom property and its Tailwind token. Use `/N` modifiers for alpha.
- **Do** use the lit pill for the one primary action in a view, and quiet outline, ghost or signal pills for everything else.
- **Do** set every number, unit, date and pace in IBM Plex Mono with tabular figures. Stat headline values use light Bricolage Grotesque.
- **Do** divide a panel's content into rows with `divider` hairlines, or into ink-2 tiles.
- **Do** pair every status hue with a word or icon.
- **Do** use `ease-signal` for every transition, and check both desktop and about 380px.

### Don't:
- **Don't** put an eyebrow kicker (a small uppercase label) above a heading or page title. Mono uppercase labels caption values and table columns only.
- **Don't** nest a card or panel inside another card or panel. Use hairline-divided rows or ink-2 tiles.
- **Don't** write hex or rgb colour literals in components.
- **Don't** use signal blue as decoration, or green, amber or red for anything but status.
- **Don't** pulse anything that isn't live data, and don't add easings beyond the one curve.
- **Don't** set Bricolage Grotesque heavier than 300, or use it for body copy.
- **Don't** add a light theme or a second accent hue.
