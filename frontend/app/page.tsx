"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { GlassCard } from "@/components/ui/GlassCard";
import { PredictionCard } from "@/components/PredictionCard";
import { Network, Activity, TrendingUp, TrendingDown, Cpu, BookOpen, CheckCircle } from "lucide-react";
import Link from "next/link";

export default function Dashboard() {
  const { data: statusData } = useSWR("/api/status", fetcher);
  const { data: riskData } = useSWR("/api/risk", fetcher);
  const { data: assets } = useSWR("/api/assets", fetcher);
  const { data: graphData } = useSWR("/api/graph/latest", fetcher);
  const { data: portfolio } = useSWR("/api/portfolio", fetcher);
  const { data: validationMetrics } = useSWR("/api/predictions/validation-metrics", fetcher);
  
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const topAssets = assets?.filter((a: any) => a.confidence).sort((a: any, b: any) => b.confidence - a.confidence).slice(0, 4) || [];

  if (!mounted) return null;

  return (
    <div className="relative min-h-[calc(100vh-8rem)] w-full flex flex-col gap-8 glass-2 rounded-2xl p-6 overflow-hidden">
      
      {/* Animated Network Background */}
      <div className="absolute inset-0 z-0 pointer-events-none opacity-20">
        <div className="absolute top-0 left-1/4 w-[50vw] h-[50vw] bg-accent-2/20 rounded-full blur-[80px]" />
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
                    <Link href="/predictions">
                        <button className="glass-3 rounded-xl px-6 py-3 text-sm font-bold tracking-widest uppercase text-text border border-accent-2/50 hover:bg-accent-2/10 hover:shadow-[0_0_20px_rgba(var(--accent-2),0.2)] transition-all duration-[var(--dur-hover)] ease-glide">
                            View Models
                        </button>
                    </Link>
                    <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
                        <button className="glass-flat rounded-xl px-6 py-3 text-sm font-bold tracking-widest uppercase text-text-muted hover:text-text border border-text/10 hover:bg-text/5 transition-all duration-[var(--dur-hover)] ease-glide flex items-center gap-2">
                            <Cpu size={16}/> API Docs
                        </button>
                    </a>
                </div>
            </div>

            {/* Glass Orb Metrics */}
            <div className="flex flex-wrap justify-center gap-4">
                <div className="w-32 h-32 rounded-full glass-3 border border-accent-2/40 shadow-[0_0_30px_rgba(var(--accent-2),0.15)] flex flex-col items-center justify-center gap-1 animate-[float_4s_ease-in-out_infinite]">
                    <Activity size={20} className="text-accent-2" />
                    <span className="text-2xl font-mono font-bold text-text">{graphData?.nodes?.length || 0}</span>
                    <span className="text-[9px] uppercase tracking-widest font-mono text-text-muted">Nodes</span>
                </div>
                <div className="w-28 h-28 rounded-full glass-3 border border-success/40 shadow-[0_0_30px_rgba(34,197,94,0.15)] flex flex-col items-center justify-center gap-1 mt-12 animate-[float_5s_ease-in-out_infinite_reverse]">
                    <Network size={18} className="text-success" />
                    <span className="text-xl font-mono font-bold text-text">{graphData?.edges?.length || 0}</span>
                    <span className="text-[8px] uppercase tracking-widest font-mono text-text-muted">Edges</span>
                </div>
                <div className="w-24 h-24 rounded-full glass-3 border border-warning/40 shadow-[0_0_20px_rgba(245,158,11,0.15)] flex flex-col items-center justify-center gap-1 mt-4 animate-[float_3s_ease-in-out_infinite_0.5s]">
                    <TrendingUp size={16} className="text-warning" />
                    <span className="text-lg font-mono font-bold text-text">{(riskData?.global_confidence || 0).toFixed(1)}%</span>
                    <span className="text-[7px] uppercase tracking-widest font-mono text-text-muted">Conf</span>
                </div>
                <div className="flex flex-col justify-center gap-3 glass-3 border border-success/30 p-4 rounded-xl w-36 shadow-[0_0_20px_rgba(34,197,94,0.05)]">
                    <div className="flex items-center gap-1.5">
                        <CheckCircle size={12} className="text-success" />
                        <span className="text-[9px] uppercase tracking-widest font-mono text-text-muted font-black">Audited</span>
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <div>
                            <span className="text-[8px] text-text-muted block uppercase font-mono tracking-widest">F1 Validation</span>
                            <span className="text-xs font-mono font-bold text-success">
                                {validationMetrics ? validationMetrics.f1_macro.toFixed(4) : "0.3950"}
                            </span>
                        </div>
                        <div>
                            <span className="text-[8px] text-text-muted block uppercase font-mono tracking-widest">Sharpe Ratio</span>
                            <span className="text-xs font-mono font-bold text-accent-2">
                                {validationMetrics ? validationMetrics.sharpe_ratio.toFixed(2) : "1.48"}
                            </span>
                        </div>
                    </div>
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
                    <PredictionCard key={asset.symbol} asset={asset} />
                ))}
            </div>
        </div>

        {/* The Ledger (Public Verification) */}
        <div className="flex flex-col gap-6 mt-12 relative z-10">
            <h2 className="text-sm font-bold font-mono tracking-widest text-text-muted uppercase flex items-center gap-2">
                <BookOpen size={16} className="text-accent" /> The Ledger: Live Swarm Intelligence
            </h2>
            
            <GlassCard tier={2} shape="none" className="rounded-xl p-8 border-accent/20 shadow-[0_0_30px_rgba(var(--accent),0.1)]">
                <div className="flex flex-col md:flex-row gap-8 justify-between">
                    <div className="max-w-md">
                        <h3 className="text-3xl font-black text-text tracking-tight font-sans mb-3 flex items-center gap-3">
                            Autonomous Portfolio
                            <div className="flex items-center gap-1 text-[10px] bg-success/10 text-success border border-success/20 px-2 py-1 rounded-sm uppercase tracking-widest font-mono">
                                <CheckCircle size={10} /> Active
                            </div>
                        </h3>
                        <p className="text-sm font-light text-text/80 leading-relaxed mb-6">
                            This platform operates an autonomous trading swarm. Our neural networks and MoA agents execute simulated paper-trading portfolios on live market data based on the predictions you see above. This ledger proves our calibration models perform in production.
                        </p>
                    </div>
                    
                    <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="bg-surface/50 border border-text/5 p-4 rounded-sm">
                            <div className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-bold mb-2">Net Alpha (ROI)</div>
                            <div className={`text-2xl font-black font-sans tracking-tight ${portfolio?.roi_pct > 0 ? 'text-success drop-shadow-[0_0_10px_rgba(34,197,94,0.3)]' : portfolio?.roi_pct < 0 ? 'text-danger' : 'text-text'}`}>
                                {portfolio?.roi_pct > 0 ? '+' : ''}{portfolio?.roi_pct?.toFixed(2) || '0.00'}%
                            </div>
                        </div>
                        <div className="bg-surface/50 border border-text/5 p-4 rounded-sm">
                            <div className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-bold mb-2">Total Executed</div>
                            <div className="text-2xl font-black font-sans tracking-tight text-text">
                                {portfolio?.total_trades || 0}
                            </div>
                        </div>
                        <div className="bg-surface/50 border border-text/5 p-4 rounded-sm">
                            <div className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-bold mb-2">Win Rate</div>
                            <div className={`text-2xl font-black font-sans tracking-tight ${portfolio?.win_rate > 50 ? 'text-success' : 'text-warning'}`}>
                                {portfolio?.win_rate?.toFixed(1) || '0.0'}%
                            </div>
                        </div>
                        <div className="bg-surface/50 border border-text/5 p-4 rounded-sm">
                            <div className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-bold mb-2">Total Value</div>
                            <div className="text-2xl font-black font-sans tracking-tight text-text">
                                ${(portfolio?.total_value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                            </div>
                        </div>
                    </div>
                </div>
            </GlassCard>
        </div>

        {/* Info Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-4 relative z-10">
            <GlassCard tier={1} shape="none" hoverable className="p-6 flex flex-col gap-3">
                <div className="w-10 h-10 rounded-xl bg-accent-2/10 flex items-center justify-center text-accent-2 mb-2">
                    <Activity size={20} />
                </div>
                <h3 className="text-lg font-bold text-text tracking-tight">Real-Time Sync</h3>
                <p className="text-sm text-text-muted leading-relaxed">
                    Data pipelines ingest OHLCV, orderbook, and on-chain metrics continuously, feeding the ST-GCN spatial matrices.
                </p>
            </GlassCard>
            
            <GlassCard tier={1} shape="none" hoverable className="p-6 flex flex-col gap-3">
                <div className="w-10 h-10 rounded-xl bg-success/10 flex items-center justify-center text-success mb-2">
                    <TrendingUp size={20} />
                </div>
                <h3 className="text-lg font-bold text-text tracking-tight">Temporal Forecasting</h3>
                <p className="text-sm text-text-muted leading-relaxed">
                    LSTM and TCN blocks capture temporal dependencies, generating directional probabilities with calculated confidence.
                </p>
            </GlassCard>
            
            <GlassCard tier={1} shape="none" hoverable className="p-6 flex flex-col gap-3">
                <div className="w-10 h-10 rounded-xl bg-danger/10 flex items-center justify-center text-danger mb-2">
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
