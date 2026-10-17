---
name: Anton
description: A warm-black instrument console for one runner's own data, with a single Horizon Amber accent, bold narrow display type and mono labels.
colors:
  ground: "#141210"
  ink: "#efebe2"
  panel: "#1a1714"
  popover: "#1e1b17"
  rail: "#161411"
  surface: "#221e1a"
  raised: "#282420"
  ink-soft: "#d4cfc4"
  ink-muted: "#a39e92"
  ink-faint: "#908b80"
  nav-inactive: "#463f35"
  horizon-amber: "#ffb45e"
  horizon-amber-hover: "#ffc684"
  amber-deep: "#b8661f"
  amber-on: "#0b0906"
  amber-wash: "rgba(255, 180, 94, 0.12)"
  glow: "rgb(255, 226, 189)"
  sweep-hot: "#ffe2bd"
  ice: "#a9caff"
  ok: "#8be0a4"
  warn: "#f2d16b"
  alert: "#ff6f61"
  strava: "oklch(0.7 0.18 45)"
  photo: "#f1eee8"
  hairline: "rgba(239, 235, 226, 0.14)"
  hairline-input: "rgba(239, 235, 226, 0.30)"
  divider: "rgba(255, 240, 220, 0.10)"
  chart-2: "#e58f6b"
  chart-3: "#c9d77a"
  chart-4: "#c3a6ff"
  chart-5: "#ff8fb1"
typography:
  headline:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "46px"
    fontWeight: 800
    lineHeight: 0.94
    letterSpacing: "-0.03em"
  display:
    fontFamily: "Archivo Narrow, Arial Narrow, Helvetica Neue, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  stat:
    fontFamily: "Archivo Narrow, Arial Narrow, Helvetica Neue, Arial, sans-serif"
    fontSize: "23px"
    fontWeight: 700
    letterSpacing: "-0.01em"
    fontFeature: "\"tnum\" 1"
  body:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "JetBrains Mono, Courier New, ui-monospace, monospace"
    fontSize: "11px"
    fontWeight: 400
    letterSpacing: "0.18em"
  control:
    fontFamily: "JetBrains Mono, Courier New, ui-monospace, monospace"
    fontSize: "12px"
    fontWeight: 500
    letterSpacing: "0.18em"
  tag:
    fontFamily: "JetBrains Mono, Courier New, ui-monospace, monospace"
    fontSize: "10px"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "0.18em"
rounded:
  tag: "6px"
  control: "10px"
  sm: "12px"
  md: "14px"
  panel: "16px"
  pill: "9999px"
spacing:
  xs: "8px"
  sm: "16px"
  md: "24px"
  page: "34px"
  rail: "236px"
components:
  button-primary:
    backgroundColor: "{colors.horizon-amber}"
    textColor: "{colors.amber-on}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    height: "40px"
    padding: "0 20px"
  button-primary-hover:
    backgroundColor: "{colors.horizon-amber-hover}"
  button-outline:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.horizon-amber}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    height: "40px"
    padding: "0 20px"
  button-secondary:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    height: "40px"
    padding: "0 20px"
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "24px"
  input:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    height: "40px"
    padding: "8px 12px"
  badge:
    backgroundColor: "{colors.amber-wash}"
    textColor: "{colors.horizon-amber}"
    typography: "{typography.tag}"
    rounded: "{rounded.tag}"
    padding: "3px 8px"
  nav-item:
    textColor: "{colors.ink-muted}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "10px 14px"
  nav-item-active:
    textColor: "{colors.ink}"
---

# Design System: Anton

## Overview

**Creative North Star: "The Night Ops Console"**

