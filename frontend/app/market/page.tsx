"use client";
import { useEffect, useState, useRef } from "react";
import useSWR from "swr";
import Link from "next/link";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { fetcher, Asset, RiskData } from "@/lib/api";
import { PredictionNode } from "@/components/PredictionNode";
import { ArrowUpRight, ArrowDownRight, RefreshCcw, TrendingUp, TrendingDown, Minus, Activity, Network } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { DIRECTION_TOKENS, Direction } from "@/lib/design-tokens";
import { useCurrency } from "@/components/CurrencyContext";
import { useWebSocket } from "@/lib/useWebSocket";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function MarketPage() {
  const { data: initialAssets, error, isLoading, mutate } = useSWR<any[]>("/api/v1/screener", fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 30000,
  });
  
  const { data: riskData } = useSWR<RiskData>("/api/v1/risk", fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 30000,
  });

  const [assets, setAssets] = useState<Asset[]>([]);
  const [mounted, setMounted] = useState(false);
  const [hoveredAsset, setHoveredAsset] = useState<Asset | null>(null);
  const [hoveredAssetPos, setHoveredAssetPos] = useState<{ top: number; left: number } | null>(null);
  const hoverTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const { formatPrice } = useCurrency();
  const router = useRouter();

  useEffect(() => {
    setMounted(true);
    return () => {
      if (hoverTimeoutRef.current) {
        clearTimeout(hoverTimeoutRef.current);
      }
    };
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

  const { status: wsStatus } = useWebSocket("api/v1/stream/market", {
    shouldConnect: !!(initialAssets && initialAssets.length > 0),
    onMessage: (msg) => {
      if (msg.type === "MARKET_UPDATE") {
        Object.assign(updatesRef.current, msg.data);
      }
    },
  });

  useEffect(() => {
    if (!initialAssets || initialAssets.length === 0) return;

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
      clearInterval(interval);
    };
  }, [initialAssets]);

  if (!mounted) {
    return null;
  }

  // Prioritize riskData global confidence as the Single Source of Truth
  const avgConfidence = riskData && riskData.global_confidence !== undefined
    ? riskData.global_confidence.toFixed(1) 
    : (() => {
        if (!assets || assets.length === 0) return "0.0";
        const validConfs = assets
          .map(a => a.confidence)
          .filter((c): c is number => c !== undefined && c !== null && c > 0);
        if (validConfs.length === 0) return "0.0";
        return (validConfs.reduce((sum, c) => sum + c, 0) / validConfs.length).toFixed(1);
      })();

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

  const handleHoverChange = (asset: Asset | null, pos: { top: number; left: number } | null) => {
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
    }
    if (asset) {
      setHoveredAsset(asset);
      setHoveredAssetPos(pos);
    } else {
      hoverTimeoutRef.current = setTimeout(() => {
        setHoveredAsset(null);
        setHoveredAssetPos(null);
      }, 100);
    }
  };

  const handlePortalEnter = () => {
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
    }
  };

  const handlePortalLeave = () => {
    handleHoverChange(null, null);
  };

  // Portal values for rendering
  const direction = hoveredAsset ? ((hoveredAsset.predicted_direction || (hoveredAsset as any).direction)?.toLowerCase() ?? "neutral") : "neutral";
  const isUp = direction === "up" || direction === "strong_up";
  const isDown = direction === "down" || direction === "strong_down";
  const safeDirection = (direction in DIRECTION_TOKENS ? direction : "neutral") as Direction;
  const t = DIRECTION_TOKENS[safeDirection];
  const confidence = hoveredAsset?.confidence;

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
                <span className={`flex items-center gap-2 px-4 py-2 border rounded-sm text-xs font-mono font-bold glass transition-all duration-300 ${
                  wsStatus === "connected" 
                    ? "bg-success/10 text-success border-success/30 shadow-[0_0_15px_rgba(34,197,94,0.2)]" 
                    : wsStatus === "connecting"
                      ? "bg-warning/10 text-warning border-warning/30 animate-pulse"
                      : "bg-danger/10 text-danger border-danger/30"
                }`}>
                  <span className={`w-2 h-2 rounded-full ${wsStatus === "connected" ? "bg-success" : wsStatus === "connecting" ? "bg-warning" : "bg-danger"}`} />
                  {wsStatus === "connected" ? "STREAM ON" : wsStatus === "connecting" ? "SYNCING" : "OFFLINE"}
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
      <div className="relative w-full">
        {isLoading || !assets || assets.length === 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-x-4 gap-y-3 auto-rows-[76px] w-full content-start items-start justify-start">
            {Array.from({ length: 25 }).map((_, i) => (
              <GlassCard tier="flat" shape="none" key={i} className="h-[76px] animate-pulse bg-[rgba(var(--text),0.03)] border border-text/5 rounded-lg" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-x-4 gap-y-3 auto-rows-[76px] w-full content-start items-start justify-start">
            {sortedAssets.map((asset) => (
              <Link key={asset.symbol} href={`/coin/${asset.symbol}`} className="block w-full">
                <PredictionNode asset={asset} onHoverChange={handleHoverChange} />
              </Link>
            ))}
          </div>
        )}
      </div>
      {hoveredAsset && (
        <div 
          className="fixed inset-0 z-30 bg-black/15 transition-all duration-300 pointer-events-none" 
          style={{
            backdropFilter: "blur(8px)",
            WebkitBackdropFilter: "blur(8px)"
          }}
        />
      )}

      {/* Centralized Portaled Hover Panel Popup */}
      {hoveredAsset && hoveredAssetPos && typeof document !== "undefined" && createPortal(
        <div
          className="fixed z-[999] pointer-events-auto animate-in fade-in zoom-in-95 duration-200"
          style={{ top: hoveredAssetPos.top, left: hoveredAssetPos.left, width: 320 }}
          onMouseEnter={handlePortalEnter}
          onMouseLeave={handlePortalLeave}
          onClick={() => router.push(`/coin/${hoveredAsset.symbol}`)}
        >
          <GlassCard
            tier={3}
            shape="none"
            className="rounded-2xl border border-text/15 shadow-2xl p-5 relative overflow-hidden bg-surface text-text cursor-pointer"
          >
            {/* Glow behind popup */}
            <div className={`absolute inset-0 opacity-[0.06] blur-xl pointer-events-none ${t.textClass.replace('text-', 'bg-')}`} />

            <div className="relative z-10 space-y-4 text-left">
              {/* Header */}
              <div className="flex justify-between items-start gap-3 border-b border-text/10 pb-2">
                <div className="min-w-0 flex-1">
                  <h3 className="text-text font-black text-base font-sans tracking-tight uppercase truncate">{hoveredAsset.name}</h3>
                  <span className="text-[10px] text-text-muted uppercase tracking-widest font-mono mt-0.5 block truncate">{hoveredAsset.sector || "Uncategorized"}</span>
                </div>
                <div className={`shrink-0 shape-tag text-[10px] font-black px-3 py-1 uppercase tracking-widest border ${t.textClass} border-current/25 bg-black/20 font-mono`}>
                  {t.label}
                </div>
              </div>

              {/* Swarm Confidence Bar */}
              {confidence != null && (
                <div className="space-y-1">
                  <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest font-mono text-text-muted">
                    <span>Swarm Conviction</span>
                    <span className={t.textClass}>{confidence.toFixed(1)}%</span>
                  </div>
                  <div className="w-full h-1.5 bg-black/30 rounded-full overflow-hidden border border-text/10 p-[1px]">
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
                <div className="bg-black/20 rounded-lg p-2.5 border border-text/10">
                  <span className="text-[9px] text-text-muted uppercase tracking-widest font-mono block mb-1">24h Vol</span>
                  <span className="text-sm font-mono font-bold text-text">
                    {hoveredAsset.volume_24h != null ? `$${((hoveredAsset.volume_24h) / 1000000).toFixed(1)}M` : "—"}
                  </span>
                </div>
                <div className="bg-black/20 rounded-lg p-2.5 border border-text/10">
                  <span className="text-[9px] text-text-muted uppercase tracking-widest font-mono block mb-1">RSI (14D)</span>
                  <span className={`text-sm font-mono font-bold ${hoveredAsset.rsi_14 != null && hoveredAsset.rsi_14 > 70 ? 'text-danger' : hoveredAsset.rsi_14 != null && hoveredAsset.rsi_14 < 30 ? 'text-success' : 'text-text'}`}>
                    {hoveredAsset.rsi_14 != null ? hoveredAsset.rsi_14.toFixed(1) : "—"}
                  </span>
                </div>
                <div className="bg-black/20 rounded-lg p-2.5 border border-text/10 col-span-2">
                  <span className="text-[9px] text-text-muted uppercase tracking-widest font-mono block mb-1">MACD Signal</span>
                  <span className={`text-sm font-mono font-bold ${hoveredAsset.macd != null && hoveredAsset.macd > 0 ? 'text-success' : 'text-danger'}`}>
                    {hoveredAsset.macd != null ? hoveredAsset.macd.toFixed(4) : "—"}
                  </span>
                </div>
              </div>

              {/* CTA Footer */}
              <div className="pt-2 border-t border-text/10 text-center flex items-center justify-center gap-1.5 text-[10px] text-text tracking-[0.2em] font-mono uppercase font-black">
                <span>Explore Neural Profile</span>
                <ArrowUpRight size={11} className="tracking-normal animate-pulse" />
              </div>
            </div>
          </GlassCard>
        </div>,
        document.body
      )}
    </div>
  );
}

