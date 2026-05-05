import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        "surface-3": "var(--surface-3)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        text: "var(--text)",
        "text-muted": "var(--text-muted)",
        "text-faint": "var(--text-faint)",
        accent: "var(--accent)",
        "accent-soft": "var(--accent-soft)",
        "accent-glow": "var(--accent-glow)",
        good: "var(--good)",
        "good-soft": "var(--good-soft)",
        warn: "var(--warn)",
        "warn-soft": "var(--warn-soft)",
        info: "var(--info)",
        "info-soft": "var(--info-soft)",
      },
      fontFamily: {
        serif: ["Instrument Serif", "Georgia", "serif"],
        sans: ["Geist", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
        mono: ["Geist Mono", "SF Mono", "monospace"],
      },
      borderRadius: {
        sm: "8px",
        md: "12px",
        lg: "16px",
        xl: "20px",
      },
      boxShadow: {
        soft: "0 1px 2px rgba(0,0,0,0.2), 0 4px 12px rgba(0,0,0,0.15)",
        elevated: "0 4px 8px rgba(0,0,0,0.25), 0 12px 32px rgba(0,0,0,0.2)",
      },
      transitionTimingFunction: {
        toggle: "cubic-bezier(0.4, 0, 0.2, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
