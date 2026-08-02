/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', 'sans-serif'] },
      colors: {
        'bg-dark': '#0a0a0f',
        'bg-card': '#111118',
        'bg-card-hover': '#18182a',
        'accent-cyan': '#38bdf8',
        'accent-gold': '#d4a843',
        'text-primary': '#f0f0f5',
        'text-secondary': '#9ca3af',
        'text-muted': '#6b7280',
        'border-subtle': 'rgba(255,255,255,0.06)',
      },
      animation: {
        'float-1': 'floatOrb1 20s ease-in-out infinite',
        'float-2': 'floatOrb2 25s ease-in-out infinite',
      },
      keyframes: {
        floatOrb1: {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '50%': { transform: 'translate(60px, 40px) scale(1.1)' },
        },
        floatOrb2: {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '50%': { transform: 'translate(-50px, -30px) scale(1.05)' },
        },
      },
    },
  },
  plugins: [],
}
