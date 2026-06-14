import { Asset } from "@/lib/api";
import { ArrowDownRight, ArrowUpRight, TrendingUp, TrendingDown, Minus, Activity, ShieldAlert, Cpu } from "lucide-react";
import { useState } from "react";

export function PredictionNode({ asset }: { asset: Asset }) {
  const [isHovered, setIsHovered] = useState(false);

  // @ts-ignore
  const direction = (asset.predicted_direction || asset.direction)?.toLowerCase() ?? "neutral";
  const isUp = direction === "up" || direction === "strong_up";
  const isDown = direction === "down" || direction === "strong_down";
  const price = asset.current_price;
  const change = asset.price_change_24h_pct;
  const confidence = asset.confidence;

  const statusConfig: Record<string, { bg: string, text: string, shadow: string, label: string, borderAccent: string }> = {
    strong_up: { bg: "bg-emerald-500", text: "text-emerald-50", shadow: "shadow-[0_0_20px_rgba(16,185,129,0.4)]", label: "STRONG BUY", borderAccent: "border-emerald-500/50 shadow-[inset_0_0_15px_rgba(16,185,129,0.1)]" },
    up: { bg: "bg-emerald-400", text: "text-emerald-950", shadow: "shadow-[0_0_15px_rgba(52,211,153,0.3)]", label: "BUY", borderAccent: "border-emerald-400/40 shadow-[inset_0_0_10px_rgba(52,211,153,0.1)]" },
    down: { bg: "bg-orange-500", text: "text-orange-50", shadow: "shadow-[0_0_15px_rgba(249,115,22,0.3)]", label: "SELL", borderAccent: "border-orange-500/40 shadow-[inset_0_0_10px_rgba(249,115,22,0.1)]" },
    strong_down: { bg: "bg-rose-500", text: "text-rose-50", shadow: "shadow-[0_0_20px_rgba(244,63,94,0.4)]", label: "STRONG SELL", borderAccent: "border-rose-500/50 shadow-[inset_0_0_15px_rgba(244,63,94,0.1)]" },
    neutral: { bg: "bg-slate-500", text: "text-slate-50", shadow: "shadow-[0_0_10px_rgba(100,116,139,0.2)]", label: "NEUTRAL", borderAccent: "border-white/10" },
  };

  const c = statusConfig[direction] || statusConfig["neutral"];
  
  // Safe crypto icon url via jsdelivr (atomiclabs)
  const iconUrl = `https://cdn.jsdelivr.net/gh/atomiclabs/cryptocurrency-icons@1a63530be6e374711a8554f31b17e4cb92c25fa5/svg/color/${asset.symbol.toLowerCase()}.svg`;

  const formatPrice = (p: number | undefined | null) => {
    if (p == null) return "—";
    const str = p.toString();
    if (str.includes("e")) return p.toPrecision(4);
    
    const parts = str.split('.');
    const intLen = parts[0] === '0' ? 1 : parts[0].length;
    
    if (intLen >= 7) return Math.floor(p).toLocaleString('en-US');
    
    let allowedFrac = 7 - intLen;
    if (p >= 1 && allowedFrac < 2) allowedFrac = 2;
    
    return p.toLocaleString('en-US', { minimumFractionDigits: p < 1 ? 0 : 2, maximumFractionDigits: allowedFrac });
  };

  return (
    <div 
      className={`relative flex items-center justify-center cursor-pointer group transition-all duration-200 ${isHovered ? 'z-50' : 'z-10'}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* THE PILL NODE */}
      <div className={`relative flex items-center gap-2.5 px-3 py-1.5 rounded-full border bg-[#0a0e17]/80 backdrop-blur-xl transition-all duration-500 ${isHovered ? `scale-110 z-20 ${c.borderAccent}` : `hover:bg-white/10 ${c.borderAccent}`}`}>
        
        {/* Crypto Icon */}
        <div className="w-5 h-5 rounded-full bg-white/5 flex items-center justify-center overflow-hidden border border-white/10 p-0.5">
            <img 
                src={iconUrl} 
                alt={asset.symbol} 
                onError={(e) => {
                    // Fallback to a generic circle with first letter if icon not found
                    (e.target as HTMLImageElement).style.display = 'none';
                    (e.target as HTMLImageElement).parentElement!.innerHTML = `<span class="text-[10px] font-bold text-white">${asset.symbol[0]}</span>`;
                }}
                className="w-full h-full object-contain"
            />
        </div>
        
        <span className="font-bold text-white tracking-wide text-sm">{asset.symbol}</span>
        
        <div className="flex items-center gap-1.5 ml-1">
            <span className={`text-xs font-mono tracking-tight ${price ? 'text-slate-300' : 'text-slate-600'}`}>
                {price != null ? `$${formatPrice(price)}` : "—"}
            </span>
            {change != null && (
                <span className={`text-[10px] font-bold flex items-center ${change >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {change >= 0 ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                    {Math.abs(change).toFixed(1)}%
                </span>
            )}
        </div>
      </div>

      {/* THE HOVER POPUP (Glassmorphic Detail Card) */}
      <div className={`absolute bottom-full left-1/2 -translate-x-1/2 mb-4 w-64 rounded-2xl bg-[#0a0e17]/90 backdrop-blur-3xl border border-white/10 p-4 transition-all duration-300 origin-bottom pointer-events-none shadow-2xl ${isHovered ? 'opacity-100 scale-100 z-50' : 'opacity-0 scale-95 z-0'}`}>
        
        {/* Glow behind popup */}
        <div className={`absolute inset-0 rounded-2xl opacity-10 blur-xl ${c.bg}`} />
        
        <div className="relative z-10">
            <div className="flex justify-between items-start mb-3">
                <div>
                    <h3 className="text-white font-bold text-lg leading-none">{asset.name}</h3>
                    <span className="text-[9px] text-slate-400 uppercase tracking-widest font-mono mt-1 block">{asset.sector || "Unknown"}</span>
                </div>
                <div className={`text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-widest ${c.bg} ${c.text}`}>
                    {c.label}
                </div>
            </div>

            <div className="grid grid-cols-2 gap-2 mt-4">
                <div className="bg-black/40 rounded-lg p-2 border border-white/5">
                    <span className="text-[8px] text-slate-500 uppercase tracking-widest font-mono block mb-1">Confidence</span>
                    <span className="text-xs font-mono font-bold text-white">{confidence != null ? `${confidence.toFixed(1)}%` : "—"}</span>
                </div>
                <div className="bg-black/40 rounded-lg p-2 border border-white/5">
                    <span className="text-[8px] text-slate-500 uppercase tracking-widest font-mono block mb-1">Volatility</span>
                    <span className="text-xs font-mono font-bold text-white capitalize">{asset.volatility_regime || "Normal"}</span>
                </div>
                <div className="bg-black/40 rounded-lg p-2 border border-white/5">
                    <span className="text-[8px] text-slate-500 uppercase tracking-widest font-mono block mb-1">RSI (14D)</span>
                    <span className={`text-xs font-mono font-bold ${asset.rsi_14 != null && asset.rsi_14 > 70 ? 'text-rose-400' : asset.rsi_14 != null && asset.rsi_14 < 30 ? 'text-emerald-400' : 'text-white'}`}>
                        {asset.rsi_14 != null ? asset.rsi_14.toFixed(1) : "—"}
                    </span>
                </div>
                <div className="bg-black/40 rounded-lg p-2 border border-white/5">
                    <span className="text-[8px] text-slate-500 uppercase tracking-widest font-mono block mb-1">MACD</span>
                    <span className={`text-xs font-mono font-bold ${asset.macd != null && asset.macd > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {asset.macd != null ? asset.macd.toFixed(4) : "—"}
                    </span>
                </div>
            </div>
            <div className="mt-3 text-center">
                <span className="text-[9px] text-indigo-400 tracking-widest font-mono uppercase">Click for Deep Analysis</span>
            </div>
        </div>
        
        {/* Downward triangle pointer */}
        <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-4 h-4 bg-[#0a0e17]/90 border-b border-r border-white/10 transform rotate-45 backdrop-blur-3xl" />
      </div>
    </div>
  );
}
