/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['Plus Jakarta Sans', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Vora-inspired purple-blue accent palette
        tao: {
          50: '#eef1ff',
          100: '#dde4ff',
          200: '#c2cbff',
          300: '#9da8ff',
          400: '#7580ff',
          500: '#5566ff',
          600: '#2a3ded',
          700: '#2230d4',
          800: '#1c28ab',
          900: '#1a2587',
        },
        // Additional Vora-style semantic colors
        vora: {
          bg: '#000000',
          'bg-alt': '#050d15',
          card: '#121f2d',
          'card-alt': '#132436',
          border: '#1e3a5f',
          text: '#6f87a0',
          'text-muted': '#6f87a099',
          accent: '#5566ff',
          'accent-glow': '#2a3ded66',
        },
      },
    },
  },
  plugins: [],
}
