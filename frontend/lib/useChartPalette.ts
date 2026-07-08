"use client";
import { useTheme } from "next-themes";
import { CHART_HEX } from "./design-tokens";

export function useChartPalette() {
  const { resolvedTheme } = useTheme();
  return CHART_HEX[resolvedTheme === "dark" ? "dark" : "light"];
}
