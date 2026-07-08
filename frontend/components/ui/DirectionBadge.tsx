import { ReactNode } from "react";
import { TrendingUp, TrendingDown, Minus, Activity } from "lucide-react";
import { DIRECTION_TOKENS, Direction } from "@/lib/design-tokens";
import { cn } from "@/lib/utils";

const DEFAULT_ICONS: Record<Direction, ReactNode> = {
  strong_up: <TrendingUp size={12} />,
  up: <TrendingUp size={12} />,
  neutral: <Minus size={12} />,
  down: <TrendingDown size={12} />,
  strong_down: <TrendingDown size={12} />,
  recalibrating: <Activity size={12} />,
};

export function DirectionBadge({
  direction,
  showIcon = false,
  className = "",
}: {
  direction?: string | null;
  showIcon?: boolean;
  className?: string;
}) {
  const key = (direction ?? "neutral").toLowerCase();
  const safe = (key in DIRECTION_TOKENS ? key : "neutral") as Direction;
  const t = DIRECTION_TOKENS[safe];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 shape-tag border px-3 py-1 text-[10px] font-bold uppercase tracking-widest",
        t.bgClass,
        t.textClass,
        t.borderClass,
        className
      )}
      style={{ boxShadow: t.glow !== "none" ? t.glow : undefined }}
    >
      {showIcon && DEFAULT_ICONS[safe]}
      {t.label}
    </span>
  );
}
