import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "rgba(var(--background), <alpha-value>)",
        surface: "rgba(var(--surface), <alpha-value>)",
        "surface-2": "rgba(var(--surface-2), <alpha-value>)",
        text: "rgba(var(--text), <alpha-value>)",
        "text-muted": "rgba(var(--text-muted), <alpha-value>)",
        accent: "rgba(var(--accent), <alpha-value>)",
        "accent-2": "rgba(var(--accent-2), <alpha-value>)",
        success: "rgba(var(--success), <alpha-value>)",
        danger: "rgba(var(--danger), <alpha-value>)",
        warning: "rgba(var(--warning), <alpha-value>)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        display: ["var(--font-display)"],
        mono: ["var(--font-mono)"],
      },
      transitionTimingFunction: {
        glide: "cubic-bezier(0.22, 1, 0.36, 1)",
        snap: "cubic-bezier(0.4, 0, 0.2, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
