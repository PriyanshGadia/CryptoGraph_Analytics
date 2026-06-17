import { Asset } from "@/lib/api";
import { ArrowDownRight, ArrowUpRight, TrendingUp, TrendingDown, Minus, Cpu } from "lucide-react";

export function PredictionCard({ asset }: { asset: Asset }) {
  const direction = asset.predicted_direction?.toLowerCase() ?? "neutral";
  const isUp = direction === "up" || direction === "strong_up";
  const isDown = direction === "down" || direction === "strong_down";
  const isStrong = direction.startsWith("strong_");
  const price = asset.current_price;
  const change = asset.price_change_24h_pct;
  const confidence = asset.confidence || 0; 

  const statusConfig: Record<string, { bg: string, text: string, border: string, glow: string, label: string, icon: React.ReactNode }> = {
    strong_up: { bg: "bg-success/10", text: "text-success", border: "border-success/30", glow: "shadow-[0_0_15px_rgba(34,197,94,0.3)]", label: "STRONG BUY", icon: <TrendingUp size={14}/> },
    up: { bg: "bg-success/5", text: "text-success", border: "border-success/20", glow: "", label: "BUY", icon: <TrendingUp size={14}/> },
    down: { bg: "bg-danger/5", text: "text-danger", border: "border-danger/20", glow: "", label: "SELL", icon: <TrendingDown size={14}/> },
    strong_down: { bg: "bg-danger/10", text: "text-danger", border: "border-danger/30", glow: "shadow-[0_0_15px_rgba(239,68,68,0.3)]", label: "STRONG SELL", icon: <TrendingDown size={14}/> },
    neutral: { bg: "bg-text-muted/10", text: "text-text-muted", border: "border-text-muted/20", glow: "", label: "NEUTRAL", icon: <Minus size={14}/> },
  };

  const c = statusConfig[direction] || statusConfig["neutral"];

  // Calculate SVG stroke-dasharray for radial progress
  const radius = 18;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (confidence / 100) * circumference;

  return (
    <div className={`relative group glass-panel p-6 transition-all duration-500 hover:scale-[1.02] hover:-translate-y-1 ${isStrong ? 'hover:shadow-[0_0_30px_rgba(var(--accent),0.15)] hover:border-accent/50' : 'hover:border-white/20'}`} style={{ clipPath: 'polygon(5% 0, 95% 0, 100% 5%, 100% 95%, 95% 100%, 5% 100%, 0 95%, 0 5%)' }}>
      
      {/* Background Ambient Glow */}
      <div className={`absolute -top-10 -right-10 w-40 h-40 rounded-full blur-[60px] opacity-10 transition-opacity duration-700 group-hover:opacity-30 ${isUp ? 'bg-success' : isDown ? 'bg-danger' : 'bg-accent'}`} />

      {/* Header */}
      <div className="flex justify-between items-start relative z-10 mb-6">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-3">
            <h3 className="text-3xl font-black text-text tracking-tight font-sans">{asset.symbol}</h3>
            {asset.sector && (
              <span className="text-[10px] px-2 py-1 rounded bg-white/5 border border-white/10 text-text-muted uppercase tracking-widest font-mono">
                {asset.sector}
              </span>
            )}
          </div>
          <span className="text-sm text-text-muted/80 font-light tracking-wide">{asset.name}</span>
        </div>

        <div className="flex flex-col items-end">
          <div className={`font-mono text-xl font-bold tracking-tight transition-colors duration-300 ${price ? 'text-text' : 'text-text-muted'}`}>
            {price != null
              ? `$${price < 1 ? price.toFixed(4) : price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : "—"}
          </div>
          <div className={`text-sm font-bold flex items-center gap-1 mt-1 transition-colors duration-300 ${change != null && change >= 0 ? "text-success" : "text-danger"}`}>
            {change != null ? (
              <>
                {change >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                {Math.abs(change).toFixed(2)}%
              </>
            ) : (
              <span className="text-text-muted">—</span>
            )}
          </div>
        </div>
      </div>

      {/* Prediction Metrics Grid */}
      <div className="grid grid-cols-[1fr_auto] gap-4 relative z-10 items-center">
        
        {/* Signal Chip */}
        <div className="bg-surface/30 rounded-crypto p-4 border border-white/5 flex flex-col justify-center gap-2">
            <span className="text-[10px] text-text-muted uppercase tracking-[0.2em] font-mono flex items-center gap-1.5"><Cpu size={12} className="text-accent"/> AI SIGNAL</span>
            <div className={`inline-flex w-max items-center gap-2 px-3 py-1.5 rounded-sm text-xs font-bold uppercase tracking-widest border ${c.bg} ${c.text} ${c.border} ${c.glow}`}>
                {c.icon}{c.label}
            </div>
        </div>

        {/* Radial Confidence Meter */}
        <div className="bg-surface/30 rounded-crypto p-4 border border-white/5 flex items-center justify-center relative">
            <div className="relative flex items-center justify-center">
              <svg className="transform -rotate-90 w-14 h-14">
                <circle cx="28" cy="28" r="18" stroke="currentColor" strokeWidth="4" fill="transparent" className="text-white/10" />
                <circle cx="28" cy="28" r="18" stroke="currentColor" strokeWidth="4" fill="transparent" strokeDasharray={circumference} strokeDashoffset={strokeDashoffset} className={`${confidence > 75 ? 'text-accent' : confidence > 50 ? 'text-accent/60' : 'text-text-muted'} transition-all duration-1000 ease-out`} strokeLinecap="round" />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-[10px] font-mono font-bold text-text">{confidence.toFixed(0)}</span>
                <span className="text-[8px] font-mono text-text-muted">%</span>
              </div>
            </div>
        </div>
      </div>
    </div>
  );
}
