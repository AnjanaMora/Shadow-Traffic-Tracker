/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          950: '#070A11',
          900: '#0B0F19',
          850: '#101726',
          800: '#131B2E',
          750: '#1A233A',
          700: '#232E47',
          600: '#334155',
          500: '#475569',
        },
        risk: {
          normal: '#10B981',    // Emerald green
          watch: '#F59E0B',     // Amber yellow
          warning: '#F97316',   // Orange
          critical: '#EF4444',  // Rose red
        },
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      animation: {
        'pulse-subtle': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
