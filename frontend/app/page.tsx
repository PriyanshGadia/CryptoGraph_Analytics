"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { GlassCard } from "@/components/ui/GlassCard";
import { PredictionCard } from "@/components/PredictionCard";
import { Network, Activity, TrendingUp, TrendingDown, Cpu } from "lucide-react";

export default function Dashboard() {
  const { data: statusData } = useSWR("/api/status", fetcher);
  const { data: riskData } = useSWR("/api/risk", fetcher);
  const { data: assets } = useSWR("/api/assets", fetcher);
  
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const topAssets = assets?.filter((a: any) => a.confidence).sort((a: any, b: any) => b.confidence - a.confidence).slice(0, 4) || [];

  if (!mounted) return null;

  return (
    <div className="relative min-h-[calc(100vh-8rem)] w-full flex flex-col gap-8">
      
      {/* Animated Network Background */}
      <div className="absolute inset-0 z-0 overflow-hidden rounded-crypto-lg pointer-events-none opacity-20">
        <div className="absolute top-0 left-1/4 w-[50vw] h-[50vw] bg-accent/20 rounded-full blur-[80px]" />
        <div className="absolute bottom-0 right-1/4 w-[40vw] h-[40vw] bg-success/10 rounded-full blur-[80px]" />
        
        {/* CSS grid pattern to simulate network */}
        <div className="absolute inset-0" style={{
            backgroundImage: `radial-gradient(circle at 2px 2px, rgba(255,255,255,0.15) 1px, transparent 0)`,
            backgroundSize: `40px 40px`
        }} />
      </div>

      <div className="relative z-10 flex flex-col gap-12 w-full max-w-7xl mx-auto mt-4">
        
        {/* Hero Section */}
        <div className="flex flex-col md:flex-row gap-8 items-center justify-between">
            <div className="flex flex-col gap-4 max-w-2xl">
                <h1 className="text-5xl font-black font-sans tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-text to-text-muted">
                    Spatio-Temporal<br/>Graph Intelligence
                </h1>
                <p className="text-lg text-text-muted/80 font-light max-w-xl">
                    Live crypto market forecasts synthesized by ST-GCN neural networks. Decrypting market topology in real-time.
                </p>
                <div className="flex items-center gap-4 mt-2">
                    <button className="glass px-6 py-3 rounded-crypto text-sm font-bold tracking-widest uppercase text-text border-accent/50 hover:bg-accent/10 hover:shadow-[0_0_20px_rgba(var(--accent),0.2)] transition-all duration-300">
                        View Models
                    </button>
                    <button className="glass px-6 py-3 rounded-crypto text-sm font-bold tracking-widest uppercase text-text-muted hover:text-text border-white/10 hover:bg-white/5 transition-all duration-300 flex items-center gap-2">
                        <Cpu size={16}/> API Docs
                    </button>
                </div>
            </div>

            {/* Glass Orb Metrics */}
            <div className="flex flex-wrap justify-center gap-4">
                <div className="w-32 h-32 rounded-full glass border border-accent/40 shadow-[0_0_30px_rgba(var(--accent),0.15)] flex flex-col items-center justify-center gap-1 animate-[float_4s_ease-in-out_infinite]">
                    <Activity size={20} className="text-accent" />
                    <span className="text-2xl font-mono font-bold text-text">{statusData?.active_nodes || 0}</span>
                    <span className="text-[9px] uppercase tracking-widest font-mono text-text-muted">Nodes</span>
                </div>
                <div className="w-28 h-28 rounded-full glass border border-success/40 shadow-[0_0_30px_rgba(34,197,94,0.15)] flex flex-col items-center justify-center gap-1 mt-12 animate-[float_5s_ease-in-out_infinite_reverse]">
                    <Network size={18} className="text-success" />
                    <span className="text-xl font-mono font-bold text-text">{statusData?.total_edges || 0}</span>
                    <span className="text-[8px] uppercase tracking-widest font-mono text-text-muted">Edges</span>
                </div>
                <div className="w-24 h-24 rounded-full glass border border-warning/40 shadow-[0_0_20px_rgba(245,158,11,0.15)] flex flex-col items-center justify-center gap-1 mt-4 animate-[float_3s_ease-in-out_infinite_0.5s]">
                    <TrendingUp size={16} className="text-warning" />
                    <span className="text-lg font-mono font-bold text-text">{(riskData?.global_confidence || 0).toFixed(1)}%</span>
                    <span className="text-[7px] uppercase tracking-widest font-mono text-text-muted">Conf</span>
                </div>
            </div>
        </div>

        {/* Market Overview Grid */}
        <div className="flex flex-col gap-6 mt-4">
            <h2 className="text-sm font-bold font-mono tracking-widest text-text-muted uppercase flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-accent animate-pulse" /> Top AI Signals
            </h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {topAssets.map((asset: any) => (
                    <PredictionCard key={asset.id} asset={asset} />
                ))}
            </div>
        </div>

        {/* Info Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-4">
            <GlassCard variant="auto" asymmetric="lg" hoverable className="p-6 flex flex-col gap-3">
                <div className="w-10 h-10 rounded-crypto-sm bg-accent/10 flex items-center justify-center text-accent mb-2">
                    <Activity size={20} />
                </div>
                <h3 className="text-lg font-bold text-text tracking-tight">Real-Time Sync</h3>
                <p className="text-sm text-text-muted leading-relaxed">
                    Data pipelines ingest OHLCV, orderbook, and on-chain metrics continuously, feeding the ST-GCN spatial matrices.
                </p>
            </GlassCard>
            
            <GlassCard variant="auto" asymmetric="lg" hoverable className="p-6 flex flex-col gap-3">
                <div className="w-10 h-10 rounded-crypto-sm bg-success/10 flex items-center justify-center text-success mb-2">
                    <TrendingUp size={20} />
                </div>
                <h3 className="text-lg font-bold text-text tracking-tight">Temporal Forecasting</h3>
                <p className="text-sm text-text-muted leading-relaxed">
                    LSTM and TCN blocks capture temporal dependencies, generating directional probabilities with calculated confidence.
                </p>
            </GlassCard>
            
            <GlassCard variant="auto" asymmetric="lg" hoverable className="p-6 flex flex-col gap-3">
                <div className="w-10 h-10 rounded-crypto-sm bg-danger/10 flex items-center justify-center text-danger mb-2">
                    <TrendingDown size={20} />
                </div>
                <h3 className="text-lg font-bold text-text tracking-tight">Risk Intelligence</h3>
                <p className="text-sm text-text-muted leading-relaxed">
                    Automated regime detection identifies bullish or bearish market conditions to dynamically adjust portfolio risk.
                </p>
            </GlassCard>
        </div>
      </div>
    </div>
  );
}
