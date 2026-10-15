// Theme colours are CSS variables (index.css), which Tailwind can't split into
// channels — so a bare 'var(--x)' silently drops every opacity modifier
// (`bg-primary/90` generated no CSS at all; roadmap §R7.1). Wrapping each token
// in color-mix() with Tailwind's <alpha-value> placeholder makes `/N` work and
// renders the plain class (alpha 1 → 100%) exactly as before. color-mix needs
// Safari 16.2+ / Chrome 111+, which the installed PWA targets already meet.
const token = (name) =>
  `color-mix(in oklab, var(--${name}) calc(<alpha-value> * 100%), transparent)`

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    container: {
      center: true,
      padding: '2rem',
      screens: { '2xl': '1400px' },
    },
    extend: {
      fontFamily: {
        // Signal redesign: template --sans / --display / --mono. `heading` is
        // the display voice (Bricolage Grotesque, set LIGHT — 200–300), kept
        // under its old key so call sites didn't churn.
        sans: ['Hanken Grotesk', 'Helvetica Neue', 'Helvetica', 'Arial', 'system-ui', 'sans-serif'],
        heading: ['Bricolage Grotesque', 'Helvetica Neue', 'Helvetica', 'Arial', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      // Named steps for the recurring arbitrary sizes that fall between
      // Tailwind's defaults. Plain strings (font-size only, no line-height) so
      // they render identically to the text-[NNpx] values they replace.
      fontSize: {
        '2xs': '11px',
        'sm-plus': '13px',
        'md-plus': '15px',
        'lg-plus': '17px',
        stat: '23px',
      },
      colors: {
        border: token('border'),
        input: token('input'),
        ring: token('ring'),
        background: token('background'),
        foreground: token('foreground'),
        primary: {
          DEFAULT: token('primary'),
          foreground: token('primary-foreground'),
        },
        secondary: {
          DEFAULT: token('secondary'),
          foreground: token('secondary-foreground'),
        },
        destructive: {
          DEFAULT: token('destructive'),
          foreground: token('destructive-foreground'),
        },
        muted: {
          DEFAULT: token('muted'),
          foreground: token('muted-foreground'),
        },
        accent: {
          DEFAULT: token('accent'),
          foreground: token('accent-foreground'),
        },
        popover: {
          DEFAULT: token('popover'),
          foreground: token('popover-foreground'),
        },
        card: {
          DEFAULT: token('card'),
          foreground: token('card-foreground'),
        },
        success: {
          DEFAULT: token('success'),
          foreground: token('success-foreground'),
        },
        warning: {
          DEFAULT: token('warning'),
          foreground: token('warning-foreground'),
        },
        strava: {
          DEFAULT: token('strava'),
          foreground: token('strava-foreground'),
        },
        // "Velocity" design system: a second, slightly lighter dark tone used
        // for nested tiles/rows inside a --card panel (stat tiles, table rows),
        // distinct from the panel background itself.
        surface: token('surface'),
        faint: token('faint'),
        sidebar: token('sidebar'),
        divider: token('divider'),
        edge: token('edge'),
        'nav-inactive': token('nav-inactive'),
        'signal-deep': token('signal-deep'),
        photo: {
          DEFAULT: token('photo'),
          foreground: token('photo-foreground'),
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      keyframes: {
        // Template tick-fade: a sweep of fading ticks (used for "working" dots).
        'tick-fade': {
          '0%, 100%': { opacity: '0.15' },
          '50%': { opacity: '1' },
        },
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      transitionTimingFunction: {
        signal: 'cubic-bezier(0.6, 0, 0.2, 1)', // template --ease
      },
      letterSpacing: {
        display: '-0.035em', // template .display
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        'tick-fade': 'tick-fade 1.2s ease-in-out infinite',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
