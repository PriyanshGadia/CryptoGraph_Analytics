"use client";
import React, { useState, useEffect } from "react";
import { BlockchainLoader } from "@/components/BlockchainLoader";
import { useChartPalette } from "@/lib/useChartPalette";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { ComposedChart, Area, Line, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import Link from "next/link";
import { ChartSkeleton, StatCardSkeleton } from "@/components/PageSkeleton";
import { ScrollToTop } from "@/components/ScrollToTop";
import { GlassCard } from "@/components/ui/GlassCard";
import { Target, Activity, TrendingUp, Cpu } from "lucide-react";
import { DirectionBadge } from "@/components/ui/DirectionBadge";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function CountUp({ end, decimals = 0, suffix = "" }: { end: number, decimals?: number, suffix?: string }) {
  const [count, setCount] = useState(0);
  
  useEffect(() => {
    let startTime: number;
    let animationFrame: number;
    const duration = 1000;
    
    const step = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      const easeProgress = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      setCount(easeProgress * end);
      if (progress < 1) {
        animationFrame = window.requestAnimationFrame(step);
      }
    };
    
    animationFrame = window.requestAnimationFrame(step);
    
    return () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
    };
  }, [end]);
  
  return <>{count.toFixed(decimals)}{suffix}</>;
}

