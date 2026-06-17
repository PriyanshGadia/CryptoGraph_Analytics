import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: 'class',
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        crypto: {
          dark: { bg: '#0a0a0f', surface: '#14141e', text: '#f0ede8' },
          light: { bg: '#f8f6f0', surface: '#f0ede8', text: '#1a1a1e' },
          accent: { dark: '#d4a547', light: '#7a1f2b' },
        },
        background: "rgba(var(--background), <alpha-value>)",
        surface: "rgba(var(--surface), <alpha-value>)",
        border: "rgba(var(--border), <alpha-value>)",
        accent: "rgba(var(--accent), <alpha-value>)",
        success: "rgba(var(--success), <alpha-value>)",
        danger: "rgba(var(--danger), <alpha-value>)",
        warning: "rgba(var(--warning), <alpha-value>)",
        text: "rgba(var(--text), <alpha-value>)",
        "text-muted": "rgba(var(--text-muted), <alpha-value>)",
        textMuted: "rgba(var(--text-muted), <alpha-value>)",
      },
      fontFamily: {
        mono: ["var(--font-mono)"],
        sans: ["var(--font-primary)"],
      },
      borderRadius: {
        'crypto': '20px 8px 20px 8px',
        'crypto-lg': '32px 12px 32px 12px',
        'crypto-xl': '48px 16px 48px 16px',
        'crypto-sm': '12px 4px 12px 4px',
      },
      keyframes: {
        blob: {
          '0%': { borderRadius: '40% 60% 70% 30% / 40% 50% 60% 50%' },
          '33%': { borderRadius: '60% 40% 30% 70% / 60% 30% 70% 40%' },
          '66%': { borderRadius: '30% 70% 50% 50% / 50% 60% 40% 50%' },
          '100%': { borderRadius: '40% 60% 70% 30% / 40% 50% 60% 50%' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        }
      },
      animation: {
        blob: 'blob 8s ease-in-out infinite',
        shimmer: 'shimmer 2s infinite',
        float: 'float 4s ease-in-out infinite',
      }
    },
  },
  plugins: [],
};

export default config;
