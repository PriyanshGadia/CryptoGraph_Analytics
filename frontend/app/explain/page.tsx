"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, Asset, apiService, ExplainResponse } from "@/lib/api";
import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { MessageSquare, Bot, AlertCircle } from "lucide-react";

export default function ExplainPage() {
  const { data: assets, isLoading: assetsLoading } = useSWR<Asset[]>("/api/assets", fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 30000,
  });
  const [selectedSymbol, setSelectedSymbol] = useState<string>("ETH");
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null);
  const [isExplaining, setIsExplaining] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExplain = async () => {
    if (!selectedSymbol) return;
    
    setIsExplaining(true);
    setError(null);
    try {
      const data = await apiService.getExplain(selectedSymbol);
      setExplanation(data);
    } catch (err: any) {
      setError(err.message || "Failed to generate explanation");
    } finally {
      setIsExplaining(false);
    }
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto pt-8">
      <div>
        <h1 className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted tracking-tight font-sans">Explain Predictions</h1>
        <p className="text-text-muted font-light tracking-wide mt-2">Get LLM-generated rationale behind the ST-GCN forecasting.</p>
      </div>

      <GlassCard variant="auto" asymmetric="lg" className="p-8 relative overflow-hidden">
        {/* Glow */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-accent/5 rounded-full blur-[80px] pointer-events-none" />
        
        <h2 className="text-sm font-bold font-mono tracking-widest uppercase text-accent mb-6">Select Asset</h2>
        <div className="flex flex-col sm:flex-row gap-4 relative z-10">
          <select
            value={selectedSymbol}
            onChange={(e) => setSelectedSymbol(e.target.value)}
            className="flex-1 bg-surface/50 border border-white/10 rounded-crypto-sm px-5 py-3 text-text focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/50 transition-all font-mono"
            disabled={assetsLoading || isExplaining}
          >
            {assetsLoading ? (
              <option>Loading assets...</option>
            ) : (
              assets?.map((asset) => (
                <option key={asset.id} value={asset.symbol}>
                  {asset.symbol} - {asset.name}
                </option>
              ))
            )}
          </select>
          <button
            onClick={handleExplain}
            disabled={!selectedSymbol || isExplaining || assetsLoading}
            className="glass bg-accent/20 hover:bg-accent/30 text-accent px-8 py-3 rounded-crypto-sm font-bold flex justify-center items-center gap-3 disabled:opacity-50 transition-all border border-accent/30 hover:shadow-[0_0_15px_rgba(var(--accent),0.2)] tracking-widest uppercase text-xs"
          >
            <Bot size={18} />
            {isExplaining ? "Analyzing..." : "Explain Rationale"}
          </button>
        </div>
      </GlassCard>

      {error && (
        <div className="bg-danger/10 border border-danger/20 text-danger p-5 rounded-crypto flex items-center gap-3 animate-in fade-in slide-in-from-top-2 font-mono text-sm shadow-[0_0_15px_rgba(239,68,68,0.15)]">
          <AlertCircle size={20} />
          {error}
        </div>
      )}

      {isExplaining && (
        <GlassCard variant="auto" asymmetric="lg" className="p-8">
            <div className="flex items-center gap-3 mb-6">
                <div className="w-5 h-5 rounded-full border-2 border-accent/20 border-t-accent animate-spin" />
                <span className="text-xs font-mono tracking-widest uppercase text-accent animate-pulse">Generating neural interpretation...</span>
            </div>
            <div className="space-y-4">
              <Skeleton className="h-6 w-1/3 rounded-crypto-sm bg-white/5" />
              <Skeleton className="h-4 w-full rounded-sm bg-white/5" />
              <Skeleton className="h-4 w-full rounded-sm bg-white/5" />
              <Skeleton className="h-4 w-5/6 rounded-sm bg-white/5" />
            </div>
        </GlassCard>
      )}

      {explanation && !isExplaining && (
        <GlassCard variant="auto" asymmetric="xl" className="p-0 border-accent/30 shadow-[0_0_30px_rgba(var(--accent),0.1)] overflow-hidden animate-in fade-in slide-in-from-bottom-4">
          <div className="border-b border-white/10 bg-surface/30 p-6 sm:p-8">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <h2 className="flex items-center gap-3 text-2xl font-black text-text font-sans tracking-tight">
                <MessageSquare className="text-accent" size={24} />
                Analysis for {explanation.symbol}
              </h2>
              <div className={`px-4 py-1.5 rounded-crypto-sm text-xs font-bold uppercase tracking-widest border shadow-lg ${explanation.direction.toLowerCase().includes('up') ? 'bg-success/10 text-success border-success/30 shadow-success/20' : explanation.direction.toLowerCase().includes('down') ? 'bg-danger/10 text-danger border-danger/30 shadow-danger/20' : 'bg-text-muted/10 text-text-muted border-white/10'}`}>
                {explanation.direction.replace('_', ' ')}
              </div>
            </div>
          </div>
          
          <div className="p-6 sm:p-8">
            <div className="prose prose-invert max-w-none">
              {explanation.explanation.split('\n').map((paragraph, i) => (
                <p key={i} className="text-text/90 leading-relaxed mb-6 last:mb-0 text-sm sm:text-base font-light tracking-wide">
                  {paragraph}
                </p>
              ))}
            </div>
            
            {explanation.news_sources && explanation.news_sources.length > 0 && (
              <div className="mt-8 pt-6 border-t border-white/10">
                <div className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-bold mb-4">Market Context Sources</div>
                <div className="flex flex-wrap gap-2.5">
                  {explanation.news_sources.map((source, idx) => (
                    <span key={idx} className="text-xs text-text-muted bg-surface/50 border border-white/5 px-3 py-1.5 rounded-crypto-sm hover:text-text hover:bg-white/5 transition-colors cursor-default">
                      {source}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </GlassCard>
      )}
    </div>
  );
}