export default function PerformancePage() {
  const [mounted, setMounted] = useState(false);
  const palette = useChartPalette();
  const [days, setDays] = useState(30);
  const [search, setSearch] = useState("");
  const [showAll, setShowAll] = useState(false);
  const { data, isLoading } = useSWR(`${BASE}/api/performance?days=${days}`, fetcher);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return null;
  }
  
  if (isLoading) return (
    <div className="space-y-8 pt-8 max-w-[1600px] mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted tracking-tight">Model Diagnostics</h1>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
      </div>
      <ChartSkeleton height={280} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartSkeleton height={240} />
        <ChartSkeleton height={240} />
      </div>
    </div>
  );
  if (!data) return <div className="p-12 text-center text-danger font-mono border border-danger/20 bg-danger/5 rounded-sm">Tensor stream corrupted. Error loading metrics.</div>;
  
  const overallAcc = data.overall_accuracy * 100;
  const accColor = overallAcc > 55 ? "text-success" : overallAcc > 45 ? "text-warning" : "text-danger";
  const accShadow = overallAcc > 55 ? "drop-shadow-[0_0_10px_rgba(34,197,94,0.3)]" : "";
  
  const stratRet = data.strategy_return_pct;
  const retColor = stratRet > 0 ? "text-success" : "text-danger";
  const retShadow = stratRet > 0 ? "drop-shadow-[0_0_10px_rgba(34,197,94,0.3)]" : "drop-shadow-[0_0_10px_rgba(239,68,68,0.3)]";
  
  const sharpe = data.strategy_sharpe;
  const sharpeColor = sharpe > 1.0 ? "text-success" : sharpe > 0.5 ? "text-warning" : "text-danger";
  
  const assetEntries = Object.entries(data.per_asset_accuracy || {}).map(([sym, stats]: [string, any]) => ({
    symbol: sym,
    ...stats
  })).filter(a => a.symbol.toLowerCase().includes(search.toLowerCase()))
     .sort((a, b) => b.accuracy - a.accuracy);
     
  const visibleAssets = showAll ? assetEntries : assetEntries.slice(0, 20);

  let maxVal = 1;
  data.confusion_matrix.forEach((row: number[]) => {
    row.forEach(val => { if (val > maxVal) maxVal = val; });
  });

  return (
    <div className="space-y-8 pt-8 p-6 glass-2 rounded-2xl overflow-hidden max-w-[1600px] mx-auto">
      
      {/* HEADER */}
      <div className="relative flex flex-col md:flex-row justify-between items-start md:items-end gap-6 mb-4">
        <div className="absolute top-[-50px] left-[-50px] w-64 h-64 bg-accent/5 rounded-full blur-[80px] pointer-events-none" />
        <div className="relative z-10">
          <h1 className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted flex items-center gap-4 tracking-tight">
            <div className="p-3 glass bg-accent/10 rounded-sm shadow-inner shadow-accent/20">
                <Target className="text-accent" size={32} />
            </div>
            Model Diagnostics
          </h1>
          <p className="text-text-muted mt-3 font-light tracking-wide max-w-xl">
            Evaluate predictive performance, calibration metrics, and neural strategy returns.
          </p>
        </div>
        
        <div className="flex bg-surface/50 rounded-sm border border-white/10 p-1 backdrop-blur-md relative z-10">
          {[7, 30, 90].map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-6 py-2 rounded-sm text-[10px] uppercase tracking-widest font-black transition-all ${
                days === d ? "bg-accent text-white shadow-[0_0_15px_rgba(var(--accent),0.5)]" : "text-text-muted hover:text-text hover:bg-white/5"
              }`}
            >
              {d} Days
            </button>
          ))}
        </div>
      </div>
      
      {/* SECTION 1 - Hero Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 relative z-10">
        <GlassCard tier={2} shape="none" className="rounded-xl p-6 group interactive-lift relative overflow-hidden flex flex-col justify-between h-36 border border-white/10 hover:border-white/20 hover:bg-white/[0.02]">
          <div className="absolute top-0 right-0 w-24 h-24 bg-success/5 rounded-full blur-[40px] group-hover:bg-success/10 transition-colors pointer-events-none" />
          <div className="text-[10px] text-text-muted uppercase tracking-widest font-bold flex items-center gap-2">
              <Activity size={12} className="text-success" />
              Global Accuracy
          </div>
          <div className={`text-5xl font-black font-sans tracking-tight ${accColor} ${accShadow}`}>
            <CountUp end={overallAcc} decimals={1} /><span className="text-2xl text-text-muted">%</span>
          </div>
        </GlassCard>
        
        <GlassCard tier={2} shape="none" className="rounded-xl p-6 group interactive-lift relative overflow-hidden flex flex-col justify-between h-36 border border-white/10 hover:border-white/20 hover:bg-white/[0.02]">
          <div className="absolute top-0 right-0 w-24 h-24 bg-accent/5 rounded-full blur-[40px] group-hover:bg-accent/10 transition-colors pointer-events-none" />
          <div className="text-[10px] text-text-muted uppercase tracking-widest font-bold flex items-center gap-2">
              <Cpu size={12} className="text-accent" />
              Tensors Scored
          </div>
          <div className="text-5xl font-black font-sans tracking-tight text-text">
            <CountUp end={data.total_scored} />
          </div>
        </GlassCard>
        
        <GlassCard tier={2} shape="none" className="rounded-xl p-6 group interactive-lift relative overflow-hidden flex flex-col justify-between h-36 border border-white/10 hover:border-white/20 hover:bg-white/[0.02]">
          <div className="absolute top-0 right-0 w-24 h-24 bg-success/5 rounded-full blur-[40px] group-hover:bg-success/10 transition-colors pointer-events-none" />
          <div className="text-[10px] text-text-muted uppercase tracking-widest font-bold flex items-center gap-2">
              <TrendingUp size={12} className={stratRet > 0 ? "text-success" : "text-danger"} />
              Strategy Alpha
          </div>
          <div className={`text-5xl font-black font-sans tracking-tight ${retColor} ${retShadow}`}>
            {stratRet > 0 ? "+" : ""}<CountUp end={Math.abs(stratRet)} decimals={1} /><span className="text-2xl text-text-muted">%</span>
          </div>
        </GlassCard>
        
        <GlassCard tier={2} shape="none" className="rounded-xl p-6 group interactive-lift relative overflow-hidden flex flex-col justify-between h-36 border border-white/10 hover:border-white/20 hover:bg-white/[0.02]">
          <div className="absolute top-0 right-0 w-24 h-24 bg-warning/5 rounded-full blur-[40px] group-hover:bg-warning/10 transition-colors pointer-events-none" />
          <div className="text-[10px] text-text-muted uppercase tracking-widest font-bold flex items-center gap-2">
              <Target size={12} className="text-warning" />
              Sharpe Ratio
          </div>
          <div className={`text-5xl font-black font-sans tracking-tight ${sharpeColor}`}>
            <CountUp end={sharpe} decimals={2} />
          </div>
        </GlassCard>
      </div>
      
      {/* SECTION 2 - Rolling Accuracy */}
      <GlassCard tier={2} shape="none" className="rounded-xl p-8 relative z-10">
        <h3 className="text-xl font-black text-text tracking-tight mb-1 flex items-center gap-3">
          Rolling Validation Curve
        </h3>
        <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mb-8">Baseline 50% = Random Walk · Values above indicate predictive skill</p>
        
        <div className="h-[320px]">
          <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
            <ComposedChart data={data.rolling_accuracy} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <XAxis dataKey="date" stroke="rgba(255,255,255,0.1)" tick={{fill: palette.text, fontSize: 10, fontFamily: 'monospace'}} tickMargin={10} />
              <YAxis domain={[0, 100]} stroke="rgba(255,255,255,0.1)" tick={{fill: palette.text, fontSize: 10, fontFamily: 'monospace'}} />
              <Tooltip 
                contentStyle={{ backgroundColor: "rgba(var(--background), 0.9)", borderColor: "rgba(var(--text), 0.1)", color: "rgb(var(--text))", borderRadius: "12px", boxShadow: "0 10px 25px rgba(0,0,0,0.5)", backdropFilter: "blur(10px)" }} 
                itemStyle={{ fontFamily: 'monospace', fontSize: '12px' }}
                labelStyle={{ fontWeight: 'bold', marginBottom: '8px', color: palette.muted }}
              />
              <ReferenceLine y={50} stroke="rgba(234,179,8,0.5)" strokeDasharray="3 3" />
              <defs>
                <linearGradient id="accGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="rgba(212, 165, 71, 0.3)" stopOpacity={1}/>
                  <stop offset="95%" stopColor="rgba(212, 165, 71, 0)" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <Area type="monotone" dataKey="accuracy_7d" fill="url(#accGrad)" stroke="none" />
              <Line type="monotone" dataKey="accuracy_7d" stroke="rgb(212, 165, 71)" strokeWidth={3} dot={false} name="7D Average" />
              <Line type="monotone" dataKey="accuracy_30d" stroke="#eab308" strokeWidth={2} strokeDasharray="4 4" dot={false} name="30D Average" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </GlassCard>
      
      {/* SECTION 3 - Matrix & Calibration */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 relative z-10">
        
        {/* Confusion Matrix */}
        <GlassCard tier={2} shape="none" className="rounded-xl p-8">
          <h3 className="text-xl font-black text-text tracking-tight mb-1 flex items-center gap-3">
            Confusion Matrix
          </h3>
          <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mb-8">Rows = Predicted · Columns = Actual Outcome</p>
          
          <div className="grid grid-cols-6 gap-2">
            <div className="text-[10px] text-center p-1"></div>
            {data.confusion_labels.map((l: string) => (
              <div key={`col-${l}`} className="text-[9px] uppercase text-text-muted font-bold tracking-widest text-center flex items-center justify-center">
                {l.replace("_", "\n")}
              </div>
            ))}
            
            {data.confusion_matrix.map((row: number[], i: number) => (
              <div className="contents" key={`row-${i}`}>
                <div className="text-[9px] uppercase text-text-muted font-bold tracking-widest flex items-center justify-end pr-3 text-right">
                  {data.confusion_labels[i].replace("_", " ")}
                </div>
                {row.map((val: number, j: number) => {
                  const isDiagonal = i === j;
                  const intensity = Math.min(val / maxVal, 1);
                  
                  let bgColor = `rgba(var(--accent), ${intensity * 0.8 + 0.05})`;
                  if (isDiagonal) {
                    bgColor = `rgba(34, 197, 94, ${intensity * 0.8 + 0.1})`;
                  }
                  if (val === 0) bgColor = "rgba(255,255,255,0.02)";
                  
                  return (
                    <div 
                      key={`cell-${i}-${j}`} 
                      className="aspect-square flex items-center justify-center rounded-sm text-text text-xs font-black font-mono cursor-crosshair transition-all hover:scale-105 border border-white/5 hover:border-white/30 hover:shadow-[0_0_15px_rgba(255,255,255,0.1)]"
                      style={{ backgroundColor: bgColor }}
                      title={`Predicted ${data.confusion_labels[i]}, actually ${data.confusion_labels[j]}: ${val} instances`}
                    >
                      {val > 0 ? val : ""}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </GlassCard>
        
        {/* Confidence Calibration */}
        <GlassCard tier={2} shape="none" className="rounded-xl p-8">
          <h3 className="text-xl font-black text-text tracking-tight mb-1 flex items-center gap-3">
            Confidence Calibration
          </h3>
          <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mb-8">Expected vs Actual Precision per Decile</p>
          
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <ComposedChart data={data.confidence_calibration.map((d: any) => {
                  const upper = parseInt(d.confidence_range.split('-')[1]);
                  return { ...d, ideal: isNaN(upper) ? d.actual_accuracy : upper };
              })} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                <XAxis dataKey="confidence_range" stroke="rgba(255,255,255,0.1)" tick={{fill: palette.text, fontSize: 9, fontFamily: 'monospace'}} angle={-30} textAnchor="end" tickMargin={5} />
                <YAxis yAxisId="left" domain={[0, 100]} stroke="rgba(255,255,255,0.1)" tick={{fill: palette.text, fontSize: 10, fontFamily: 'monospace'}} />
                <YAxis yAxisId="right" orientation="right" hide />
                <Tooltip 
                    contentStyle={{ backgroundColor: "rgba(var(--background), 0.9)", borderColor: "rgba(var(--text), 0.1)", color: "rgb(var(--text))", borderRadius: "12px", backdropFilter: "blur(10px)" }} 
                    itemStyle={{ fontFamily: 'monospace', fontSize: '12px' }}
                />
                <Bar yAxisId="right" dataKey="bucket_counts" fill={palette.muted} fillOpacity={0.2} radius={[4, 4, 0, 0]} name="Frequency" />
                <Line yAxisId="left" type="monotone" dataKey="ideal" stroke={palette.success} strokeDasharray="3 3" dot={false} name="Ideal Calibration" />
                <Line yAxisId="left" type="monotone" dataKey="actual_accuracy" stroke={palette.accent} strokeWidth={3} dot={{r: 4, fill: palette.accent}} name="Empirical Accuracy" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[10px] text-text-muted mt-4 text-center border-t border-white/5 pt-4 uppercase tracking-widest">
             <span className="text-success font-bold">Over-performing</span> = Conservative · <span className="text-danger font-bold">Under-performing</span> = Overconfident
          </p>
        </GlassCard>
      </div>
      
      {/* SECTION 4 - Per Direction */}
      <GlassCard tier={2} shape="none" className="rounded-xl p-8 relative z-10">
        <h3 className="text-xl font-black text-text tracking-tight mb-8">Precision by Intent Vector</h3>
        <div className="space-y-6">
          {[
            { label: "Strong Buy", key: "strong_up", color: "bg-success shadow-[0_0_10px_rgba(34,197,94,0.5)]" },
            { label: "Buy", key: "up", color: "bg-success/60" },
            { label: "Neutral", key: "neutral", color: "bg-text-muted" },
            { label: "Sell", key: "down", color: "bg-danger/60" },
            { label: "Strong Sell", key: "strong_down", color: "bg-danger shadow-[0_0_10px_rgba(239,68,68,0.5)]" },
          ].map(d => {
            const acc = (data.per_direction_accuracy?.[d.key] || 0) * 100;
            return (
              <div key={d.key} className="flex items-center gap-6 group">
                <div className="w-32 text-right"><DirectionBadge direction={d.key} /></div>
                <div className="flex-1 h-3 bg-surface border border-white/5 rounded-full overflow-hidden relative">
                  <div className="absolute left-[50%] top-0 bottom-0 w-px bg-white/20 z-10" />
                  <div className={`h-full transition-all duration-1000 ${d.color}`} style={{ width: `${acc}%` }} />
                </div>
                <div className="w-20 text-right font-mono text-text font-black text-lg group-hover:text-accent transition-colors">{acc.toFixed(1)}%</div>
              </div>
            );
          })}
        </div>
      </GlassCard>
      
      {/* SECTION 5 - Per Asset */}
      <GlassCard tier={2} shape="none" className="rounded-xl p-0 relative z-10 overflow-hidden">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 p-8 border-b border-white/5 bg-surface/30">
          <div>
            <h3 className="text-xl font-black text-text tracking-tight">Asset Isolation Metrics</h3>
            <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-1">Cross-sectional model performance</p>
          </div>
          <div className="relative">
              <input 
                type="text" 
                placeholder="Query symbol..." 
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="bg-surface/50 border border-white/10 rounded-sm pl-4 pr-10 py-3 text-sm text-text placeholder-text-muted focus:outline-none focus:border-accent transition-colors w-full md:w-64 font-mono font-bold hover:bg-surface/80 shadow-inner"
              />
              <div className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">
                  ⌘F
              </div>
          </div>
        </div>
        
        <div className="overflow-x-auto custom-scrollbar p-0">
          <table className="w-full text-sm text-left">
            <thead className="text-[10px] text-text-muted uppercase tracking-widest bg-surface/50 font-mono border-b border-white/5">
              <tr>
                <th className="px-8 py-5">Node Identity</th>
                <th className="px-8 py-5 text-right">Hit Rate</th>
                <th className="px-8 py-5 text-right">True Positives</th>
                <th className="px-8 py-5 text-right">False Positives</th>
                <th className="px-8 py-5 text-right">Mean Certainty</th>
                <th className="px-8 py-5 text-right">Optimal Vector</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {visibleAssets.map(a => {
                const a_acc = a.accuracy * 100;
                const a_color = a_acc >= 60 ? "text-success drop-shadow-[0_0_5px_rgba(34,197,94,0.3)]" : a_acc >= 50 ? "text-warning" : "text-danger";
                return (
                  <tr key={a.symbol} className="hover:bg-white/[0.02] transition-colors group">
                    <td className="px-8 py-4 font-sans font-black text-lg text-text">
                      <Link href={`/coin/${a.symbol}`} className="hover:text-accent transition-colors flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-surface/50 border border-white/10 flex items-center justify-center font-bold text-xs shadow-inner text-text-muted group-hover:text-accent">
                            {a.symbol.charAt(0)}
                          </div>
                          {a.symbol}
                      </Link>
                    </td>
                    <td className={`px-8 py-4 text-right font-mono font-black text-lg ${a_color}`}>{a_acc.toFixed(1)}%</td>
                    <td className="px-8 py-4 text-right font-mono text-success font-bold">{a.correct}</td>
                    <td className="px-8 py-4 text-right font-mono text-danger font-bold">{a.wrong}</td>
                    <td className="px-8 py-4 text-right font-mono text-text-muted">
                        <div className="flex items-center justify-end gap-2">
                            <span>{a.avg_confidence.toFixed(1)}%</span>
                            <div className="w-12 h-1.5 bg-background rounded-full overflow-hidden">
                                <div className="h-full bg-accent" style={{width: `${a.avg_confidence}%`}} />
                            </div>
                        </div>
                    </td>
                    <td className="px-8 py-4 text-right"><DirectionBadge direction={a.best_direction} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        
        {!showAll && assetEntries.length > 20 && (
          <div className="p-6 border-t border-white/5 bg-surface/10">
              <button 
                onClick={() => setShowAll(true)}
                className="w-full py-4 glass bg-white/5 border border-white/10 hover:border-white/20 rounded-sm text-xs font-black uppercase tracking-widest text-text transition-all shadow-inner hover:bg-white/10"
              >
                Reveal Entire Graph
              </button>
          </div>
        )}
      </GlassCard>
      
      <ScrollToTop />
    </div>
  );
}

