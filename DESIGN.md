---
name: Anton
description: A calm, instrument-panel dark UI for a runner's shoes, miles and deals, lit by a single green signal.
colors:
  signal-green: "oklch(0.74 0.17 153)"
  signal-green-text: "oklch(0.8 0.16 153)"
  signal-green-wash: "oklch(0.74 0.17 153 / 0.13)"
  amber-caution: "oklch(0.8 0.15 75)"
  red-limit: "oklch(0.65 0.2 25)"
  strava-orange: "oklch(0.66 0.19 41)"
  void: "#0e0f11"
  panel: "#13151a"
  surface: "#16181b"
  sidebar: "#101215"
  divider: "#1a1d22"
  hairline: "#23262b"
  edge: "#2e3239"
  nav-inactive: "#3a3e44"
  faint: "#6a6f76"
  muted-text: "#8a8f96"
  soft-text: "#c4c8ce"
  ink: "#f2f2f0"
typography:
  display:
    fontFamily: "Archivo, sans-serif"
    fontSize: "32px"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "normal"
  headline:
    fontFamily: "Archivo, sans-serif"
    fontSize: "19px"
    fontWeight: 800
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Hanken Grotesk, sans-serif"
    fontSize: "17px"
    fontWeight: 600
  body:
    fontFamily: "Hanken Grotesk, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Hanken Grotesk, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "0.1em"
  data:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "13px"
    fontWeight: 500
rounded:
  sm: "8px"
  md: "10px"
  lg: "12px"
  tile: "13px"
  pill: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  tile: "17px"
  lg: "24px"
  page: "32px"
components:
  button-primary:
    backgroundColor: "{colors.signal-green}"
    textColor: "{colors.void}"
    typography: "{typography.headline}"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "8px 16px"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.soft-text}"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "8px 16px"
  button-ghost:
    textColor: "{colors.muted-text}"
    rounded: "{rounded.md}"
    height: "40px"
  stat-tile:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.tile}"
    padding: "17px"
  card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "24px"
  input:
    backgroundColor: "{colors.void}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "8px 12px"
  nav-item-active:
    backgroundColor: "{colors.signal-green-wash}"
    textColor: "{colors.signal-green-text}"
    rounded: "9px"
    padding: "11px 12px"
  nav-item:
    textColor: "{colors.muted-text}"
    rounded: "9px"
    padding: "11px 12px"
---

# Design System: Anton

## Overview

**Creative North Star: "The Pit Wall"**

Anton looks like the monitor a race engineer watches between laps: a single fixed dark theme, near-black with a faint cool cast, where almost everything is quiet and one green signal marks what matters. Calm and instrumental is the register. Surfaces step through tonal layers, numbers are large, tabular and unadorned, and information outranks personality. There is no light mode; the design does not define one.

Density is moderate and compact: stat tiles, mileage bars, rows and badges, scanned in a glance on a phone after a run or studied at a desk. Brand lives in details, not decoration: an Archivo heading voice for numbers and actions, a rotated-diamond nav marker, a green square holding the Anton mark.

**Key Characteristics:**
- One fixed dark theme; flat tonal layering instead of shadows.
- A single chromatic signal (green) plus two traffic-light states (amber, red) and one provenance color (Strava orange).
- Archivo for the loud, Hanken Grotesk for the readable, JetBrains Mono for raw data.
- Tabular numerals everywhere a number is compared.
- Same components from 380 px phone to wide desktop; the PWA safe-area insets are honored.

## Colors

A near-monochrome cool-black field with one saturated green that signals "go, healthy, primary action," and warm colors reserved for wear and provenance.

### Primary
- **Signal Green** (oklch(0.74 0.17 153)): primary actions, focus ring, active nav diamond, "healthy" mileage, success states. Its wash (`oklch(0.74 0.17 153 / 0.13)`) fills the active nav item; its brighter text variant (`oklch(0.8 0.16 153)`) sits on that wash.

### Secondary
- **Amber Caution** (oklch(0.8 0.15 75)): shoe nearing its retirement limit (75-100%), limited-scrape states.
- **Red Limit** (oklch(0.65 0.2 25)): past the mileage limit, destructive actions, errors.
- **Strava Orange** (oklch(0.66 0.19 41)): the provenance badge for runs backfilled from the Strava archive. Never used for general emphasis.

