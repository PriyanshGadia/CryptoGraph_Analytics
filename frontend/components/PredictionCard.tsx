import { Asset } from "@/lib/api";
import { ArrowDownRight, ArrowUpRight, TrendingUp, TrendingDown, Minus, Activity, ShieldAlert, Cpu } from "lucide-react";

export function PredictionCard({ asset }: { asset: Asset }) {
  const direction = asset.predicted_direction?.toLowerCase() ?? "neutral";
  const isUp = direction === "up" || direction === "strong_up";
  const isDown = direction === "down" || direction === "strong_down";
  const isStrong = direction.startsWith("strong_");
  const price = asset.current_price;
  const change = asset.price_change_24h_pct;
  const confidence = asset.confidence; // Fix: Assuming confidence is already 0-100 from API

  const statusConfig: Record<string, { bg: string, text: string, border: string, glow: string, label: string, icon: React.ReactNode }> = {
    strong_up: { bg: "bg-[#10b981]/10", text: "text-[#10b981]", border: "border-[#10b981]/30", glow: "shadow-[0_0_15px_rgba(16,185,129,0.2)]", label: "STRONG BUY", icon: <TrendingUp size={14}/> },
    up: { bg: "bg-[#34d399]/10", text: "text-[#34d399]", border: "border-[#34d399]/20", glow: "", label: "BUY", icon: <TrendingUp size={14}/> },
    down: { bg: "bg-[#fb923c]/10", text: "text-[#fb923c]", border: "border-[#fb923c]/20", glow: "", label: "SELL", icon: <TrendingDown size={14}/> },
    strong_down: { bg: "bg-[#f43f5e]/10", text: "text-[#f43f5e]", border: "border-[#f43f5e]/30", glow: "shadow-[0_0_15px_rgba(244,63,94,0.2)]", label: "STRONG SELL", icon: <TrendingDown size={14}/> },
    neutral: { bg: "bg-[#94a3b8]/10", text: "text-[#94a3b8]", border: "border-[#94a3b8]/20", glow: "", label: "NEUTRAL", icon: <Minus size={14}/> },
  };

  const c = statusConfig[direction] || statusConfig["neutral"];

  return (
    <div className={`relative group overflow-hidden bg-white/[0.02] border border-white/[0.05] hover:border-indigo-500/30 rounded-2xl p-5 transition-all duration-500 backdrop-blur-xl ${isStrong ? 'hover:shadow-[0_0_30px_rgba(99,102,241,0.15)]' : 'hover:bg-white/[0.04]'}`}>
      
      {/* Background Ambient Glow */}
      <div className={`absolute -top-10 -right-10 w-32 h-32 rounded-full blur-[50px] opacity-20 transition-opacity duration-500 group-hover:opacity-40 ${isUp ? 'bg-emerald-500' : isDown ? 'bg-rose-500' : 'bg-slate-500'}`} />

      {/* Header */}
      <div className="flex justify-between items-start relative z-10">
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <h3 className="text-xl font-black text-white tracking-tight">{asset.symbol}</h3>
            {asset.sector && (
              <span className="text-[9px] px-1.5 py-0.5 rounded border border-white/10 text-slate-400 uppercase tracking-widest font-mono">
                {asset.sector}
              </span>
            )}
          </div>
          <span className="text-xs text-slate-500 mt-0.5 font-light tracking-wide">{asset.name}</span>
        </div>

        <div className="flex flex-col items-end">
          <div className={`font-mono text-lg font-bold tracking-tight transition-colors duration-300 ${price ? 'text-white' : 'text-slate-500'}`}>
            {price != null
              ? `$${price < 1 ? price.toFixed(4) : price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : "—"}
          </div>
          <div className={`text-xs font-bold flex items-center gap-0.5 mt-0.5 transition-colors duration-300 ${change != null && change >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {change != null ? (
              <>
                {change >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                {Math.abs(change).toFixed(2)}%
              </>
            ) : (
              <span className="text-slate-600">—</span>
            )}
          </div>
        </div>
      </div>

      {/* Prediction Metrics Grid */}
      <div className="mt-6 grid grid-cols-2 gap-3 relative z-10">
        
        {/* Signal Chip */}
        <div className="bg-black/40 rounded-xl p-3 border border-white/5 flex flex-col justify-center">
            <span className="text-[9px] text-slate-500 uppercase tracking-widest font-mono mb-1.5 flex items-center gap-1"><Cpu size={10}/> AI Signal</span>
            <div className={`inline-flex w-max items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest border ${c.bg} ${c.text} ${c.border} ${c.glow}`}>
                {c.icon}{c.label}
            </div>
        </div>

        {/* Confidence Meter */}
        <div className="bg-black/40 rounded-xl p-3 border border-white/5 flex flex-col justify-center">
            <div className="flex justify-between items-end mb-1.5">
                <span className="text-[9px] text-slate-500 uppercase tracking-widest font-mono flex items-center gap-1"><Activity size={10}/> Confidence</span>
                <span className="text-xs font-mono font-bold text-white">{confidence != null ? `${confidence.toFixed(1)}%` : "—"}</span>
            </div>
            <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div 
                    className={`h-full rounded-full transition-all duration-1000 ${confidence && confidence > 75 ? 'bg-indigo-500' : confidence && confidence > 60 ? 'bg-indigo-400' : 'bg-slate-500'}`}
                    style={{ width: `${confidence || 0}%` }}
                />
            </div>
        </div>

      </div>
    </div>
  );
}
