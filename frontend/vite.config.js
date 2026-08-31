import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // RA2.2 — installable PWA + offline READ. Writes stay online-only (§4),
    // so the service worker caches static assets and *safe GET reads* only;
    // it never caches auth responses or the session cookie.
    VitePWA({
      // New deploys refresh the SW without a prompt — fine for a single-user
      // app (RA2.2 §1). Revisit if it ever causes a mid-session reload.
      registerType: 'autoUpdate',
      // Icons live in public/ (generated via `npm run generate-pwa-assets`);
      // include them + the source SVG in the precache glob below.
      includeAssets: ['favicon.svg', 'icon.svg', 'apple-touch-icon-180x180.png'],
      manifest: {
        name: 'Anton',
        short_name: 'Anton',
        description: 'Personal running platform — rotation, training, and deals.',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        // From the design tokens: --background #0e0f11, brand green #16a34a.
        background_color: '#0e0f11',
        theme_color: '#0e0f11',
        icons: [
          { src: 'pwa-64x64.png', sizes: '64x64', type: 'image/png' },
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          {
            src: 'maskable-icon-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // §2 app-shell precache: the built HTML/JS/CSS/icons/fonts.
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff,woff2}'],
        // SPA nav-fallback mirrors Caddy's try_files → index.html so client
        // routes work offline. Exclude /api and backend auth/mcp paths so a
        // navigation never resolves to the app shell instead of the backend.
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [
          /^\/api/,
          /^\/mcp/,
          /^\/health/,
          /^\/authorize/,
          /^\/token/,
          /^\/revoke/,
          /^\/oauth/,
          /^\/\.well-known/,
        ],
        // autoUpdate: take over immediately and drop stale precaches so a
        // deploy doesn't strip-mine storage (§2 cache versioning).
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        skipWaiting: true,
        runtimeCaching: [
          {
            // §3 offline READ: cache safe GET /api reads. NetworkFirst =
            // fresh when online, last-good when offline. Scoped to GET only;
            // the auth session endpoint is explicitly excluded so no
            // credential/session state is ever cached (RA2.2 §0, §3).
            urlPattern: ({ url, request, sameOrigin }) =>
              sameOrigin &&
              request.method === 'GET' &&
              url.pathname.startsWith('/api/') &&
              url.pathname !== '/api/auth/session',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'anton-api-reads',
              networkTimeoutSeconds: 5,
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 * 7 },
              cacheableResponse: { statuses: [200] },
            },
          },
        ],
      },
      devOptions: {
        // Keep the SW off in `vite dev` to avoid caching surprises while
        // developing; it's exercised via `vite build` + preview.
        enabled: false,
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // Proxy API requests to the FastAPI backend during development so the
    // frontend can call relative `/api/...` paths without CORS concerns.
    proxy: {
      // Use 127.0.0.1 (not localhost) so Node 18 doesn't resolve to IPv6 ::1,
      // which the IPv4-only backend refuses.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
