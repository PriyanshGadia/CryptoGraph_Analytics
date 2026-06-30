"use client";

import { useEffect, useState, useRef } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher, Asset, RiskData } from "@/lib/api";
import { PredictionNode } from "@/components/PredictionNode";
import { RefreshCcw, TrendingUp, TrendingDown, Minus, BarChart2, Activity, Network } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
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

  useEffect(() => {
      if (initialAssets) {
          setAssets(initialAssets.map(a => ({
              ...a,
              base_price: a.current_price / (1 + (a.price_change_24h_pct || 0) / 100)
          })));
      }
  }, [initialAssets]);

  const updatesRef = useRef<Record<string, any>>({});

  useEffect(() => {
      if (!initialAssets || initialAssets.length === 0) return;

      const ws = new WebSocket(`${WS_BASE}/api/stream/market`);
      ws.onmessage = (event) => {
          try {
              const msg = JSON.parse(event.data);
              if (msg.type === "MARKET_UPDATE") {
                  Object.assign(updatesRef.current, msg.data);
              }
          } catch (e) {
              console.error("WS Parse Error", e);
          }
      };

      const interval = setInterval(() => {
          if (Object.keys(updatesRef.current).length === 0) return;
          
          setAssets(prev => prev.map(asset => {
              const liveData = updatesRef.current[asset.symbol];
              if (liveData) {
                  const prevClose = (asset as any).base_price || (asset.current_price / (1 + (asset.price_change_24h_pct || 0) / 100));
                  const newPctChange = prevClose > 0 ? ((liveData.close - prevClose) / prevClose) * 100 : 0;
                  
                  return {
                      ...asset,
                      current_price: liveData.close,
                      price_change_24h_pct: newPctChange,
                  };
              }
              return asset;
          }));
          
          updatesRef.current = {};
      }, 1000);

      return () => {
          ws.close();
          clearInterval(interval);
      };
  }, [initialAssets]);

  const avgConfidence = assets && assets.length > 0
    ? (assets.reduce((sum, a) => sum + (a.confidence ?? 0), 0) / assets.length).toFixed(1)
    : "0.0";

  const regimeColor = riskData?.market_regime === "bull"
    ? "bg-success/10 text-success border-success/30 shadow-[0_0_15px_rgba(34,197,94,0.2)]"
    : riskData?.market_regime === "bear"
      ? "bg-danger/10 text-danger border-danger/30 shadow-[0_0_15px_rgba(239,68,68,0.2)]"
      : "bg-text-muted/10 text-text-muted border-text/10";

  const RegimeIcon = riskData?.market_regime === "bull" ? TrendingUp
    : riskData?.market_regime === "bear" ? TrendingDown : Minus;

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full space-y-4">
        <div className="text-danger bg-danger/10 p-4 rounded-sm border border-danger/20 backdrop-blur-md">
          Failed to load market data. The prediction engine may be offline.
        </div>
        <button
          onClick={() => mutate()}
          className="flex items-center gap-2 px-6 py-3 glass hover:bg-text/10 transition-colors rounded-sm text-text border border-text/10"
        >
          <RefreshCcw size={16} />
          Reconnect
        </button>
      </div>
    );
  }

  const sortedAssets = [...assets].sort((a, b) => {
    return (b.confidence ?? 0) - (a.confidence ?? 0);
  });

  return (
    <div className="relative min-h-[calc(100vh-8rem)] flex flex-col items-center justify-start pt-10 p-6 max-w-6xl mx-auto w-full glass-2 rounded-2xl">
      
      {/* Absolute Ambient Background Lights */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-accent/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-success/10 rounded-full blur-[120px] pointer-events-none" />

      {/* Hero Header */}
      <div className="w-full mb-12 relative z-10 flex flex-col md:flex-row items-center justify-between gap-6">
        <div>
            <h1 className="text-4xl md:text-5xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted tracking-tight mb-2 drop-shadow-sm font-sans">
                Neural Market
            </h1>
            <p className="text-text-muted font-light tracking-wide">
                Live topological asset network. Node connections indicate correlation strength.
            </p>
        </div>
        
        {/* Stats Bar */}
        {assets && assets.length > 0 && (
            <div className="flex flex-wrap items-center gap-3">
                 <span className="flex items-center gap-2 px-4 py-2 glass border-text/10 rounded-sm text-xs font-mono text-text shadow-lg">
                    <Network size={14} className="text-accent" />
                    {assets.length} Nodes
                </span>
                <span className="flex items-center gap-2 px-4 py-2 glass border-text/10 rounded-sm text-xs font-mono text-text shadow-lg">
                    <Activity size={14} className="text-accent" />
                    Conf: {avgConfidence}%
                </span>
                {riskData && (
                    <span className={`flex items-center gap-2 px-4 py-2 border rounded-sm text-xs font-mono font-bold glass ${regimeColor}`}>
                        <RegimeIcon size={14} />
                        {riskData.market_regime.toUpperCase()}
                    </span>
                )}
            </div>
        )}
      </div>

      {/* Compact Hover-detail Grid view */}
      <div className="relative z-10 w-full">
        {isLoading || !assets || assets.length === 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 w-full">
            {Array.from({ length: 25 }).map((_, i) => (
              <GlassCard tier="flat" shape="none" key={i} className="rounded-sm h-[64px] animate-pulse bg-[rgba(var(--text),0.03)] border border-text/5" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 w-full">
            {sortedAssets.map((asset) => (
              <Link key={asset.symbol} href={`/coin/${asset.symbol}`} className="block w-full">
                <PredictionNode asset={asset} />
              </Link>
            ))}
          </div>
        )}
      </div>

    </div>
  );
}