### Neutral
- **Void** (#0e0f11): page background, input fill, and text color on green buttons.
- **Panel** (#13151a): cards.
- **Surface** (#16181b): nested tiles, rows, secondary buttons, popovers.
- **Sidebar** (#101215): sidebar and topbar, a half-step below the page.
- **Divider** (#1a1d22) / **Hairline** (#23262b) / **Edge** (#2e3239): soft row dividers, standard borders and input strokes, and dashed "add" outlines, in rising strength.
- **Ink** (#f2f2f0): primary text. **Soft Text** (#c4c8ce), **Muted Text** (#8a8f96), **Faint** (#6a6f76): secondary, supporting and quietest text.
- **Nav Inactive** (#3a3e44): the inactive nav diamond.

### Named Rules
**The One Signal Rule.** Green is the only chromatic voice at rest. Amber, red and orange appear only when a state or source earns them; never for decoration.

**The Traffic-Light Rule.** Wear is always green under 75% of a shoe's limit, amber from 75-100%, red beyond. The thresholds are the product's rules, not styling.

## Typography

**Display Font:** Archivo (with sans-serif)
**Body Font:** Hanken Grotesk (with sans-serif)
**Label/Mono Font:** JetBrains Mono for raw data; labels use Hanken Grotesk.

**Character:** Archivo at weight 800 carries stats and primary actions with athletic weight; Hanken Grotesk keeps running text humane and legible at small sizes; JetBrains Mono is reserved for data that reads as telemetry.

### Hierarchy
- **Display** (Archivo 800, 32px, line-height 1): headline stat numbers in tiles, tabular-nums.
- **Headline** (Archivo 800, 19px, -0.025em tracking): brand wordmark and primary button labels.
- **Title** (Hanken Grotesk 600, 17px / 15px): card and section titles.
- **Body** (Hanken Grotesk 400, 14px, 1.5): rows, descriptions, chat text. Cap prose near 65-75ch.
- **Label** (Hanken Grotesk 600, 11px, 0.1em, uppercase): tile captions and table headers.
- **Data** (JetBrains Mono 500, 13px): paces, IDs, raw figures.

Scale uses named half-steps: 11px, 13px, 15px, 17px, and a 23px stat size, alongside Tailwind defaults.

### Named Rules
**The Tabular Rule.** Any number that may be compared across rows or over time uses tabular numerals.

## Layout

Fixed-height app shell: a static header and offline banner sit outside the scroll region, and only the main area scrolls (100dvh, with `env(safe-area-inset-*)` insets for the installed iOS PWA). Navigation is a left sidebar on desktop and a bottom tab bar on mobile, five primary destinations (Home, Training, Shoes, Deals, Son of Anton) with Settings pinned apart (sidebar footer on desktop, a gear in the mobile top bar). The tab bar is a static shell child below the scroll region, owns the bottom safe-area inset, and hides while the iOS keyboard is up; the shell height follows `visualViewport` (`--app-height`) while the keyboard is open. The chat route goes full-bleed with its own internal scroll regions and replaces the mobile top bar with its own header.

Pages are padded containers (2rem, max 1400px at 2xl) built from stat-tile grids, panels and rows. Aggregate-per-page data means a page is a handful of well-organized panels, not a feed. Spacing is compact and rhythmic (8, 16, 17, 24, 32px) rather than airy.

## Elevation & Depth

Flat by design. Depth is conveyed by tonal stepping (void → panel → surface) and 1px borders in Hairline; panels carry at most Tailwind's faint `shadow-sm`, which is imperceptible on this dark field. Nothing floats with a glow.

### Named Rules
**The Flat-Tonal Rule.** To lift an element, step it up one surface tone or add a hairline; never add a drop shadow or glow.

## Shapes

Gently rounded, never pill-shaped except for badges and progress bars. Radius derives from one variable (`--radius`, 0.75rem): panels 12px, controls 10px, small buttons 8px, stat tiles 13px, nav items 9px. Borders are 1px, hairline; "add" affordances use a dashed Edge outline. The nav's active marker is a 7px rotated square with 2px corners, a small repeating geometric signature.

## Components

### Buttons
- **Shape:** 10px radius (8px small), 40px high (36px small, 44px large).
- **Primary:** Signal Green fill, Void text, Archivo 800; hover dims to 90%.
- **Outline / Secondary / Ghost:** hairline outline on transparent; Surface fill; or text-only muted that lifts to Surface on hover.
- **Focus:** 2px green ring with a 2px background-colored offset on every interactive element (shared `.focus-ring` for custom controls).
- **Destructive:** Red Limit fill, used behind a confirmation dialog.

### Stat Tile
- **Style:** Surface fill, 1px Hairline border, 13px radius, 17px padding.
- **Content:** uppercase 11px label (muted, 0.1em), Archivo 800 32px tabular number, optional 12px hint.
- Loading state is a skeleton the size of the number.

### Cards / Containers
- **Corner Style:** 12px. **Background:** Panel. **Border:** 1px Hairline. **Padding:** 24px header/content.

### Badges
- **Style:** full pill, 12px semibold; variants for primary, secondary, success, warning, destructive, Strava and outline. Status badges pair an icon with a label and optional `found/total` count.

### Inputs / Fields
- **Style:** 40px high, Void fill, Hairline stroke, 10px radius, muted placeholder.
- **Focus:** green ring with offset. **Disabled:** 50% opacity, not-allowed cursor.

### Navigation
- Active item: green wash fill, bold green text, green diamond marker. Inactive: muted text, grey diamond, Surface fill on hover. Settings and Sign out use a 15px line icon instead of the diamond.
- **Mobile tab bar:** five equal columns, 56px tall plus the home-indicator inset, Sidebar fill with a Divider top border. Each tab is a 22px line icon over an 11px label (Son of Anton shortens to "Anton"). Active: bold green text and the 7px green diamond sitting on the bar's top edge; inactive: muted text, no diamond. No floating action button on mobile; the Anton tab replaces it.

### Chat (Son of Anton)
- **Header:** one 52px bar on phones: conversations button, conversation title with "Son of Anton · model" beneath, new-chat button; all 44px targets.
- **Thread:** assistant replies are unbubbled and full width; the runner's messages are Surface bubbles with a Hairline border (not the green wash). Tool calls are 28px JetBrains Mono chips: green check when done, pulsing green diamond while running.
- **Composer:** a single 22px-radius field (Panel fill, Hairline border, green border on focus) holding the textarea and a 40px round send button (green; Hairline grey when disabled), which becomes an ink Stop button while a reply streams. Text is 16px on phones so iOS never zooms; keyboard hints show on desktop only.
- **Conversations (mobile):** a bottom sheet with a 20px top radius, grabber, primary New conversation button, Model picker, and 56px rows whose delete control is always visible.

### Mileage Progress Bar (signature)
- 8px full-pill track in Secondary, filled green/amber/red by the Traffic-Light Rule, with a tabular 11px caption (`412 km` ... `800 km limit`). The bar's color alone carries the limit on compact cards.

### Product image placeholder
- 135° diagonal stripes in two near-identical dark greys (6px bands) behind product images until they load.

## Do's and Don'ts

### Do:
- **Do** use only the CSS variables (`--primary`, `--surface`, ...) via Tailwind tokens; add a token before adding a color.
- **Do** keep the green accent rare; let numbers and tonal layers do the work.
- **Do** use tabular numerals for mileage, pace, price and dates.
- **Do** keep the 2px green focus ring on every interactive element.
- **Do** check every screen at desktop and ~380 px, with safe-area insets in the installed PWA.

### Don't:
- **Don't** add a light theme or a `.dark` toggle; the system is a single fixed dark theme.
- **Don't** use shadows, glows or gradients to create hierarchy; step the surface tone instead.
- **Don't** hard-code hex in components (the product-image stripe placeholder is the one existing exception).
- **Don't** use Strava Orange for anything but Strava-sourced runs.
- **Don't** introduce another chart library or heavy UI dependency; charts stay on recharts.

## Rejected Directions

Decisions the owner has made against specific looks. Do not propose these again; evolve the Pit Wall system above instead.

- **Montréal '76 "lane sheet" (tried 2026-10-08, rejected).** Ultramarine ground, royal-blue sidebar, azure signal, Schibsted Grotesk, shoes drawn as numbered track lanes. The owner disliked the colors. Do not move the palette toward blue/ultramarine or replace the green signal without being asked. Any redesign must keep the green One Signal Rule and the near-black cool field unless the owner explicitly says otherwise.
