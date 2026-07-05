"use client";

import { Asset } from "@/lib/api";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { DIRECTION_TOKENS, Direction } from "@/lib/design-tokens";
import { GlassCard } from "./ui/GlassCard";
import { useCallback, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { useCurrency } from "./CurrencyContext";
import { clampToViewport } from "@/lib/utils";

// Fixed estimate of the popup footprint, used only for viewport-clamp math.
const POPUP_W = 320;
const POPUP_H = 280;

export function PredictionNode({ asset, onHoverChange }: { asset: Asset; onHoverChange?: (hovered: boolean) => void }) {
  const [isHovered, setIsHovered] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const anchorRef = useRef<HTMLDivElement>(null);
  const { formatPrice } = useCurrency();
  const router = useRouter();

  // @ts-ignore
  const direction = (asset.predicted_direction || asset.direction)?.toLowerCase() ?? "neutral";
  const isUp = direction === "up" || direction === "strong_up";
  const isDown = direction === "down" || direction === "strong_down";
  const price = asset.current_price;
  const change = asset.price_change_24h_pct;
  const confidence = asset.confidence;

  const safeDirection = (direction in DIRECTION_TOKENS ? direction : "neutral") as Direction;
  const t = DIRECTION_TOKENS[safeDirection];

  // Safe crypto icon url via jsdelivr (atomiclabs)
  const iconUrl = `https://cdn.jsdelivr.net/gh/atomiclabs/cryptocurrency-icons@1a63530be6e374711a8554f31b17e4cb92c25fa5/svg/color/${asset.symbol.toLowerCase()}.svg`;

  const handleEnter = useCallback(() => {
    if (anchorRef.current) {
      const rect = anchorRef.current.getBoundingClientRect();
      setPos(clampToViewport(rect, POPUP_W, POPUP_H));
    }
    setIsHovered(true);
    onHoverChange?.(true);
  }, [onHoverChange]);

  const handleLeave = useCallback(() => {
    setIsHovered(false);
    onHoverChange?.(false);
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
        className={`relative flex items-center justify-between w-full h-[76px] rounded-lg glass bg-surface/30 border transition-all duration-300 ease-out p-3.5 ${
          isHovered
            ? `border-accent/40 bg-surface/60 shadow-[0_0_15px_rgba(var(--accent),0.15)] -translate-y-[2px]`
            : `border-text/5 hover:border-text/20`
        }`}
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

      {/* DETAILED HOVER PANEL POPUP — portaled to <body> so it's never clipped by an
          ancestor's overflow, and positioned via clampToViewport so it always stays
          fully on-screen regardless of which grid cell it anchors to. */}
      {isHovered && pos && typeof document !== "undefined" && createPortal(
        <div
          className="fixed z-[999] pointer-events-auto animate-in fade-in zoom-in-95 duration-200"
          style={{ top: pos.top, left: pos.left, width: POPUP_W }}
          onMouseEnter={handleEnter}
          onMouseLeave={handleLeave}
          onClick={() => router.push(`/coin/${asset.symbol}`)}
        >
          <GlassCard
            tier={3}
            shape="none"
            className="rounded-2xl border border-text/15 shadow-2xl p-5 relative overflow-hidden bg-surface text-text cursor-pointer"
          >
            {/* Glow behind popup */}
            <div className={`absolute inset-0 opacity-[0.06] blur-xl pointer-events-none ${t.textClass.replace('text-', 'bg-')}`} />

            <div className="relative z-10 space-y-4 text-left">
              {/* Header */}
              <div className="flex justify-between items-start gap-3 border-b border-text/10 pb-2">
                <div className="min-w-0 flex-1">
                  <h3 className="text-text font-black text-base font-sans tracking-tight uppercase truncate">{asset.name}</h3>
                  <span className="text-[10px] text-text-muted uppercase tracking-widest font-mono mt-0.5 block truncate">{asset.sector || "Uncategorized"}</span>
                </div>
                <div className={`shrink-0 shape-tag text-[10px] font-black px-3 py-1 uppercase tracking-widest border ${t.textClass} border-current/25 bg-black/20 font-mono`}>
                  {t.label}
                </div>
              </div>

              {/* Swarm Confidence Bar */}
              {confidence != null && (
                <div className="space-y-1">
                  <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest font-mono text-text-muted">
                    <span>Swarm Conviction</span>
                    <span className={t.textClass}>{confidence.toFixed(1)}%</span>
                  </div>
                  <div className="w-full h-1.5 bg-black/30 rounded-full overflow-hidden border border-text/10 p-[1px]">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        isUp ? 'bg-success' : isDown ? 'bg-danger' : 'bg-text-muted'
                      }`}
                      style={{ width: `${confidence}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Technical Details Grid */}
              <div className="grid grid-cols-2 gap-2 text-left">
                <div className="bg-black/20 rounded-lg p-2.5 border border-text/10">
                  <span className="text-[9px] text-text-muted uppercase tracking-widest font-mono block mb-1">24h Vol</span>
                  <span className="text-sm font-mono font-bold text-text">
                    {asset.volume_24h != null ? `$${((asset.volume_24h) / 1000000).toFixed(1)}M` : "—"}
                  </span>
                </div>
                <div className="bg-black/20 rounded-lg p-2.5 border border-text/10">
                  <span className="text-[9px] text-text-muted uppercase tracking-widest font-mono block mb-1">RSI (14D)</span>
                  <span className={`text-sm font-mono font-bold ${asset.rsi_14 != null && asset.rsi_14 > 70 ? 'text-danger' : asset.rsi_14 != null && asset.rsi_14 < 30 ? 'text-success' : 'text-text'}`}>
                    {asset.rsi_14 != null ? asset.rsi_14.toFixed(1) : "—"}
                  </span>
                </div>
                <div className="bg-black/20 rounded-lg p-2.5 border border-text/10 col-span-2">
                  <span className="text-[9px] text-text-muted uppercase tracking-widest font-mono block mb-1">MACD Signal</span>
                  <span className={`text-sm font-mono font-bold ${asset.macd != null && asset.macd > 0 ? 'text-success' : 'text-danger'}`}>
                    {asset.macd != null ? asset.macd.toFixed(4) : "—"}
                  </span>
                </div>
              </div>

              {/* CTA Footer */}
              <div className="pt-2 border-t border-text/10 text-center flex items-center justify-center gap-1.5 text-[10px] text-text tracking-[0.2em] font-mono uppercase font-black">
                <span>Explore Neural Profile</span>
                <ArrowUpRight size={11} className="tracking-normal animate-pulse" />
              </div>
            </div>
          </GlassCard>
        </div>,
        document.body
      )}
    </div>
  );
}
