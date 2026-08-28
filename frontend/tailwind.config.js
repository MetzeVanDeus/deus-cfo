/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Legacy class names mapped onto the brass terminal tokens.
        // Component migration is tracked separately; no second palette lives here.
        dracula: {
          bg:        'var(--bg)',
          current:   'var(--surface-raised)',
          fg:        'var(--text)',
          comment:   'var(--muted)',
          cyan:      'var(--info)',
          green:     'var(--positive)',
          orange:    'var(--warning)',
          pink:      'var(--negative)',
          purple:    'var(--brass)',
          red:       'var(--negative)',
          yellow:    'var(--brass-bright)',
        },
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Consolas', 'Liberation Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
