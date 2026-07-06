"use client";

import { useMemo, useEffect, useState } from "react";
import { apiService } from "@/lib/api";
import { useChartPalette } from "@/lib/useChartPalette";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, BarChart, Bar, Cell, CartesianGrid, ComposedChart } from "recharts";
import Link from "next/link";
import { TrendingUp, TrendingDown, MessageSquareShare, Activity, HeartPulse } from "lucide-react";
import { ChartSkeleton } from "@/components/PageSkeleton";
import { GlassCard } from "@/components/ui/GlassCard";
import { ScrollToTop } from "@/components/ScrollToTop";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// --- Sector Color Mapping ---
const getSectorColor = (sector: string) => {
  const colors: Record<string, string> = {
    layer1: "rgb(59, 130, 246)",
    defi: "rgb(139, 92, 246)",
    exchange: "rgb(245, 158, 11)",
    payment: "rgb(16, 185, 129)",
    gaming: "rgb(236, 72, 153)",
    privacy: "rgb(99, 102, 241)",
    storage: "rgb(20, 184, 166)",
    other: "rgb(148, 163, 184)"
  };
  return colors[sector?.toLowerCase()] || colors.other;
};

// --- SVG Gauge Component ---
const FearGreedGauge = ({ value }: { value: number }) => {
  const palette = useChartPalette();
  // Convert 0-100 to rotation (-90 to +90 degrees)
  const clampedValue = Math.max(0, Math.min(100, value));
  const rotation = (clampedValue / 100) * 180 - 90;
  
  // Zones: Extreme Fear (0-24), Fear (25-44), Neutral (45-55), Greed (56-74), Extreme Greed (75-100)
  let zoneLabel = "Neutral";
  let zoneColor: string = palette.muted; // Neutral
  if (clampedValue <= 24) { zoneLabel = "Extreme Fear"; zoneColor = palette.danger; }
  else if (clampedValue <= 44) { zoneLabel = "Fear"; zoneColor = palette.danger; }
  else if (clampedValue <= 55) { zoneLabel = "Neutral"; zoneColor = palette.muted; }
  else if (clampedValue <= 74) { zoneLabel = "Greed"; zoneColor = palette.success; }
  else { zoneLabel = "Extreme Greed"; zoneColor = palette.success; }

  // SVG Geometry
  const width = 320;
  const height = 180;
  const cx = width / 2;
  const cy = height - 20; // needle pivot
  const r = 120; // radius
  
  // Using circle with stroke-dasharray
  const circ = 2 * Math.PI * r;
  const halfCirc = circ / 2;
  
  // Percentages of the 180 degree arc
  const p1 = 24 / 100 * halfCirc; // Extreme Fear
  const p2 = 20 / 100 * halfCirc; // Fear (44-24 = 20)
  const p3 = 11 / 100 * halfCirc; // Neutral (55-44 = 11)
  const p4 = 19 / 100 * halfCirc; // Greed (74-55 = 19)
  const p5 = 26 / 100 * halfCirc; // Extreme Greed (100-74 = 26)

  // Offsets for each segment
  const offset1 = 0; // starts at left
  const offset2 = -p1;
  const offset3 = -(p1 + p2);
  const offset4 = -(p1 + p2 + p3);
  const offset5 = -(p1 + p2 + p3 + p4);

  return (
    <div className="flex flex-col items-center relative">
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-48 rounded-full blur-[80px] pointer-events-none opacity-50 transition-colors duration-1000" style={{ backgroundColor: zoneColor }} />
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="relative z-10 drop-shadow-[0_0_15px_rgba(0,0,0,0.5)]">
        {/* Base circle for path, rotated so it starts from left (180 deg) and goes to right */}
        <g transform={`rotate(180, ${cx}, ${cy})`}>
          {/* Extreme Greed */}
          <circle cx={cx} cy={cy} r={r} fill="transparent" stroke={palette.success} strokeWidth="24" strokeDasharray={`${p5} ${circ}`} strokeDashoffset={offset5} className="drop-shadow-[0_0_5px_rgba(34,197,94,0.5)]" />
          {/* Greed */}
          <circle cx={cx} cy={cy} r={r} fill="transparent" stroke={palette.success} strokeWidth="24" strokeDasharray={`${p4} ${circ}`} strokeDashoffset={offset4} />
          {/* Neutral */}
          <circle cx={cx} cy={cy} r={r} fill="transparent" stroke={palette.muted} strokeWidth="24" strokeDasharray={`${p3} ${circ}`} strokeDashoffset={offset3} />
          {/* Fear */}
          <circle cx={cx} cy={cy} r={r} fill="transparent" stroke={palette.danger} strokeWidth="24" strokeDasharray={`${p2} ${circ}`} strokeDashoffset={offset2} />
          {/* Extreme Fear */}
          <circle cx={cx} cy={cy} r={r} fill="transparent" stroke={palette.danger} strokeWidth="24" strokeDasharray={`${p1} ${circ}`} strokeDashoffset={offset1} className="drop-shadow-[0_0_5px_rgba(239,68,68,0.5)]" />
        </g>
        
        {/* Needle Group */}
        <g transform={`translate(${cx}, ${cy}) rotate(${rotation})`} className="transition-transform duration-1000 ease-out">
          {/* Needle base */}
          <circle cx="0" cy="0" r="10" fill="rgb(var(--text))" className="opacity-90" />
          <circle cx="0" cy="0" r="4" fill="rgb(var(--background))" />
          {/* Needle pointer */}
          <polygon points="-3,0 3,0 0,-115" fill="rgb(var(--text))" className="opacity-90" />
        </g>
        
      </svg>
      {/* Text Label Below SVG */}
      <div className="flex flex-col items-center mt-2 relative z-20">
        <span className="text-5xl font-black text-text font-mono tracking-tighter">
          {Math.round(value)}
        </span>
        <span className="text-xs font-bold tracking-widest uppercase mt-1" style={{ color: zoneColor }}>
          {zoneLabel}
        </span>
      </div>
    </div>
  );
};

