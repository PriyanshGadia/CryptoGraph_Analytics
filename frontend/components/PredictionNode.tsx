"use client";

import { Asset } from "@/lib/api";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { useCallback, useRef } from "react";
import { useCurrency } from "./CurrencyContext";
import { clampToViewport } from "@/lib/utils";

// Fixed estimate of the popup footprint, used only for viewport-clamp math.
const POPUP_W = 320;
const POPUP_H = 280;

interface PredictionNodeProps {
  asset: Asset;
  onHoverChange?: (asset: Asset | null, pos: { top: number; left: number } | null) => void;
}

export function PredictionNode({ asset, onHoverChange }: PredictionNodeProps) {
  const anchorRef = useRef<HTMLDivElement>(null);
  const { formatPrice } = useCurrency();

  // @ts-ignore
  const direction = (asset.predicted_direction || asset.direction)?.toLowerCase() ?? "neutral";
  const isUp = direction === "up" || direction === "strong_up";
  const isDown = direction === "down" || direction === "strong_down";
  const price = asset.current_price;
  const change = asset.price_change_24h_pct;

  // Safe crypto icon url via jsdelivr (atomiclabs)
  const iconUrl = `https://cdn.jsdelivr.net/gh/atomiclabs/cryptocurrency-icons@1a63530be6e374711a8554f31b17e4cb92c25fa5/svg/color/${asset.symbol.toLowerCase()}.svg`;

  const handleEnter = useCallback(() => {
    if (anchorRef.current && onHoverChange) {
      const rect = anchorRef.current.getBoundingClientRect();
      const calculatedPos = clampToViewport(rect, POPUP_W, POPUP_H);
      onHoverChange(asset, calculatedPos);
    }
  }, [asset, onHoverChange]);

  const handleLeave = useCallback(() => {
    onHoverChange?.(null, null);
  }, [onHoverChange]);

  return (
    <div
      ref={anchorRef}
      className="relative flex flex-col cursor-pointer group transition-all duration-300 w-full"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      {/* COMPACT RECTANGULAR CARD PANEL */}
      <div
        className="relative flex items-center justify-between w-full h-[76px] rounded-lg glass bg-surface/30 border transition-all duration-300 ease-out p-3.5 border-text/5 hover:border-accent/40 hover:bg-surface/60 hover:shadow-[0_0_15px_rgba(var(--accent),0.15)] hover:-translate-y-[2px]"
      >
        {/* Subtle background glow matching prediction on hover */}
        <div className={`absolute inset-0 rounded-lg transition-opacity duration-300 opacity-0 group-hover:opacity-[0.03] ${
          isUp ? 'bg-success' : isDown ? 'bg-danger' : 'bg-text-muted'
        } pointer-events-none`} />

        {/* Left Section: Icon & Info */}
        <div className="flex items-center min-w-0">
          <div className="w-8 h-8 shape-node overflow-hidden flex items-center justify-center bg-black/10 border border-text/5 p-1 shrink-0">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={iconUrl}
              alt={asset.symbol}
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none';
                (e.target as HTMLImageElement).parentElement!.innerHTML = `<span class="text-[9px] font-black text-text-muted">${asset.symbol[0]}</span>`;
              }}
              className="w-full h-full object-contain"
            />
          </div>
          <div className="ml-3 min-w-0 flex flex-col justify-center">
            <span className="text-sm font-black tracking-tight text-text leading-none font-sans uppercase">{asset.symbol}</span>
            <span className="text-[8px] font-bold text-text-muted uppercase tracking-widest font-mono mt-1 truncate max-w-[80px]">
              {asset.sector || "General"}
            </span>
          </div>
        </div>

        {/* Center/Right Section: Price & Change */}
        <div className="text-right shrink-0 flex flex-col items-end justify-center">
          <span className="text-xs font-bold font-mono text-text leading-none">
            {price != null ? formatPrice(price) : "—"}
          </span>
          <div className="flex items-center gap-1 mt-1 leading-none">
            <span className={`text-[9px] font-mono font-bold ${change != null && change > 0 ? 'text-success' : change != null && change < 0 ? 'text-danger' : 'text-text-muted'}`}>
              {change != null ? `${change > 0 ? '+' : ''}${change.toFixed(2)}%` : "—"}
            </span>
            {isUp && <ArrowUpRight size={10} className="text-success" />}
            {isDown && <ArrowDownRight size={10} className="text-danger" />}
            {!isUp && !isDown && <Minus size={10} className="text-text-muted" />}
          </div>
        </div>
      </div>
    </div>
  );
}

