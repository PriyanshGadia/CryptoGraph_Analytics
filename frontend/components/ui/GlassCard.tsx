"use client";

import { ReactNode } from "react";

interface GlassCardProps {
  children?: ReactNode;
  className?: string;
  variant?: "dark" | "light" | "auto" | "flat" | 1 | 2 | 3;
  tier?: "flat" | 1 | 2 | 3;
  asymmetric?: "default" | "lg" | "xl" | "sm" | "none" | "md" | "shape-facet" | "shape-ledger" | "shape-squircle" | "shape-hex" | "shape-seal";
  shape?: "shape-facet" | "shape-facet-sm" | "shape-ledger" | "shape-squircle" | "shape-hex" | "shape-seal" | "none";
  hoverable?: boolean;
  style?: React.CSSProperties;
}

export function GlassCard({
  children,
  className = "",
  variant = "auto",
  tier,
  asymmetric = "default",
  shape,
  hoverable = false,
  style
}: GlassCardProps) {
  let finalTier = tier;
  if (!finalTier) {
    if (variant === 1 || variant === 2 || variant === 3 || variant === "flat") finalTier = variant;
    else if (variant === "dark") finalTier = 3;
    else if (variant === "light") finalTier = 1;
    else finalTier = 2; // auto
  }
  const tierClass = finalTier === "flat" ? "glass-flat" : `glass-${finalTier}`;

  let finalShape = shape;
  if (!finalShape) {
    if (asymmetric.startsWith("shape-") || asymmetric === "none") finalShape = asymmetric as any;
    else if (asymmetric === "sm") finalShape = "shape-facet-sm";
    else if (asymmetric === "lg") finalShape = "shape-squircle";
    else if (asymmetric === "xl") finalShape = "shape-hex";
    else finalShape = "rounded-2xl" as any; // default, md
  }
  const shapeClass = finalShape === "none" ? "" : finalShape;

  const baseClass = "transition-all duration-[var(--dur-enter)] ease-glide relative";

  const hoverClass = hoverable
    ? "hover:scale-[1.02] hover:-translate-y-1 hover:shadow-[0_0_15px_rgba(var(--accent),0.3)] hover:border-accent/50 cursor-pointer"
    : "";

  return (
    <div className={`${baseClass} ${tierClass} ${shapeClass} ${hoverClass} ${className}`} style={style}>
      {/* Subtle shine effect on hover */}
      {hoverable && (
        <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-[rgba(var(--text),0.05)] to-transparent opacity-0 hover:opacity-100 transition-opacity duration-[var(--dur-hover)] pointer-events-none" />
      )}
      {children}
    </div>
  );
}
