"use client";

import { useEffect, useState } from "react";

export type PerformanceMode = "full" | "lite";

export function usePerformanceMode() {
  const [mode, setMode] = useState<PerformanceMode>("full");

  useEffect(() => {
    // Check local storage first
    const saved = localStorage.getItem("performance-mode") as PerformanceMode | null;
    if (saved) {
      setMode(saved);
      document.documentElement.setAttribute("data-performance", saved);
    } else {
      // Check prefers-reduced-motion for automatic lite mode on mobile/low-power
      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const initialMode = prefersReduced ? "lite" : "full";
      setMode(initialMode);
      document.documentElement.setAttribute("data-performance", initialMode);
    }
  }, []);

  const toggleMode = (newMode: PerformanceMode) => {
    setMode(newMode);
    localStorage.setItem("performance-mode", newMode);
    document.documentElement.setAttribute("data-performance", newMode);
  };

  return { mode, toggleMode };
}
