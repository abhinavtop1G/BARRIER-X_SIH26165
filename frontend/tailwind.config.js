export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bx: {
          bg:         '#0a0a0a',
          card:       '#111111',
          hover:      '#161616',
          border:     '#1e1e1e',
          subtle:     '#2a2a2a',
          gold:       '#D4AF37',
          'gold-dim': '#b89b2e',
          text:       '#F8F8F8',
          secondary:  '#8a8a8a',
          muted:      '#555555',
          green:      '#228B22',
          red:        '#c0392b',
        },
      },
      fontFamily: {
        display: ['"Playfair Display"', 'Georgia', 'serif'],
        mono:    ['"JetBrains Mono"', 'monospace'],
        sans:    ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'fade-up':   'fadeUp 0.42s cubic-bezier(0.22,1,0.36,1) both',
        'spin-slow': 'spin 0.9s linear infinite',
        pulse:       'pulse 2s ease infinite',
      },
      keyframes: {
        fadeUp: {
          from: { opacity: '0', transform: 'translateY(14px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
