/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: { sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'] },
      colors: {
        'bg-dark': 'var(--bg-base)',
        'bg-card': 'var(--surface-reading)',
        'accent-gold': 'var(--accent-gold)',
        'accent-gold-strong': 'var(--accent-gold-strong)',
        'text-primary': 'var(--text-1)',
        'text-secondary': 'var(--text-2)',
        'text-muted': 'var(--text-2)',
        'border-subtle': 'var(--glass-border)',
      },
    },
  },
  plugins: [],
};
