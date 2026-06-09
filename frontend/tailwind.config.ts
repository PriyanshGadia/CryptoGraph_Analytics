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
        background: "#0f0f0f",
        surface: "#1a1a1a",
        border: "#2a2a2a",
        accent: "#6366f1",
        success: "#22c55e",
        danger: "#ef4444",
        warning: "#f59e0b",
        text: "#f1f5f9",
        textMuted: "#94a3b8",
      },
      fontFamily: {
        mono: ["var(--font-space-mono)"],
        sans: ["var(--font-inter)"],
      },
    },
  },
  plugins: [],
};

export default config;
