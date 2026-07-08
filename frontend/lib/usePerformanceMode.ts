"use client";

import { useAppStore, PerformanceMode } from "./store";

export type { PerformanceMode };

export function usePerformanceMode() {
  const mode = useAppStore((state) => state.performanceMode);
  const toggleMode = useAppStore((state) => state.setPerformanceMode);

  return { mode, toggleMode };
}
