"use client";

import useSWR from "swr";
import Link from "next/link";
import { fetcher, Asset, RiskData } from "@/lib/api";
import { PredictionCard } from "@/components/PredictionCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { RefreshCcw, TrendingUp, TrendingDown, Minus, BarChart2, Activity, Clock } from "lucide-react";

export default function MarketPage() {
  const { data: assets, error, isLoading, mutate } = useSWR<Asset[]>("/api/assets", fetcher, {
    refreshInterval: 60000,
    revalidateOnFocus: false,
    dedupingInterval: 30000,
  });
  const { data: riskData } = useSWR<RiskData>("/api/risk", fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 30000,
  });

  const avgConfidence = assets && assets.length > 0
    ? (assets.reduce((sum, a) => sum + (a.confidence ?? 0), 0) / assets.length * 100).toFixed(1)
    : "0.0";

  const regimeColor = riskData?.market_regime === "bull"
    ? "bg-green-900/50 text-green-400 border-green-700"
    : riskData?.market_regime === "bear"
      ? "bg-red-900/50 text-red-400 border-red-700"
      : "bg-amber-900/50 text-amber-400 border-amber-700";

  const RegimeIcon = riskData?.market_regime === "bull" ? TrendingUp
    : riskData?.market_regime === "bear" ? TrendingDown : Minus;

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full space-y-4">
        <div className="text-danger bg-danger/10 p-4 rounded-md border border-danger/20">
          Failed to load market data
        </div>
        <button
          onClick={() => mutate()}
          className="flex items-center gap-2 px-4 py-2 bg-surface hover:bg-border transition-colors rounded-md text-text border border-border"
        >
          <RefreshCcw size={16} />
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-text">Market Overview</h1>
        <p className="text-textMuted mt-1">Live AI-driven forecasts for top 50 crypto assets</p>
      </div>

      {/* Stats Bar */}
      {assets && (
        <div className="flex flex-wrap gap-3">
          <span className="flex items-center gap-1.5 px-3 py-1.5 bg-surface border border-border rounded-full text-xs font-mono text-text">
            <BarChart2 size={12} className="text-accent" />
            {assets.length} Assets Tracked
          </span>
          <span className="flex items-center gap-1.5 px-3 py-1.5 bg-surface border border-border rounded-full text-xs font-mono text-text">
            <Activity size={12} className="text-accent" />
            Avg Confidence: {avgConfidence}%
          </span>
          {riskData && (
            <span className={`flex items-center gap-1.5 px-3 py-1.5 border rounded-full text-xs font-mono font-bold ${regimeColor}`}>
              <RegimeIcon size={12} />
              {riskData.market_regime.toUpperCase()}
            </span>
          )}
          <span className="flex items-center gap-1.5 px-3 py-1.5 bg-surface border border-border rounded-full text-xs font-mono text-textMuted">
            <Clock size={12} />
            Updated: just now
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {isLoading || !assets
          ? Array.from({ length: 12 }).map((_, i) => (
              <Skeleton key={i} className="h-40 w-full" />
            ))
          : assets.map((asset) => (
              <Link href={`/coin/${asset.symbol}`} key={asset.id} className="block cursor-pointer hover:ring-2 ring-indigo-500 rounded-xl transition-all">
                <PredictionCard asset={asset} />
              </Link>
            ))}
      </div>
    </div>
  );
}
