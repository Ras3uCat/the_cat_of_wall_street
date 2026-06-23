import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          cyan:    '#58E3EF',
          magenta: '#D34CF1',
          dark:    '#000612',
          slate:   '#1A1C2C',
          gold:    '#FFB938',
          white:   '#E8FEFF',
        },
      },
      fontFamily: {
        play:     ['var(--font-play)',    'sans-serif'],
        orbitron: ['var(--font-orbitron)','monospace'],
        space:    ['var(--font-space)',   'sans-serif'],
        inter:    ['var(--font-inter)',   'sans-serif'],
      },
    },
  },
  plugins: [],
};

export default config;
