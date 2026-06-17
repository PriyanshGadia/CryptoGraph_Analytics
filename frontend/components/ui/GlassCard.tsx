"use client";

import { useTheme } from "next-themes";
import { ReactNode, useEffect, useState } from "react";

interface GlassCardProps {
  children?: ReactNode;
  className?: string;
  variant?: "dark" | "light" | "auto";
  asymmetric?: "default" | "lg" | "xl" | "sm" | "none" | "md";
  hoverable?: boolean;
  style?: React.CSSProperties;
}

export function GlassCard({
  children,
  className = "",
  variant = "auto",
  asymmetric = "default",
  hoverable = false,
  style
}: GlassCardProps) {
  const [mounted, setMounted] = useState(false);
  const { theme } = useTheme();

  useEffect(() => setMounted(true), []);

  const isDark = mounted ? theme === "dark" : true; // default dark during ssr

  const baseClass = "glass transition-all duration-500 relative overflow-hidden";
  const darkClass = "bg-white/5 border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.4)]";
  const lightClass = "bg-white/60 border-white/30 shadow-[0_8px_32px_rgba(0,0,0,0.08)]";

  const variantClass =
    variant === "dark" ? darkClass :
    variant === "light" ? lightClass :
    isDark ? darkClass : lightClass;

  const radiusClass = 
    asymmetric === "lg" ? "rounded-crypto-lg" :
    asymmetric === "xl" ? "rounded-crypto-xl" :
    asymmetric === "sm" ? "rounded-crypto-sm" :
    asymmetric === "none" ? "" :
    "rounded-crypto";

  const hoverClass = hoverable
    ? "hover:scale-[1.02] hover:-translate-y-1 hover:shadow-[0_0_15px_rgba(var(--accent),0.3)] hover:border-accent/50 cursor-pointer"
    : "";

  return (
    <div className={`${baseClass} ${variantClass} ${radiusClass} ${hoverClass} ${className}`} style={style}>
      {/* Subtle shine effect on hover */}
      {hoverable && (
        <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-white/5 to-transparent opacity-0 hover:opacity-100 transition-opacity duration-700 pointer-events-none" />
      )}
      {children}
    </div>
  );
}
