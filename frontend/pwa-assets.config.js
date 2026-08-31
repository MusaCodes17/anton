import { defineConfig, minimal2023Preset } from '@vite-pwa/assets-generator/config'

// RA2.2 §1 — PWA icon generation from public/icon.svg.
//
// The source SVG is a full-bleed green square with the Anton mark already inset
// within the central ~65% (the maskable safe zone), so every variant renders
// with padding: 0 — no white letterboxing, brand-green edge-to-edge on the
// home screen. Colors come from the design tokens (favicon green #16a34a,
// mark #0a0f0d), not invented here.
//
// Run `npm run generate-pwa-assets` to (re)generate the PNGs into public/.
export default defineConfig({
  headLinkOptions: { preset: '2023' },
  preset: {
    ...minimal2023Preset,
    transparent: { ...minimal2023Preset.transparent, padding: 0 },
    maskable: { ...minimal2023Preset.maskable, padding: 0, resizeOptions: { background: '#16a34a' } },
    apple: { ...minimal2023Preset.apple, padding: 0, resizeOptions: { background: '#16a34a' } },
  },
  images: ['public/icon.svg'],
})
