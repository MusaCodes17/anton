import { defineConfig, minimal2023Preset } from '@vite-pwa/assets-generator/config'

// RA2.2 §1 — PWA icon generation from public/icon.svg.
//
// Horizon redesign (2026-10-17): colours from tokens --background #070605 and
// --primary #ffb45e. The source SVG is a full-bleed ink square with the Anton
// mark inset within the central ~65% (the maskable safe zone), so every variant
// renders with padding: 0 — no letterboxing, ink edge-to-edge on the home screen.
//
// Run `npm run generate-pwa-assets` to (re)generate the PNGs into public/.
export default defineConfig({
  headLinkOptions: { preset: '2023' },
  preset: {
    ...minimal2023Preset,
    transparent: { ...minimal2023Preset.transparent, padding: 0 },
    maskable: { ...minimal2023Preset.maskable, padding: 0, resizeOptions: { background: '#070605' } },
    apple: { ...minimal2023Preset.apple, padding: 0, resizeOptions: { background: '#070605' } },
  },
  images: ['public/icon.svg'],
})
