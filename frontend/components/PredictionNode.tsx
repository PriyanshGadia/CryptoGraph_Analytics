import { Asset } from "@/lib/api";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
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
      className={`relative flex flex-col cursor-pointer group transition-all duration-300 w-full ${isHovered ? 'z-50' : 'z-10'}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* COMPACT RECTANGULAR CARD PANEL */}
      <div 
        className={`relative flex items-center justify-between w-full h-[64px] rounded-sm glass bg-surface/30 border transition-all duration-300 ease-out p-3.5 ${
          isHovered 
            ? `border-accent/40 bg-surface/60 shadow-[0_0_15px_rgba(var(--accent),0.15)] -translate-y-[2px]` 
            : `border-text/5 hover:border-text/20`
        }`}
      >
        {/* Subtle background glow matching prediction on hover */}
        <div className={`absolute inset-0 rounded-sm transition-opacity duration-300 opacity-0 group-hover:opacity-[0.03] ${
          isUp ? 'bg-success' : isDown ? 'bg-danger' : 'bg-text-muted'
        } pointer-events-none`} />

        {/* Left Section: Icon & Info */}
        <div className="flex items-center min-w-0">
          <div className="w-8 h-8 rounded-sm overflow-hidden flex items-center justify-center bg-black/10 border border-text/5 p-1 shrink-0">
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

      {/* THE HOVER POPUP (Premium Floating Panel) */}
      <GlassCard 
        tier={3} 
        shape="none" 
        className={`rounded-sm absolute bottom-full left-1/2 -translate-x-1/2 mb-3.5 w-72 p-4 transition-all duration-300 ease-out origin-bottom pointer-events-none border border-text/10 shadow-2xl ${
          isHovered 
            ? 'opacity-100 scale-100 z-50 translate-y-0 visible' 
            : 'opacity-0 scale-95 z-0 translate-y-2 invisible'
        }`}
      >
        {/* Glow behind popup */}
        <div className={`absolute inset-0 opacity-[0.02] blur-xl pointer-events-none ${t.textClass.replace('text-', 'bg-')}`} />
        
        <div className="relative z-10 space-y-3 text-left">
          {/* Header */}
          <div className="flex justify-between items-start border-b border-text/5 pb-2">
            <div className="min-w-0 flex-1 mr-2">
              <h3 className="text-text font-black text-sm font-sans tracking-tight uppercase truncate">{asset.name}</h3>
              <span className="text-[8px] text-text-muted uppercase tracking-widest font-mono mt-0.5 block truncate">{asset.sector || "Uncategorized"}</span>
            </div>
            <div className={`text-[8px] font-black px-2 py-0.5 rounded-sm uppercase tracking-widest border ${t.textClass} border-current/25 bg-surface/50 font-mono shrink-0`}>
              {t.label}
            </div>
          </div>

          {/* Swarm Confidence Bar */}
          {confidence != null && (
            <div className="space-y-1">
              <div className="flex justify-between text-[8px] font-bold uppercase tracking-widest font-mono text-text-muted">
                <span>Swarm Conviction</span>
                <span className={t.textClass}>{confidence.toFixed(1)}%</span>
              </div>
              <div className="w-full h-1.5 bg-black/35 rounded-full overflow-hidden border border-text/5 p-[1px]">
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
            <div className="bg-black/20 rounded-sm p-2 border border-text/5">
              <span className="text-[8px] text-text-muted uppercase tracking-widest font-mono block mb-0.5">24h Vol</span>
              <span className="text-xs font-mono font-bold text-text">
                {asset.volume_24h != null ? `$${((asset.volume_24h) / 1000000).toFixed(1)}M` : "—"}
              </span>
            </div>
            <div className="bg-black/20 rounded-sm p-2 border border-text/5">
              <span className="text-[8px] text-text-muted uppercase tracking-widest font-mono block mb-0.5">RSI (14D)</span>
              <span className={`text-xs font-mono font-bold ${asset.rsi_14 != null && asset.rsi_14 > 70 ? 'text-danger' : asset.rsi_14 != null && asset.rsi_14 < 30 ? 'text-success' : 'text-text'}`}>
                {asset.rsi_14 != null ? asset.rsi_14.toFixed(1) : "—"}
              </span>
            </div>
            <div className="bg-black/20 rounded-sm p-2 border border-text/5 col-span-2">
              <span className="text-[8px] text-text-muted uppercase tracking-widest font-mono block mb-0.5">MACD Signal</span>
              <span className={`text-xs font-mono font-bold ${asset.macd != null && asset.macd > 0 ? 'text-success' : 'text-danger'}`}>
                {asset.macd != null ? asset.macd.toFixed(4) : "—"}
              </span>
            </div>
          </div>

          {/* CTA Footer */}
          <div className="pt-2 border-t border-text/5 text-center flex items-center justify-center gap-1.5 text-[8px] text-accent tracking-[0.2em] font-mono uppercase font-black">
            <span>Explore Neural Profile</span>
            <ArrowUpRight size={10} className="tracking-normal animate-pulse" />
          </div>
        </div>
        
        {/* Downward triangle pointer */}
        <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-surface border-b border-r border-text/10 transform rotate-45 backdrop-blur-3xl" />
      </GlassCard>
    </div>
  );
}