export default function SentimentPage() {
  const [mounted, setMounted] = useState(false);
  const palette = useChartPalette();
  const { data: fgHistory } = useSWR(`${BASE}/api/sentiment-data/fear-greed-history?days=365`, fetcher, { refreshInterval: 120000 });
  const { data: btcHistory } = useSWR(`${BASE}/api/sentiment-data/fear-greed-vs-btc?days=365`, fetcher, { refreshInterval: 120000 });
  const { data: sectorSent } = useSWR(`${BASE}/api/sentiment-data/sector-sentiment`, fetcher, { refreshInterval: 120000 });
  const [synthesis, setSynthesis] = useState<any>(null);
  const { data: trending } = useSWR(`${BASE}/api/sentiment-data/trending`, fetcher, { refreshInterval: 120000 });

  useEffect(() => setMounted(true), []);
  useEffect(() => { apiService.getLatestSynthesis().then(setSynthesis).catch(console.error); }, []);

  if (!mounted) return <div className="h-screen w-full flex items-center justify-center text-text-muted font-mono bg-background">Loading chart components...</div>;
  if (!fgHistory || !btcHistory || !sectorSent || !trending) return <ChartSkeleton />;

  // Calculate current, yesterday, 7d avg
  const today = fgHistory[fgHistory.length - 1]?.fear_greed || 50;
  const yesterday = fgHistory.length > 1 ? fgHistory[fgHistory.length - 2]?.fear_greed : today;
  const last7 = fgHistory.slice(-7);
  const avg7 = last7.reduce((sum: number, curr: any) => sum + curr.fear_greed, 0) / (last7.length || 1);

  return (
    <div className="space-y-8 pt-8 p-6 glass-2 rounded-2xl overflow-hidden max-w-[1600px] mx-auto relative">
      <div className="absolute top-[10%] right-[-10%] w-[500px] h-[500px] bg-accent/5 rounded-full blur-[150px] pointer-events-none" />
      <div className="absolute bottom-[20%] left-[-10%] w-[400px] h-[400px] bg-success/5 rounded-full blur-[120px] pointer-events-none" />

      {/* HEADER */}
      <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-end gap-6 mb-4 border-b border-white/10 pb-6">
        <div>
          <h1 className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted flex items-center gap-4 tracking-tight">
            <div className="p-3 glass bg-accent/10 rounded-sm shadow-inner shadow-accent/20">
                <MessageSquareShare className="text-accent" size={32} />
            </div>
            Social Substrates
          </h1>
          <p className="text-text-muted mt-3 font-light tracking-wide max-w-xl">
            NLP-driven sentiment analysis, crowd psychology vectors, and fear/greed clustering.
          </p>
        </div>
      </div>
      
      <div className="relative z-10 space-y-8">
        {/* SECTION 1 & 2 - Top Row: Gauge and History Area */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          {/* Gauge Card */}
          <GlassCard tier={2} shape="none" className="interactive-lift rounded-xl p-8 flex flex-col items-center justify-center relative overflow-hidden group">
            <div className="absolute top-0 right-0 p-4">
                <HeartPulse size={20} className={`opacity-50 group-hover:opacity-100 transition-opacity ${today > 60 ? 'text-success animate-pulse' : today < 40 ? 'text-danger' : 'text-text-muted'}`} />
            </div>
            <h3 className="text-xl font-black text-text tracking-tight mb-8">Fear & Greed Index</h3>
            
            <FearGreedGauge value={today} />
            
            <div className="flex gap-8 mt-6">
              <div className="text-[10px] uppercase tracking-widest font-bold text-text-muted text-center">
                Yesterday<br/><span className="text-lg font-black text-text font-mono mt-1 block">{yesterday}</span>
              </div>
              <div className="w-px h-8 bg-white/10" />
              <div className="text-[10px] uppercase tracking-widest font-bold text-text-muted text-center">
                7D Vector<br/><span className="text-lg font-black text-text font-mono mt-1 block">{Math.round(avg7)}</span>
              </div>
            </div>
          </GlassCard>
          
          {/* Fear & Greed History Area */}
          <GlassCard tier={2} shape="none" className="rounded-xl p-8 lg:col-span-2">
            <div className="mb-6 flex justify-between items-end">
                <div>
                    <h3 className="text-xl font-black text-text tracking-tight flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full glass bg-accent/10 border border-accent/20 flex items-center justify-center">
                            <Activity className="text-accent" size={16} />
                        </div>
                        Emotional Trajectory
                    </h3>
                    <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-2">12-Month Rolling Analysis window</p>
                </div>
                <div className="hidden sm:flex gap-4 text-[9px] uppercase font-bold tracking-widest">
                    <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-success/80 shadow-[0_0_5px_rgba(34,197,94,0.5)]" /> Greed</div>
                    <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-text-muted/50" /> Neutral</div>
                    <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-danger/80 shadow-[0_0_5px_rgba(239,68,68,0.5)]" /> Fear</div>
                </div>
            </div>
            
            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                <AreaChart data={fgHistory} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorFG" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={palette.success} stopOpacity={1}/>
                      <stop offset="40%" stopColor={palette.muted} stopOpacity={0.8}/>
                      <stop offset="100%" stopColor={palette.danger} stopOpacity={1}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="transparent" vertical={false} />
                  <XAxis dataKey="date" stroke={palette.muted} tick={{fill: palette.text, fontSize: 10, fontFamily: 'monospace'}} minTickGap={30} tickLine={false} axisLine={false} />
                  <YAxis domain={[0, 100]} stroke={palette.muted} tick={{fill: palette.text, fontSize: 10, fontFamily: 'monospace'}} tickLine={false} axisLine={false} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: "rgba(var(--background), 0.9)", borderColor: "rgba(var(--text), 0.1)", borderRadius: "12px", color: "rgb(var(--text))", backdropFilter: "blur(10px)" }} 
                    itemStyle={{ fontFamily: 'monospace', fontWeight: 'bold' }}
                    labelStyle={{ color: palette.muted, marginBottom: '8px' }}
                  />
                  <ReferenceLine y={75} stroke={palette.success} strokeDasharray="3 3" label={{ position: 'insideTopLeft', value: 'EXTREME GREED', fill: 'rgba(34,197,94,0.8)', fontSize: 9, fontFamily: 'sans-serif', fontWeight: 'bold', letterSpacing: '0.1em' }} />
                  <ReferenceLine y={25} stroke={palette.danger} strokeDasharray="3 3" label={{ position: 'insideBottomLeft', value: 'EXTREME FEAR', fill: 'rgba(239,68,68,0.8)', fontSize: 9, fontFamily: 'sans-serif', fontWeight: 'bold', letterSpacing: '0.1em' }} />
                  <Area type="monotone" dataKey="fear_greed" stroke={palette.warning} strokeWidth={2} fillOpacity={1} fill="url(#colorFG)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </GlassCard>
        </div>
        
                {/* SECTION 2.5 - Qualitative Synthesis */}
        {synthesis && (
          <GlassCard tier={2} shape="none" className="rounded-xl p-8 relative overflow-hidden mb-8 group">
            <div className="absolute top-0 right-0 w-64 h-64 bg-accent/5 rounded-full blur-[80px] pointer-events-none" />
            <h3 className="text-xl font-black text-text tracking-tight flex items-center gap-3 mb-6">
              <div className="w-8 h-8 rounded-full glass bg-accent/10 border border-accent/20 flex items-center justify-center">
                <MessageSquareShare className="text-accent" size={16} />
              </div>
              Swarm Synthesis Readout
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 relative z-10">
              <div className="p-5 bg-surface/50 border border-white/5 rounded-sm hover:border-accent/30 transition-colors">
                <h4 className="text-[10px] font-bold font-mono tracking-widest uppercase text-text-muted mb-3 pb-2 border-b border-white/5">Macro Economist</h4>
                <p className="text-sm text-text/90 leading-relaxed font-light">{synthesis.macro_analysis}</p>
              </div>
              <div className="p-5 bg-surface/50 border border-white/5 rounded-sm hover:border-accent/30 transition-colors">
                <h4 className="text-[10px] font-bold font-mono tracking-widest uppercase text-text-muted mb-3 pb-2 border-b border-white/5">On-Chain Detective</h4>
                <p className="text-sm text-text/90 leading-relaxed font-light">{synthesis.onchain_analysis}</p>
              </div>
              <div className="p-5 bg-surface/50 border border-white/5 rounded-sm hover:border-accent/30 transition-colors">
                <h4 className="text-[10px] font-bold font-mono tracking-widest uppercase text-text-muted mb-3 pb-2 border-b border-white/5">Sentiment Analyst</h4>
                <p className="text-sm text-text/90 leading-relaxed font-light">{synthesis.sentiment_analysis}</p>
              </div>
            </div>
            <div className="mt-4 text-right">
              <span className="text-[9px] uppercase tracking-widest font-mono text-text-muted bg-black/40 px-2 py-1 shape-tag">Subject Asset: {synthesis.symbol}</span>
            </div>
          </GlassCard>
        )}

        {/* SECTION 3 - Dual Axis: Fear & Greed vs BTC Price */}
        <GlassCard tier={2} shape="none" className="rounded-xl p-0 overflow-hidden">
          <div className="p-8 border-b border-white/5 bg-surface/30">
            <h3 className="text-xl font-black text-text tracking-tight">Psychology vs. Price Action</h3>
            <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-1">Cross-referencing network sentiment against BTC valuations</p>
          </div>
          
          <div className="p-8 h-[400px] w-full">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <ComposedChart data={btcHistory} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="transparent" vertical={false} />
                <XAxis dataKey="date" stroke={palette.muted} tick={{fill: palette.text, fontSize: 10, fontFamily: 'monospace'}} minTickGap={30} tickLine={false} axisLine={false} />
                <YAxis yAxisId="left" domain={['auto', 'auto']} stroke={palette.muted} tick={{fill: palette.text, fontSize: 10, fontFamily: 'monospace'}} tickFormatter={(v) => `$${v.toLocaleString()}`} tickLine={false} axisLine={false} />
                <YAxis yAxisId="right" orientation="right" domain={[0, 100]} stroke={palette.muted} tick={{fill: palette.warning, fontSize: 10, fontFamily: 'monospace', fontWeight: 'bold'}} tickLine={false} axisLine={false} />
                <Tooltip 
                  contentStyle={{ backgroundColor: "rgba(var(--background), 0.9)", borderColor: "rgba(var(--text), 0.1)", borderRadius: "12px", color: "rgb(var(--text))", backdropFilter: "blur(10px)" }} 
                  itemStyle={{ fontFamily: 'monospace', fontWeight: 'bold' }}
                  labelStyle={{ color: palette.muted, marginBottom: '8px' }}
                  formatter={(val: any, name: any) => [name === 'btc_price' ? `$${Number(val).toLocaleString()}` : val, name === 'btc_price' ? 'BTC Price' : 'Index Level']}
                />
                <Area yAxisId="right" type="monotone" dataKey="fear_greed" fill="url(#colorFG)" stroke="none" fillOpacity={0.15} />
                <Line yAxisId="left" type="monotone" dataKey="btc_price" stroke={palette.text} strokeWidth={3} dot={false} className="drop-shadow-[0_0_8px_rgba(var(--text),0.3)]" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>
        
        {/* SECTION 4 - Two Column Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          
          {/* LEFT: Sentiment by Sector */}
          <GlassCard tier={2} shape="none" className="rounded-xl p-8">
            <div className="mb-8">
              <h3 className="text-xl font-black text-text tracking-tight">Sector Disposition</h3>
              <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-1">Aggregated sentiment variance across topology</p>
            </div>
            
            <div className="h-[320px] w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                <BarChart data={sectorSent} layout="vertical" margin={{ top: 5, right: 30, left: 10, bottom: 5 }}>
                  <XAxis type="number" domain={[-1, 1]} stroke={palette.muted} tick={{fill: palette.text, fontSize: 10, fontFamily: 'monospace'}} tickLine={false} axisLine={false} />
                  <YAxis dataKey="sector" type="category" stroke={palette.muted} tick={{fill: palette.text, fontSize: 10, fontFamily: 'monospace', fontWeight: 'bold'}} tickFormatter={(val) => typeof val === 'string' ? val.toUpperCase() : val} tickLine={false} axisLine={false} width={80} />
                  <Tooltip 
                    cursor={{fill: 'rgba(255,255,255,0.05)'}} 
                    contentStyle={{ backgroundColor: "rgba(var(--background), 0.9)", borderColor: "rgba(var(--text), 0.1)", borderRadius: "12px", color: "rgb(var(--text))", backdropFilter: "blur(10px)" }}
                    itemStyle={{ fontFamily: 'monospace', fontWeight: 'bold' }}
                    formatter={(v: any, n: any, props: any) => [`${v > 0 ? '+' : ''}${Number(v).toFixed(3)} (${props.payload.asset_count} nodes)`, 'Vector']}
                  />
                  <ReferenceLine x={0} stroke="rgba(255,255,255,0.2)" strokeDasharray="3 3" />
                  <Bar dataKey="avg_sentiment" radius={[0, 4, 4, 0]} barSize={20}>
                    {
                      sectorSent.map((entry: any, index: number) => (
                        <Cell key={`cell-${index}`} fill={entry.avg_sentiment >= 0 ? palette.success : palette.danger} className={entry.avg_sentiment >= 0 ? 'drop-shadow-[0_0_5px_rgba(34,197,94,0.5)]' : 'drop-shadow-[0_0_5px_rgba(239,68,68,0.5)]'} />
                      ))
                    }
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </GlassCard>
          
          {/* RIGHT: Trending Assets */}
          <GlassCard tier={2} shape="none" className="rounded-xl p-0 overflow-hidden flex flex-col">
            <div className="p-8 border-b border-white/5 bg-surface/30">
              <h3 className="text-xl font-black text-text tracking-tight">Social Velocity Movers</h3>
              <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-1">Highest derivative changes in NLP scores (7d)</p>
            </div>
            
            <div className="flex-1 p-8 grid grid-cols-1 md:grid-cols-2 gap-8">
              {/* Gainers */}
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-success mb-2">
                  <div className="p-1.5 rounded-full glass bg-success/20 border border-success/30 shadow-inner">
                    <TrendingUp size={14} className="drop-shadow-[0_0_5px_currentColor]" />
                  </div>
                  <h4 className="font-bold text-xs uppercase tracking-widest text-text">Positive Momentum</h4>
                </div>
                <div className="space-y-3">
                  {trending.gainers.map((g: any, i: number) => (
                    <div key={i} className="interactive-lift flex justify-between items-center glass bg-success/5 p-4 rounded-sm border border-success/10 hover:border-success/30 hover:bg-success/10 transition-colors group">
                      <div className="flex flex-col gap-1.5">
                        <Link href={`/graph?asset=${g.symbol}`} className="font-mono font-black text-text group-hover:text-success transition-colors text-lg tracking-tight">{g.symbol}</Link>
                        <span className="text-[9px] uppercase tracking-widest font-bold text-white px-2 py-0.5 shape-tag inline-block w-max shadow-inner" style={{ backgroundColor: getSectorColor(g.sector) }}>{g.sector}</span>
                      </div>
                      <div className="text-right">
                        <div className="text-base font-black font-mono text-success drop-shadow-[0_0_5px_rgba(34,197,94,0.5)]">+{g.change.toFixed(3)}</div>
                        <div className="text-[10px] text-text-muted font-mono bg-black/40 px-2 py-0.5 rounded-sm mt-1">{g.prev_sentiment.toFixed(2)} → {g.current_sentiment.toFixed(2)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              
              {/* Losers */}
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-danger mb-2">
                  <div className="p-1.5 rounded-full glass bg-danger/20 border border-danger/30 shadow-inner">
                    <TrendingDown size={14} className="drop-shadow-[0_0_5px_currentColor]" />
                  </div>
                  <h4 className="font-bold text-xs uppercase tracking-widest text-text">Negative Momentum</h4>
                </div>
                <div className="space-y-3">
                  {trending.losers.map((l: any, i: number) => (
                    <div key={i} className="interactive-lift flex justify-between items-center glass bg-danger/5 p-4 rounded-sm border border-danger/10 hover:border-danger/30 hover:bg-danger/10 transition-colors group">
                      <div className="flex flex-col gap-1.5">
                        <Link href={`/graph?asset=${l.symbol}`} className="font-mono font-black text-text group-hover:text-danger transition-colors text-lg tracking-tight">{l.symbol}</Link>
                        <span className="text-[9px] uppercase tracking-widest font-bold text-white px-2 py-0.5 shape-tag inline-block w-max shadow-inner" style={{ backgroundColor: getSectorColor(l.sector) }}>{l.sector}</span>
                      </div>
                      <div className="text-right">
                        <div className="text-base font-black font-mono text-danger drop-shadow-[0_0_5px_rgba(239,68,68,0.5)]">{l.change.toFixed(3)}</div>
                        <div className="text-[10px] text-text-muted font-mono bg-black/40 px-2 py-0.5 rounded-sm mt-1">{l.prev_sentiment.toFixed(2)} → {l.current_sentiment.toFixed(2)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            
          </GlassCard>
        </div>
        
      </div>
      <ScrollToTop />
    </div>
  );
}

