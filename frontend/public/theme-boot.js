// Theme boot: applies a stored light preference before first paint so
// light-mode users never see a dark flash. Lives in public/ as a classic
// script (not inline) so the CSP needs no 'unsafe-inline' for script-src.
// src/lib/theme.js owns the storage key and the colours; keep them in sync.
try {
  if (localStorage.getItem('anton-theme') === 'light') {
    document.documentElement.dataset.theme = 'light'
    document.querySelector('meta[name="theme-color"]').setAttribute('content', '#f2f4f9')
    // black-translucent draws WHITE status-bar text, unreadable on paper;
    // "default" gives dark text on its own bar. iOS reads this at launch,
    // so the installed app picks up a theme change on its next cold start.
    document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]').setAttribute('content', 'default')
  }
} catch (e) {}
