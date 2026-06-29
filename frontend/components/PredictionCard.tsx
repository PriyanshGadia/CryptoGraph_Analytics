import { Asset } from "@/lib/api";
import { ArrowDownRight, ArrowUpRight, TrendingUp, TrendingDown, Minus, Cpu } from "lucide-react";
import { DIRECTION_TOKENS, Direction } from "@/lib/design-tokens";
import { GlassCard } from "./ui/GlassCard";

export function PredictionCard({ asset }: { asset: Asset }) {
  const direction = asset.predicted_direction?.toLowerCase() ?? "neutral";
  const isUp = direction === "up" || direction === "strong_up";
  const isDown = direction === "down" || direction === "strong_down";
  const isStrong = direction.startsWith("strong_");
  const price = asset.current_price;
  const change = asset.price_change_24h_pct;
  const confidence = asset.confidence || 0; 

  const safeDirection = (direction in DIRECTION_TOKENS ? direction : "neutral") as Direction;
  const t = DIRECTION_TOKENS[safeDirection];
  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : Minus;

  // Calculate SVG stroke-dasharray for radial progress
  const radius = 18;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (confidence / 100) * circumference;
  return (
    <GlassCard tier={2} shape="none" hoverable className={`rounded-xl p-6 depth-bevel ${isStrong ? 'hover:border-accent/50 hover:shadow-[0_0_30px_rgba(var(--accent),0.15)]' : 'hover:border-white/20'}`}>
      
      {/* Background Ambient Glow */}
      <div className={`absolute -top-10 -right-10 w-40 h-40 rounded-full blur-[60px] opacity-10 transition-opacity duration-700 group-hover:opacity-30 ${isUp ? 'bg-success' : isDown ? 'bg-danger' : 'bg-accent'}`} />

      {/* Verdict Stamp */}
      {isStrong && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0 overflow-hidden opacity-10 group-hover:opacity-20 transition-opacity duration-500">
          <div 
            className={`w-48 h-48 flex items-center justify-center border-[8px] ${isUp ? 'border-success text-success' : 'border-danger text-danger'} 
            animate-in zoom-in-150 duration-500 ease-out`}
            style={{ 
              clipPath: 'polygon(30% 0%, 70% 0%, 100% 30%, 100% 70%, 70% 100%, 30% 100%, 0% 70%, 0% 30%)', 
              transform: 'rotate(-15deg)'
            }}
          >
            <div className="border-y-4 border-current py-2 px-6 w-full text-center transform -rotate-12 mt-2">
              <span className="font-black text-3xl uppercase tracking-widest">{isUp ? 'LONG' : 'SHORT'}</span>
            </div>
          </div>
        </div>
      )}

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
                {Math.abs(change).toFixed(3)}%
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
        <div className="bg-surface/30 rounded-sm p-4 border border-white/5 flex flex-col justify-center gap-2">
            <span className="text-[10px] text-text-muted uppercase tracking-[0.2em] font-mono flex items-center gap-1.5"><Cpu size={12} className="text-accent"/> AI SIGNAL</span>
            <div className={`inline-flex w-max items-center gap-2 px-3 py-3 rounded-lg text-xs font-bold uppercase tracking-widest border ${t.bgClass} ${t.textClass} ${t.borderClass}`} style={{ boxShadow: t.glow !== 'none' ? t.glow : undefined }}>
                <Icon size={14}/>{t.label}
            </div>
        </div>

        {/* Conformal Prediction Interval or Fallback Radial */}
        <div className="bg-surface/30 rounded-sm p-4 border border-white/5 flex flex-col items-center justify-center relative min-w-[80px]">
            {asset.confidence_interval ? (
              <div className="flex flex-col w-full gap-1">
                <div className="flex justify-between items-center text-[10px] font-mono text-text-muted">
                  <span>{asset.confidence_interval[0].toFixed(1)}%</span>
                  <span>{asset.confidence_interval[1].toFixed(1)}%</span>
                </div>
                <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden relative">
                  {/* The active band */}
                  <div 
                    className="absolute h-full bg-accent/80 rounded-full" 
                    style={{ 
                      left: `${asset.confidence_interval[0]}%`, 
                      width: `${asset.confidence_interval[1] - asset.confidence_interval[0]}%` 
                    }} 
                  />
                  {/* The point estimate */}
                  <div 
                    className="absolute h-full w-0.5 bg-white shadow-[0_0_5px_white]"
                    style={{ left: `${confidence}%` }}
                  />
                </div>
                <span className="text-[8px] text-center text-text-muted uppercase tracking-widest mt-1">Conformal Band</span>
              </div>
            ) : (
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
            )}
        </div>
      </div>
    </GlassCard>
  );
}

