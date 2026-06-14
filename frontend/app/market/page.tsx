"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher, Asset, RiskData } from "@/lib/api";
import { PredictionNode } from "@/components/PredictionNode";
import { RefreshCcw, TrendingUp, TrendingDown, Minus, BarChart2, Activity, ShieldAlert } from "lucide-react";

const BASE = "http://localhost:8000";
const WS_BASE = BASE.replace(/^http/, "ws");

export default function MarketPage() {
  const { data: initialAssets, error, isLoading, mutate } = useSWR<any[]>("/api/screener", fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 30000,
  });
  
  const { data: riskData } = useSWR<RiskData>("/api/risk", fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 30000,
  });

  const [assets, setAssets] = useState<Asset[]>([]);

  // Initialize assets from SWR
  useEffect(() => {
      if (initialAssets) setAssets(initialAssets);
  }, [initialAssets]);

  // Connect to unified /stream/market WebSocket
  useEffect(() => {
      if (!initialAssets || initialAssets.length === 0) return;

      const ws = new WebSocket(`${WS_BASE}/api/stream/market`);
      ws.onmessage = (event) => {
          try {
              const msg = JSON.parse(event.data);
              if (msg.type === "MARKET_UPDATE") {
                  const updates = msg.data;

                  setAssets(prev => prev.map(asset => {
                      if (updates[asset.symbol]) {
                          const liveData = updates[asset.symbol];
                          return {
                              ...asset,
                              current_price: liveData.close,
                          };
                      }
                      return asset;
                  }));
              }
          } catch (e) {
              console.error("WS Parse Error", e);
          }
      };

      return () => ws.close();
  }, [initialAssets]);

  const avgConfidence = assets && assets.length > 0
    ? (assets.reduce((sum, a) => sum + (a.confidence ?? 0), 0) / assets.length).toFixed(1)
    : "0.0";

  const regimeColor = riskData?.market_regime === "bull"
    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-[0_0_15px_rgba(16,185,129,0.2)]"
    : riskData?.market_regime === "bear"
      ? "bg-rose-500/10 text-rose-400 border-rose-500/20 shadow-[0_0_15px_rgba(244,63,94,0.2)]"
      : "bg-slate-500/10 text-slate-400 border-slate-500/20";

  const RegimeIcon = riskData?.market_regime === "bull" ? TrendingUp
    : riskData?.market_regime === "bear" ? TrendingDown : Minus;

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full space-y-4">
        <div className="text-rose-400 bg-rose-500/10 p-4 rounded-xl border border-rose-500/20 backdrop-blur-md">
          Failed to load market data. The prediction engine may be offline.
        </div>
        <button
          onClick={() => mutate()}
          className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 transition-colors rounded-lg text-white border border-white/10"
        >
          <RefreshCcw size={16} />
          Reconnect
        </button>
      </div>
    );
  }

  // Group assets for visual clustering (e.g. strong buys together)
  const sortedAssets = [...assets].sort((a, b) => {
    // Sort primarily by confidence, descending
    return (b.confidence ?? 0) - (a.confidence ?? 0);
  });

  return (
    <div className="relative min-h-[calc(100vh-8rem)] flex flex-col items-center justify-center py-10 max-w-[1600px] mx-auto">
      
      {/* Absolute Ambient Background Lights */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-[120px] pointer-events-none" />

      {/* Hero Header */}
      <div className="text-center mb-16 relative z-10">
        <h1 className="text-4xl md:text-5xl font-black text-transparent bg-clip-text bg-gradient-to-r from-white via-indigo-200 to-slate-400 tracking-tight mb-4 drop-shadow-sm">
            Swarm Intelligence Map
        </h1>
        <p className="text-slate-400 font-light tracking-wide max-w-2xl mx-auto">
            Live neural network forecasts mapped spatially. Hover over any node to reveal the deep-learning technical matrix and directional confidence.
        </p>
        
        {/* Stats Bar */}
        {assets && assets.length > 0 && (
            <div className="flex flex-wrap items-center justify-center gap-4 mt-8">
                <span className="flex items-center gap-2 px-4 py-2 bg-white/5 border border-white/10 rounded-full text-xs font-mono text-slate-300 backdrop-blur-2xl shadow-xl">
                    <BarChart2 size={14} className="text-indigo-400" />
                    {assets.length} Nodes Active
                </span>
                <span className="flex items-center gap-2 px-4 py-2 bg-white/5 border border-white/10 rounded-full text-xs font-mono text-slate-300 backdrop-blur-2xl shadow-xl">
                    <Activity size={14} className="text-indigo-400" />
                    Global Confidence: {avgConfidence}%
                </span>
                {riskData && (
                    <span className={`flex items-center gap-2 px-4 py-2 border rounded-full text-xs font-mono font-bold backdrop-blur-2xl ${regimeColor}`}>
                        <RegimeIcon size={14} />
                        REGIME: {riskData.market_regime.toUpperCase()}
                    </span>
                )}
            </div>
        )}
      </div>

      {/* Fluid Node Map */}
      <div className="relative z-10 w-full max-w-5xl">
        {isLoading || !assets || assets.length === 0 ? (
          <div className="flex flex-wrap justify-center gap-4 animate-pulse opacity-50">
            {Array.from({ length: 30 }).map((_, i) => (
              <div key={i} className="w-32 h-10 rounded-full bg-white/10 border border-white/5" />
            ))}
          </div>
        ) : (
          <div className="flex flex-wrap justify-center gap-x-4 gap-y-6">
            {sortedAssets.map((asset) => (
              <Link href={`/coin/${asset.symbol}`} key={asset.id} className="block transition-transform">
                <PredictionNode asset={asset} />
              </Link>
            ))}
          </div>
        )}
      </div>

    </div>
  );
}
