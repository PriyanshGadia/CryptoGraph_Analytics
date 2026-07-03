"use client";
import { useEffect, useState, useRef } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher, Asset, RiskData } from "@/lib/api";
import { PredictionNode } from "@/components/PredictionNode";
import { ArrowUpRight, ArrowDownRight, RefreshCcw, TrendingUp, TrendingDown, Minus, BarChart2, Activity, Network } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { BlockchainLoader } from "@/components/BlockchainLoader";
import { DIRECTION_TOKENS, Direction } from "@/lib/design-tokens";
import { useCurrency } from "@/components/CurrencyContext";

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
  const [mounted, setMounted] = useState(false);
  const [isAnyCardHovered, setIsAnyCardHovered] = useState(false);
  const [hoveredAsset, setHoveredAsset] = useState<Asset | null>(null);
  const { formatPrice } = useCurrency();

  useEffect(() => {
    setMounted(true);
  }, []);

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

  if (!mounted) {
    return null;
  }

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
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-x-3 gap-y-1.5 w-full content-start items-start justify-start">
            {Array.from({ length: 25 }).map((_, i) => (
              <GlassCard tier="flat" shape="none" key={i} className="h-[64px] animate-pulse bg-[rgba(var(--text),0.03)] border border-text/5 rounded-sm" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-x-3 gap-y-1.5 w-full content-start items-start justify-start">
            {sortedAssets.map((asset) => (
              <Link key={asset.symbol} href={`/coin/${asset.symbol}`} className="block w-full">
                <PredictionNode asset={asset} onHoverChange={(hovered) => setHoveredAsset(hovered ? asset : null)} />
              </Link>
            ))}
          </div>
        )}
      </div>

      {hoveredAsset && (() => {
        const direction = (hoveredAsset.predicted_direction || (hoveredAsset as any).direction)?.toLowerCase() ?? "neutral";
        const isUp = direction === "up" || direction === "strong_up";
        const isDown = direction === "down" || direction === "strong_down";
        const confidence = hoveredAsset.confidence;
        const safeDirection = (direction in DIRECTION_TOKENS ? direction : "neutral") as Direction;
        const t = DIRECTION_TOKENS[safeDirection];

        return (
          <>
            {/* Viewport-wide Backdrop Blur */}
            <div className="fixed inset-0 z-30 bg-black/60 backdrop-blur-[12px] -webkit-backdrop-filter: blur(12px) pointer-events-none transition-all duration-300" />
            
            {/* Viewport-centered Floating Detail Popup */}
            <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-80 p-5 pointer-events-none transition-all duration-300">
              <GlassCard 
                tier={3} 
                shape="none" 
                className="rounded-xl border border-white/20 shadow-2xl p-5 relative overflow-hidden bg-[#355E3B]/95 text-white"
                style={{
                  backgroundImage: `url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMjAiIGhlaWdodD0iMTIwIj4KPGZpbHRlciBpZD0ibm9pc2UiPgo8ZmVUdXJidWxlbmNlIHR5cGU9ImZyYWN0YWxOb2lzZSIgYmFzZUZyZXF1ZW5jeT0iMC44NSIgbnVtT2N0YXZlcz0iMyIgc3RpdGNoVGlsZXM9InN0aXRjaCIvPgo8ZmVDb2xvck1hdHJpeCB0eXBlPSJtYXRyaXgiIHZhbHVlcz0iMCAwIDAgMCAwIDAgMCAwIDAgMCAwIDAgMCAwIDAgMCAwIDAgMC4yNCAwIi8+CjwvZmlsdGVyPgo8cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWx0ZXI9InVybCgjbm9pc2UpIi8+Cjwvc3ZnPg==")`
                }}
              >
                {/* Glow behind popup */}
                <div className={`absolute inset-0 opacity-[0.05] blur-xl pointer-events-none ${t.textClass.replace('text-', 'bg-')}`} />
                
                <div className="relative z-10 space-y-4 text-left">
                  {/* Header */}
                  <div className="flex justify-between items-start border-b border-white/10 pb-2">
                    <div className="min-w-0 flex-1 mr-2">
                      <h3 className="text-white font-black text-base font-sans tracking-tight uppercase truncate">{hoveredAsset.name}</h3>
                      <span className="text-[9px] text-white/60 uppercase tracking-widest font-mono mt-0.5 block truncate">{hoveredAsset.sector || "Uncategorized"}</span>
                    </div>
                    <div className={`text-[9px] font-black px-2 py-0.5 rounded-sm uppercase tracking-widest border ${t.textClass} border-current/25 bg-black/30 font-mono shrink-0`}>
                      {t.label}
                    </div>
                  </div>

                  {/* Swarm Confidence Bar */}
                  {confidence != null && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-[9px] font-bold uppercase tracking-widest font-mono text-white/60">
                        <span>Swarm Conviction</span>
                        <span className={t.textClass}>{confidence.toFixed(1)}%</span>
                      </div>
                      <div className="w-full h-2 bg-black/45 rounded-full overflow-hidden border border-white/10 p-[1px]">
                        <div 
                          className={`h-full rounded-full transition-all duration-500 ${
                            isUp ? 'bg-success' : isDown ? 'bg-danger' : 'bg-white/40'
                          }`} 
                          style={{ width: `${confidence}%` }} 
                        />
                      </div>
                    </div>
                  )}

                  {/* Technical Details Grid */}
                  <div className="grid grid-cols-2 gap-2 text-left">
                    <div className="bg-black/30 rounded-sm p-2 border border-white/5">
                      <span className="text-[8px] text-white/50 uppercase tracking-widest font-mono block mb-0.5">24h Vol</span>
                      <span className="text-xs font-mono font-bold text-white">
                        {hoveredAsset.volume_24h != null ? `$${((hoveredAsset.volume_24h) / 1000000).toFixed(1)}M` : "—"}
                      </span>
                    </div>
                    <div className="bg-black/30 rounded-sm p-2 border border-white/5">
                      <span className="text-[8px] text-white/50 uppercase tracking-widest font-mono block mb-0.5">RSI (14D)</span>
                      <span className={`text-xs font-mono font-bold ${hoveredAsset.rsi_14 != null && hoveredAsset.rsi_14 > 70 ? 'text-danger' : hoveredAsset.rsi_14 != null && hoveredAsset.rsi_14 < 30 ? 'text-success' : 'text-white'}`}>
                        {hoveredAsset.rsi_14 != null ? hoveredAsset.rsi_14.toFixed(1) : "—"}
                      </span>
                    </div>
                    <div className="bg-black/30 rounded-sm p-2 border border-white/5 col-span-2">
                      <span className="text-[8px] text-white/50 uppercase tracking-widest font-mono block mb-0.5">MACD Signal</span>
                      <span className={`text-xs font-mono font-bold ${hoveredAsset.macd != null && hoveredAsset.macd > 0 ? 'text-success' : 'text-danger'}`}>
                        {hoveredAsset.macd != null ? hoveredAsset.macd.toFixed(4) : "—"}
                      </span>
                    </div>
                  </div>

                  {/* CTA Footer */}
                  <div className="pt-2 border-t border-white/10 text-center flex items-center justify-center gap-1.5 text-[9px] text-white tracking-[0.2em] font-mono uppercase font-black">
                    <span>Explore Neural Profile</span>
                    <ArrowUpRight size={12} className="tracking-normal animate-pulse" />
                  </div>
                </div>
              </GlassCard>
            </div>
          </>
        );
      })()}

    </div>
  );
}

