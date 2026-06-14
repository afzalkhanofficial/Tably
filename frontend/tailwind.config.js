/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        indigo: {
          50: '#e6fff6',
          100: '#b3ffd9',
          200: '#80ffbc',
          300: '#4dff9f',
          400: '#1aff82',
          500: '#00DF9A', // Spreetail Main Accent Turquoise/Green
          600: '#00c58d', // Darker green/teal hover state
          700: '#00996d',
          800: '#007352',
          900: '#004c36',
          950: '#00261b',
        },
      },
    },
  },
  plugins: [],
}
