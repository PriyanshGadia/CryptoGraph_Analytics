"use client";

import { useTheme } from "next-themes";
import { Sun, Moon } from "lucide-react";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [mounted, setMounted] = useState(false);
  const { theme, setTheme } = useTheme();

  useEffect(() => setMounted(true), []);

  if (!mounted) return null;

  return (
    <button
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="relative w-12 h-12 shape-hex depth-bevel glass-1 hover:scale-105 hover:-translate-y-1 transition-all duration-[var(--dur-hover)] ease-glide flex items-center justify-center group"
      aria-label="Toggle theme"
    >
      <div className="absolute inset-0 shape-hex bg-gradient-to-br from-accent/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      <Sun className={`w-5 h-5 text-amber-400 drop-shadow-[0_0_8px_rgba(251,191,36,0.8)] absolute transition-all duration-[var(--dur-hover)] ease-glide ${theme === 'dark' ? 'opacity-100 scale-100' : 'opacity-0 scale-50'}`} />
      <Moon className={`w-5 h-5 text-text absolute transition-all duration-[var(--dur-hover)] ease-glide ${theme === 'dark' ? 'opacity-0 scale-50' : 'opacity-100 scale-100'}`} />
    </button>
  );
}