An instrument panel read in the dark: warm black, amber readouts, mono labels; a runner checking data right after a run. The ground is warm black lifted one step off pitch (#141210) because the runner asked for it; it must never read as pure black. Panels are warm glass over that ground, each with a hairline rim, an inset glow along the bottom edge and a deep drop shadow. Everything is the runner's own live data, so the surfaces stay quiet and the numbers carry the screen.

The voice is bold and narrow for titles and figures, mono for everything that is a label, unit or control, and a plain grotesque for reading text. There is exactly one accent, Horizon Amber. Status hues exist only to say ok, warn or alert. The system is glanceable on a phone (about 380 px) and deeper on desktop; the same layout, type and motion serve both themes. Dark is the default; a per-device "daylight" variant re-tones the tokens without forking any component.

The look is taken from the pinned `redesign-template.html` as visual language only. Component philosophy: **"Instrument-precise, warmly lit"** — mono uppercase controls and hairline edges, warmth from the glass and the amber glow.

**Key Characteristics:**
- Warm black ground (#141210), warm off-white ink (#efebe2), never pure black or pure white in dark.
- One accent, Horizon Amber (#ffb45e), for actions, links, active nav and chart lines.
- Glass panels with a six-radial warm mesh, gradient hairline rim and inset bottom glow, with no backdrop blur on cards.
- Archivo Narrow bold uppercase for card and dialog titles and stat figures; Archivo 800 uppercase for page titles; JetBrains Mono for labels, nav, buttons, tags and units.
- Warm alpha hairlines instead of grey borders.
- Motion is rare and earned: page titles rise, live dots pulse, the rim sweep runs on hover or on the login card only.

## Colors

A warm-black and amber palette: every neutral leans toward brown-orange, and one amber carries all emphasis.

### Primary
- **Horizon Amber** (#ffb45e): the only accent. Filled primary buttons, links, active nav dot, focus ring, selection, chart lines, the live dot. Hover steps to Lit Amber (#ffc684).
- **Deep Amber** (#b8661f): the deep body of the accent, used in the panel mesh glow and as the accent's darker partner.
- **Amber Wash** (rgba(255, 180, 94, 0.12)): selected and active fill, row hover (at half strength), tag background at a lighter step.
- **Ink on Amber** (#0b0906): text on filled amber and on status fills.

### Secondary
- **Ice Blue** (#a9caff): secondary readouts and the first chart series. Amber is left out of retailer series because it is the accent and the price chart's Target line.

### Neutral
- **Warm Black Ground** (#141210): the page background.
- **Rail Black** (#161411): sidebar and phone bars, a half step below the ground.
- **Panel Brown-Black** (#1a1714): card and panel fill. Popovers use Popover Umber (#1e1b17).
- **Surface Umber** (#221e1a): nested tiles and rows inside a panel; also the muted fill. Raised controls use Raised Umber (#282420).
- **Warm Off-White Ink** (#efebe2): primary text.
- **Soft Ink** (#d4cfc4), **Muted Ink** (#a39e92), **Faint Ink** (#908b80): secondary text, labels and placeholders. Faint was lifted to keep 4.5:1 on the lighter surfaces.
- **Inactive Nav** (#463f35): inactive tab icons.
- **Hairline** (rgba(239, 235, 226, 0.14)), **Input Edge** (rgba(239, 235, 226, 0.30)), **Divider** (rgba(255, 240, 220, 0.10)): warm alpha borders, input strokes and row dividers.
- **Photo Paper** (#f1eee8): the near-white backdrop behind cut-out product photos.

### Status and data hues
- **Mint OK** (#8be0a4), **Straw Warn** (#f2d16b), **Coral Alert** (#ff6f61): good, warning and alert only.
- **Strava Orange** (oklch(0.7 0.18 45)): a third-party mark for backfilled Strava runs, deliberately outside the accent palette.
- Chart series after ice: #e58f6b, #c9d77a, #c3a6ff, #ff8fb1 (plus Soft Ink as the sixth).

### Daylight (light variant)
`:root[data-theme='light']` keeps layout, type and motion and re-tones the tokens. Warm paper ground (#f4f1ea), cream panels (#fffdf8) lifted above the ground (dark sinks panels below the ink; on paper the depth cue is lift), ink (#1a1712). The accent deepens to #9a5200 so links and figures clear 4.5:1 on cream. Status hues darken (ok #2f7d4a, warn #8a6a00, alert #c2362a), ice becomes #3d6fb8, hairlines become warm brown alpha, and film grain is switched off. The filled primary button (`--lit`) stays #ffb45e in both themes.

### Named Rules
**The One Amber Rule.** Amber is the only accent. Green, yellow and red mean ok, warn and alert and never decorate.

**The Warm Hairline Rule.** Borders and dividers are warm alpha lines, not grey. A grey border breaks the lamp-lit feel.

## Typography

**Display Font:** Archivo Narrow (with Arial Narrow, Helvetica Neue, Arial, sans-serif)
**Body Font:** Archivo (with system-ui, -apple-system, Segoe UI, sans-serif)
**Label/Mono Font:** JetBrains Mono (with Courier New, ui-monospace, monospace)

**Character:** A bold condensed voice for titles and figures set against a precise mono voice for instruments, with a plain grotesque in between for reading.

### Hierarchy
- **Page title** (Archivo 800, 34px / 46px from sm, 0.94 leading, -0.03em, uppercase): the one h1 per page, rising into place on load; an optional count sits beside it as a small mono amber superscript.
- **Display** (Archivo Narrow 700, 18px card titles, 24px dialog titles, -0.01em, uppercase): card and dialog titles.
- **Stat** (Archivo Narrow 700, 23px, tabular numbers): headline figures; sized down per breakpoint when the narrow bold face would truncate.
- **Body** (Archivo 400, 14px, 1.55): reading text and descriptions; page descriptions are light weight, capped at 60ch.
- **Label** (JetBrains Mono, 11px, 0.18em, uppercase, muted ink): section and field labels, units, dates, meta.
- **Control** (JetBrains Mono 500, 12px, 0.18em, uppercase): buttons and nav.
- **Tag** (JetBrains Mono 500, 10px, 0.18em, uppercase): badges and table headers.

### Named Rules
**The Mono Means Data Rule.** Mono uppercase is for labels, nav, buttons, tags and units, and mono figures are always tabular so columns of paces line up. Reading text is never mono.

## Layout

A fixed 236px rail on desktop (mono nav, glowing dot for the active item) and a five-tab glass bar at the bottom on phones. Content scrolls in the main region under a sticky, opaque page header band that carries a Maasai savanna at the horizon (`SavannaHeader`, SVG and CSS). It has a sky gradient, a low sun, ridges and ground, and warriors standing between the title and the actions, with a scrim on the left behind the title. It is themed by `--sv-*` tokens: night in dark, dusk in daylight. Page padding steps 16px, 24px, then 34px horizontal with 30px vertical from lg. Card padding is 16px on phones and 24px from sm. Controls are 40px tall (36px small, 48px large). Every change must hold at about 380 px; the container caps at 1400px on 2xl. Spacing is Tailwind's 4px-based scale, with 8px and 16px as the common gaps.

## Elevation & Depth

Hybrid: tonal layering plus a glow. In dark, panels sink slightly below the page ink and carry an inset bottom glow and a deep, wide, low shadow; clickable panels lift on hover. Light inverts the cue: panels lift above the paper. Translucent chrome (phone bars, dialog scrim) uses blur; cards never do, because blur on dozens of cards costs the phone.

### Shadow Vocabulary
- **Panel** (`box-shadow: inset 0 -16px 24px 0 var(--panel-inset), 0 24px 60px -20px var(--shadow-color)`): the resting glass panel.
- **Panel lifted** (`inset 0 -18px 28px 0 var(--panel-inset-hover), 0 30px 70px -24px var(--shadow-color)` with `translateY(-4px)`): hover on a clickable panel.
- **Amber bloom** (`0 0 34px rgba(255, 180, 94, 0.28)`, 44px at 0.4 on hover/focus): the filled primary button.
- **Live glow** (`0 0 8px currentColor` plus the pulse ring): the live dot and the active nav dot.
- **Glass bar** (`backdrop-filter: blur(22px) saturate(1.2)` over `--glass`): shell bars only.

### Named Rules
**The Sweep Is Earned Rule.** The amber light sweeping a panel's rim runs only on `.panel-sweep` (the login card) and on hover for hover-capable pointers, never on every card. It stops entirely under reduced motion.

## Shapes

Soft-cornered but precise. Panels are 16px, with medium and small steps at 14px and 12px; controls (buttons, inputs, selects, nav items) are 10px; tags are 6px; switches, the live dot and dialog close buttons are fully round. Panels replace their 1px border with a gradient rim ring; table rows and shell bars use hairline lines. Diagonal 6px stripes mark empty image slots until a photo loads.

## Components

### Buttons
Mono uppercase, 10px radius, 40px tall with 20px side padding, 300ms on the shared easing `cubic-bezier(0.6, 0, 0.2, 1)`.
- **Primary (default):** filled Horizon Amber with ink-on-amber text and an amber bloom that strengthens on hover and focus.
- **Outline:** amber edge and text on a translucent ground, floods amber on hover.
- **Secondary:** ghost glass with an edge stroke, inverts to ink on hover.
- **Destructive:** alert-edged, fills alert on hover. **Ghost:** muted text, amber wash on hover. **Link:** the one non-mono, sentence-case control.
- **Focus:** a 2px amber ring offset from the ground.

### Badges
Mono 10px uppercase tag, 6px radius, a hairline and a faint wash in its own hue, so status reads by colour and by word. Variants: amber, secondary, alert, ok, warn, Strava, outline.

### Panels (Cards)
- **Corner Style:** 16px with the gradient rim.
- **Background:** Panel Brown-Black over a warm six-radial mesh.
- **Shadow Strategy:** see Elevation & Depth.
- **Internal Padding:** 16px, 24px from sm. Titles are Archivo Narrow bold uppercase.

### Inputs / Fields
- **Style:** 40px tall, 10px radius, input-edge stroke, translucent ground fill, faint placeholder.
- **Focus:** the border turns amber with no ring glow; hover brightens the edge.
- **Disabled:** 50% opacity.

### Navigation
Mono uppercase labels at 12px with 0.18em tracking. The active item is marked by a glowing amber dot beside a full-ink label, never a raised pill; inactive items are muted ink and warm to ink on hover. On phones a five-tab glass bar marks the active tab with a short glowing amber bar above its icon. The brand is a mono "ANTON" wordmark with a wide 0.5em tracking beside an amber-outlined mark.

### Live Dot
A 6px accent dot with a glow and a radiating pulse ring, for data that is live.

## Do's and Don'ts

### Do:
- **Do** route every colour through the `index.css` variables so the daylight variant works for free.
- **Do** use mono uppercase with 0.18em tracking for labels, nav, buttons, tags and units, and tabular figures for numbers.
- **Do** express status by colour and by word together (a tag reading OK, WARN or ALERT).
- **Do** keep panels as the one container language and let `.panel-interactive` signal that a card is clickable.
- **Do** respect `prefers-reduced-motion`; all animation stops.
- **Do** check every change at about 380 px.

### Don't:
- **Don't** use amber for status or green, yellow or red for decoration.
- **Don't** run the rim sweep on every card; it is reserved for `.panel-sweep` and hover.
- **Don't** put hex values in components; the Tokens Only Rule is that everything goes through index.css variables.
- **Don't** use pure black or pure white as the dark theme ground or ink.
- **Don't** put `backdrop-filter` on cards; blur belongs to shell bars and scrims.
- **Don't** use grey borders in place of warm alpha hairlines.
- **Don't** set reading text in mono or labels in the sans face.

### Named Rules
**The Tokens Only Rule.** No hex in components. Colour, glow, shadow and mesh all come from index.css variables, which is also what lets the light theme re-tone without a fork.
