import { Asset } from "@/lib/api";
import { ArrowDownRight, ArrowUpRight, TrendingUp, TrendingDown, Minus, Activity, ShieldAlert, Cpu } from "lucide-react";
import { DIRECTION_TOKENS, Direction } from "@/lib/design-tokens";
import { GlassCard } from "./ui/GlassCard";
import { useState } from "react";
import { useCurrency } from "./CurrencyContext";

export function PredictionNode({ asset }: { asset: Asset }) {
  const [isHovered, setIsHovered] = useState(false);
  const { formatPrice } = useCurrency();

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

  return (
    <div 
      className={`relative flex items-center justify-center cursor-pointer group transition-all duration-300 ${isHovered ? 'z-[100]' : 'z-10'}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* THE ORGANIC BLOB NODE */}
      <div 
        className={`relative flex items-center gap-2.5 px-4 py-2 glass-1 shape-facet-sm transition-all duration-[var(--dur-hover)] ease-glide ${isHovered ? `scale-110 z-20 ${t.borderClass}` : `hover:bg-white/10 border-white/5`}`}
      >
        {/* Glow */}
        <div className={`absolute inset-0 transition-opacity duration-[var(--dur-hover)] ease-glide opacity-20 ${t.textClass.replace('text-', 'bg-')} blur-md rounded-full -z-10 ${isHovered ? 'opacity-40 scale-125' : ''}`} />
        
        {/* Crypto Icon */}
        <div className="w-6 h-6 rounded-sm bg-surface/50 flex items-center justify-center overflow-hidden border border-white/10 p-0.5 shadow-inner">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img 
                src={iconUrl} 
                alt={asset.symbol} 
                onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                    (e.target as HTMLImageElement).parentElement!.innerHTML = `<span class="text-[10px] font-bold text-text">${asset.symbol[0]}</span>`;
                }}
                className="w-full h-full object-contain"
            />
        </div>
        
        <div className="flex flex-col pr-1">
          <span className="font-bold text-text tracking-wide text-sm leading-tight">{asset.symbol}</span>
          <div className="flex items-center gap-1.5">
            {change != null && (
                <span className={`text-[9px] font-bold flex items-center tracking-widest ${change >= 0 ? "text-success" : "text-danger"}`}>
                    {change >= 0 ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                    {Math.abs(change).toFixed(1)}%
                </span>
            )}
          </div>
        </div>
      </div>

      {/* THE HOVER POPUP (Glassmorphic Detail Card) */}
      <GlassCard tier={3} shape="shape-squircle" className={`absolute bottom-full left-1/2 -translate-x-1/2 mb-4 w-72 p-5 transition-all duration-[var(--dur-hover)] ease-glide origin-bottom pointer-events-none depth-bevel ${isHovered ? 'opacity-100 scale-100 z-[100] translate-y-0' : 'opacity-0 scale-95 z-0 translate-y-4'}`}>
        
        {/* Glow behind popup */}
        <div className={`absolute inset-0 opacity-10 blur-xl ${t.textClass.replace('text-', 'bg-')}`} />
        
        <div className="relative z-10">
            <div className="flex justify-between items-start mb-4">
                <div>
                    <h3 className="text-text font-black text-xl leading-none font-sans tracking-tight">{asset.name}</h3>
                    <span className="text-[10px] text-text-muted uppercase tracking-widest font-mono mt-1 block bg-surface/50 px-2 py-0.5 rounded-sm w-max border border-white/5">{asset.sector || "Unknown"}</span>
                </div>
                <div className={`text-[9px] font-bold px-2 py-1 shape-facet-sm uppercase tracking-widest border ${t.textClass} border-current/30 shadow-[0_0_10px_currentColor] bg-currentColor/10`}>
                    {t.label}
                </div>
            </div>

            <div className="grid grid-cols-2 gap-3 mt-5">
                <div className="bg-surface/40 rounded-sm p-2.5 border border-white/5">
                    <span className="text-[9px] text-text-muted/80 uppercase tracking-widest font-mono block mb-1">Confidence</span>
                    <span className="text-sm font-mono font-bold text-text">{confidence != null ? `${confidence.toFixed(1)}%` : "—"}</span>
                </div>
                <div className="bg-surface/40 rounded-sm p-2.5 border border-white/5">
                    <span className="text-[9px] text-text-muted/80 uppercase tracking-widest font-mono block mb-1">Price</span>
                    <span className="text-sm font-mono font-bold text-text capitalize">{price != null ? formatPrice(price) : "—"}</span>
                </div>
                <div className="bg-surface/40 rounded-sm p-2.5 border border-white/5">
                    <span className="text-[9px] text-text-muted/80 uppercase tracking-widest font-mono block mb-1">RSI (14D)</span>
                    <span className={`text-sm font-mono font-bold ${asset.rsi_14 != null && asset.rsi_14 > 70 ? 'text-danger' : asset.rsi_14 != null && asset.rsi_14 < 30 ? 'text-success' : 'text-text'}`}>
                        {asset.rsi_14 != null ? asset.rsi_14.toFixed(1) : "—"}
                    </span>
                </div>
                <div className="bg-surface/40 rounded-sm p-2.5 border border-white/5">
                    <span className="text-[9px] text-text-muted/80 uppercase tracking-widest font-mono block mb-1">MACD</span>
                    <span className={`text-sm font-mono font-bold ${asset.macd != null && asset.macd > 0 ? 'text-success' : 'text-danger'}`}>
                        {asset.macd != null ? asset.macd.toFixed(4) : "—"}
                    </span>
                </div>
            </div>
            <div className="mt-4 pt-3 border-t border-white/10 text-center">
                <span className="text-[9px] text-accent tracking-[0.2em] font-mono uppercase font-bold">Click for Deep Analysis</span>
            </div>
        </div>
        
        {/* Downward triangle pointer */}
        <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-4 h-4 bg-background border-b border-r border-white/10 transform rotate-45 backdrop-blur-3xl" />
      </GlassCard>
    </div>
  );
}

