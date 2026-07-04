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
        sans: ['Hanken Grotesk', 'sans-serif'],
        heading: ['Archivo', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
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
        border: 'var(--border)',
        input: 'var(--input)',
        ring: 'var(--ring)',
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        primary: {
          DEFAULT: 'var(--primary)',
          foreground: 'var(--primary-foreground)',
        },
        secondary: {
          DEFAULT: 'var(--secondary)',
          foreground: 'var(--secondary-foreground)',
        },
        destructive: {
          DEFAULT: 'var(--destructive)',
          foreground: 'var(--destructive-foreground)',
        },
        muted: {
          DEFAULT: 'var(--muted)',
          foreground: 'var(--muted-foreground)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          foreground: 'var(--accent-foreground)',
        },
        popover: {
          DEFAULT: 'var(--popover)',
          foreground: 'var(--popover-foreground)',
        },
        card: {
          DEFAULT: 'var(--card)',
          foreground: 'var(--card-foreground)',
        },
        success: {
          DEFAULT: 'var(--success)',
          foreground: 'var(--success-foreground)',
        },
        warning: {
          DEFAULT: 'var(--warning)',
          foreground: 'var(--warning-foreground)',
        },
        strava: {
          DEFAULT: 'var(--strava)',
          foreground: 'var(--strava-foreground)',
        },
        // "Velocity" design system: a second, slightly lighter dark tone used
        // for nested tiles/rows inside a --card panel (stat tiles, table rows),
        // distinct from the panel background itself.
        surface: 'var(--surface)',
        faint: 'var(--faint)',
        sidebar: 'var(--sidebar)',
        divider: 'var(--divider)',
        edge: 'var(--edge)',
        'nav-inactive': 'var(--nav-inactive)',
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
