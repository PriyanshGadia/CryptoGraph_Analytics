export type Direction = "strong_up" | "up" | "neutral" | "down" | "strong_down" | "recalibrating";

interface DirectionToken {
  label: string;
  textClass: string;
  bgClass: string;
  borderClass: string;
  glow: string;
}

export const DIRECTION_TOKENS: Record<Direction, DirectionToken> = {
  strong_up:   { label: "STRONG BUY",  textClass: "text-success",    bgClass: "bg-success/10",     borderClass: "border-success/30",     glow: "0 0 18px rgba(var(--success), 0.35)" },
  up:          { label: "BUY",         textClass: "text-success",    bgClass: "bg-success/5",      borderClass: "border-success/20",     glow: "none" },
  neutral:     { label: "NEUTRAL",     textClass: "text-text-muted", bgClass: "bg-text-muted/10",  borderClass: "border-text-muted/20",  glow: "none" },
  down:        { label: "SELL",        textClass: "text-danger",     bgClass: "bg-danger/5",       borderClass: "border-danger/20",      glow: "none" },
  strong_down: { label: "STRONG SELL", textClass: "text-danger",     bgClass: "bg-danger/10",      borderClass: "border-danger/30",      glow: "0 0 18px rgba(var(--danger), 0.35)" },
  recalibrating: { label: "RECALIBRATING", textClass: "text-warning", bgClass: "bg-warning/10",  borderClass: "border-warning/20",     glow: "none" },
};

export const CHART_HEX = {
  light: { text: "#1B1812", muted: "#5B5547", success: "#2F7A52", danger: "#A8333A", warning: "#8A5D17", accent: "#7A2433", accent2: "#544A8C", surface: "#F0EDE8" },
  dark:  { text: "#ECE7DD", muted: "#9CA3AF", success: "#5FCB9A", danger: "#E58A7E", warning: "#E6BD6E", accent: "#D8B873", accent2: "#A89CE8", surface: "#14151B" },
} as const;
