/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        brand: {
          cream: '#FBFBFA',
          surface: '#FFFFFF',
          border: '#E8E8E3',
          muted: '#6E717A',
          darkbg: '#0E1015',
          darksurface: '#15181F',
          darkborder: '#222631',
          darkmuted: '#8E94A0',
          accent: '#10B981',
          forest: '#0F172A',
          sage: '#0D9488',
          darkcard: '#15181F',
        }
      }
    },
  },
  plugins: [],
}

