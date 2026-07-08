"use client";
import React, { useState, useEffect, useMemo, memo } from "react";

import { useChartPalette } from "@/lib/useChartPalette";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from "recharts";
import Link from "next/link";
import { ChartSkeleton } from "@/components/PageSkeleton";
import { ScrollToTop } from "@/components/ScrollToTop";
import { GlassCard } from "@/components/ui/GlassCard";
import { Layers, RefreshCw, BarChart2, ShieldAlert, ArrowUpRight, ArrowDownRight, Activity, Zap, Grid3x3, BarChart3, Network, GitGraph, Maximize, Target } from "lucide-react";

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

// --- Heatmap Cell Component (Memoized) ---
const HeatmapCell = memo(({ 
  i, j, value, symA, symB, onEnter, onLeave, isRowActive, isColActive, isSectorMatch, isSectorPartial, isSectorInactive 
}: any) => {
  
  // Interpolate color from -1 to 1
  let bgColor = "rgba(var(--background), 0.4)";
  if (i === j) {
    bgColor = "rgba(var(--accent), 0.8)"; // self-correlation
  } else if (value > 0) {
    // Green scale
    const intensity = Math.min(value, 1);
    bgColor = `rgba(34, 197, 94, ${intensity * 0.8 + 0.1})`; // From faint green to solid
  } else if (value < 0) {
    // Red scale
    const intensity = Math.min(Math.abs(value), 1);
    bgColor = `rgba(239, 68, 68, ${intensity * 0.8 + 0.1})`; // From faint red to solid
  }
  
  let classes = "w-full h-full transition-all cursor-crosshair rounded-[2px] ";
  
  if (isSectorMatch) {
    classes += "ring-1 ring-accent/80 z-10 shadow-[0_0_10px_rgba(var(--accent),0.3)] ";
  } else if (isSectorInactive) {
    classes += "opacity-20 grayscale blur-[1px] ";
  } else if (isSectorPartial) {
    classes += "opacity-70 ";
  }
  
  if (isRowActive || isColActive) {
    classes += "ring-1 ring-text/50 z-20 shadow-[0_0_5px_rgba(var(--text),0.2)] ";
  }

  let cellText = "";
  if (value > 0.7 || value < -0.7) cellText = "STRONG";
  else if (value > 0.3 || value < -0.3) cellText = "MODERATE";
  else cellText = "WEAK";
  if (i === j) cellText = "IDENTITY";

  return (
    <div 
      className={classes + " relative group overflow-hidden"}
      style={{ backgroundColor: bgColor }}
      onMouseEnter={() => onEnter({ i, j, val: value, symA, symB })}
      onMouseLeave={onLeave}
    >
      <div className="absolute inset-0 flex items-center justify-center opacity-100 group-hover:opacity-0 transition-opacity duration-300">
         <span className="text-[9px] leading-none font-mono font-bold text-text/40 truncate max-w-full px-0.5">{cellText}</span>
      </div>
      <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300 delay-75">
         <span className="text-[10px] leading-none font-mono font-black text-text">{value.toFixed(2)}</span>
      </div>
    </div>
  );
});
HeatmapCell.displayName = "HeatmapCell";

export default function CorrelationsPage() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const palette = useChartPalette();
  
  const [days, setDays] = useState(30);
  const [selectedSector, setSelectedSector] = useState("all");
  const [cellSize, setCellSize] = useState(16);
  const [basis, setBasis] = useState("Price Correlation");
  
  // Hover state
  const [hoveredCell, setHoveredCell] = useState<{i: number, j: number, val: number, symA: string, symB: string} | null>(null);

  const { data: matrixData, isLoading: matrixLoading } = useSWR(`${BASE}/api/v1/correlations/matrix?days=${days}&basis=${basis}`, fetcher, { refreshInterval: 300000 });
  const { data: sectorData, isLoading: sectorLoading } = useSWR(`${BASE}/api/v1/correlations/sector-average?days=${days}&basis=${basis}`, fetcher, { refreshInterval: 300000 });
  const { data: assetsData } = useSWR(`${BASE}/api/v1/assets`, fetcher, { refreshInterval: 300000 });
  
  const assetMap = useMemo(() => {
    if (!assetsData) return {};
    const map: Record<string, string> = {};
    assetsData.forEach((a: any) => map[a.symbol] = a.sector);
    return map;
  }, [assetsData]);

  if (!mounted) return <div className="h-screen w-full flex items-center justify-center text-text-muted font-mono bg-background">Loading chart components...</div>;

  if (matrixLoading || sectorLoading) return <ChartSkeleton />;
  
  if (!matrixData || !sectorData) return (
    <div className="flex flex-col items-center justify-center h-[50vh] space-y-6">
      <div className="text-danger bg-danger/10 p-6 rounded-sm border border-danger/20 font-mono text-center flex flex-col items-center gap-4 shadow-[0_0_30px_rgba(239,68,68,0.1)]">
          <Activity size={48} className="text-danger drop-shadow-[0_0_10px_rgba(239,68,68,0.5)]" />
          <p>Correlation tensor generation failed. Retrying quantum alignment...</p>
      </div>
    </div>
  );

  const { symbols, matrix, top_pairs } = matrixData;
  const n = symbols.length;

  // Compute avg correlation
  let sum = 0, count = 0;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      sum += matrix[i][j];
      count++;
    }
  }
  const avgCorr = count > 0 ? sum / count : 0;

  // Sector avg data for Recharts
  const sectorBars = sectorData.sectors.map((s: string) => ({
    name: s,
    value: sectorData.intra_sector[s] || 0
  })).sort((a: any, b: any) => b.value - a.value);

  // Available sectors from data
  const sectorsList = Array.from(new Set(Object.values(assetMap))).filter(Boolean) as string[];

  return (
    <div className="space-y-8 pt-8 p-6 glass-2 rounded-2xl overflow-hidden max-w-[1600px] mx-auto relative">
      <div className="absolute top-[10%] right-[-100px] w-96 h-96 bg-accent/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[20%] left-[-100px] w-80 h-80 bg-success/5 rounded-full blur-[100px] pointer-events-none" />

      {/* HEADER */}
      <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-end gap-6 mb-4 border-b border-text/10 pb-6">
        <div>
          <h1 className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted flex items-center gap-4 tracking-tight">
            <div className="p-3 glass bg-accent/10 rounded-sm shadow-inner shadow-accent/20">
                <Network className="text-accent" size={32} />
            </div>
            Neural Correlations
          </h1>
          <p className="text-text-muted mt-3 font-light tracking-wide max-w-xl">
            Spatio-temporal isomorphic mapping of network token velocity and price action.
          </p>
        </div>
        
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
          <div className="flex glass bg-surface/50 rounded-sm border border-text/10 p-1 shadow-inner">
             {["Price Correlation", "On-Chain Motif Similarity"].map(b => (
               <button
                 key={b}
                 onClick={() => setBasis(b)}
                 className={`px-4 py-2 rounded-sm text-[10px] font-black uppercase tracking-widest transition-all ${
                   basis === b 
                     ? "bg-accent/20 text-accent border border-accent/30 shadow-[0_0_10px_rgba(var(--accent),0.2)]" 
                     : "text-text-muted hover:text-text hover:bg-text/5 border border-transparent"
                 }`}
               >
                 {b}
               </button>
             ))}
          </div>
          <div className="relative">
            <select 
              value={selectedSector}
              onChange={(e) => setSelectedSector(e.target.value)}
              className="appearance-none glass bg-surface/50 text-xs text-text font-bold px-4 py-3 pr-10 rounded-sm border border-text/10 focus:outline-none focus:border-accent/50 focus:shadow-[0_0_15px_rgba(var(--accent),0.2)] transition-all cursor-pointer uppercase tracking-widest"
            >
              <option value="all">Global Topology</option>
              {sectorsList.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <Target className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" size={14} />
          </div>
          
          <div className="flex glass bg-surface/50 rounded-sm border border-text/10 p-1 shadow-inner">
            {[7, 30, 90, 365].map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-4 py-2 rounded-sm text-[10px] font-black uppercase tracking-widest transition-all ${
                  days === d 
                    ? "bg-accent/20 text-accent border border-accent/30 shadow-[0_0_10px_rgba(var(--accent),0.2)]" 
                    : "text-text-muted hover:text-text hover:bg-text/5 border border-transparent"
                }`}
              >
                {d === 365 ? "1Y Vector" : `${d}D`}
              </button>
            ))}
          </div>
        </div>
      </div>
      
      <div className="relative z-10 space-y-8">
        {/* SECTION 1 - Header Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <GlassCard tier={2} shape="none" className="interactive-lift rounded-xl p-6 flex items-center gap-4 group hover:bg-text/[0.02] transition-colors h-32">
            <div className="p-3 rounded-sm glass bg-text/5 group-hover:bg-text/10 transition-colors shadow-inner shadow-text/5 border border-text/10">
                <GitGraph size={24} className="text-text" />
            </div>
            <div>
              <div className="text-3xl font-black font-sans text-text tracking-tight group-hover:scale-105 transition-transform origin-left">{symbols.length}</div>
              <div className="text-[10px] uppercase tracking-widest font-bold text-text-muted mt-1">Nodes Analyzed</div>
            </div>
          </GlassCard>
          <GlassCard tier={2} shape="none" className="interactive-lift rounded-xl p-6 flex items-center gap-4 group hover:bg-accent/[0.02] transition-colors h-32 hover:border-accent/30 hover:shadow-[0_0_20px_rgba(var(--accent),0.1)]">
            <div className="p-3 rounded-sm glass bg-accent/10 transition-colors shadow-inner shadow-accent/20 border border-accent/20">
                <Network size={24} className="text-accent drop-shadow-[0_0_5px_currentColor]" />
            </div>
            <div>
              <div className="text-3xl font-black font-sans text-accent tracking-tight group-hover:scale-105 transition-transform origin-left drop-shadow-[0_0_10px_rgba(var(--accent),0.3)]">{avgCorr.toFixed(3)}</div>
              <div className="text-[10px] uppercase tracking-widest font-bold text-text-muted mt-1">Mean Network Vector</div>
            </div>
          </GlassCard>
          <GlassCard tier={2} shape="none" className="interactive-lift rounded-xl p-6 flex items-center gap-4 group hover:bg-success/[0.02] transition-colors h-32 hover:border-success/30 hover:shadow-[0_0_20px_rgba(34,197,94,0.1)]">
            <div className="p-3 rounded-sm glass bg-success/10 transition-colors shadow-inner shadow-success/20 border border-success/20">
                <Zap size={24} className="text-success drop-shadow-[0_0_5px_currentColor]" />
            </div>
            <div>
              <div className="text-2xl font-black font-mono text-success tracking-tight group-hover:scale-105 transition-transform origin-left drop-shadow-[0_0_10px_rgba(34,197,94,0.3)] truncate max-w-[200px]">
                {top_pairs[0]?.symbol_a}<span className="text-text-muted/50 font-sans mx-1">/</span>{top_pairs[0]?.symbol_b}
              </div>
              <div className="text-[10px] uppercase tracking-widest font-bold text-text-muted mt-1 flex items-center gap-2">
                  Highest Isomorphism <span className="text-success font-mono bg-success/10 px-2 py-0.5 shape-tag border border-success/20">+{top_pairs[0]?.correlation.toFixed(3)}</span>
              </div>
            </div>
          </GlassCard>
        </div>
        
        {/* SECTION 2 - Correlation Heatmap */}
        <GlassCard tier={2} shape="none" className="rounded-xl p-0 overflow-hidden relative">
          <div className="p-8 border-b border-text/5 bg-surface/30 flex justify-between items-center flex-wrap gap-4">
            <div>
              <h3 className="text-xl font-black text-text tracking-tight">N-Dimensional Adjacency Matrix</h3>
              <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-1">Visualizing tensor co-movement probabilities</p>
            </div>
            
            <div className="flex items-center gap-4 bg-black/40 px-4 py-2 rounded-sm border border-text/5">
              <Maximize size={14} className="text-text-muted" />
              <input 
                type="range" 
                min="8" 
                max="32" 
                value={cellSize} 
                onChange={(e) => setCellSize(Number(e.target.value))}
                className="w-24 accent-accent"
              />
            </div>
          </div>
          
          <div className="p-8 bg-black/20 relative">
            {hoveredCell && (
              <div className="absolute top-12 right-12 glass bg-surface/90 border border-accent/50 rounded-sm p-4 shadow-[0_0_30px_rgba(var(--accent),0.2)] z-50 flex flex-col items-center backdrop-blur-xl transition-all pointer-events-none">
                <div className="flex items-center gap-3 mb-2 bg-black/50 px-3 py-1.5 rounded-sm border border-text/5">
                  <span className="font-mono font-black text-text text-lg">{hoveredCell.symA}</span>
                  <Network className="text-accent opacity-50" size={14} />
                  <span className="font-mono font-black text-text text-lg">{hoveredCell.symB}</span>
                </div>
                <div className={`text-3xl font-black font-mono tracking-tighter ${(hoveredCell.val || 0) > 0 ? "text-success drop-shadow-[0_0_10px_rgba(34,197,94,0.5)]" : (hoveredCell.val || 0) < 0 ? "text-danger drop-shadow-[0_0_10px_rgba(239,68,68,0.5)]" : "text-text-muted"}`}>
                  {(hoveredCell.val || 0) > 0 ? "+" : ""}{(hoveredCell.val || 0).toFixed(4)}
                </div>
                <div className="text-[10px] uppercase tracking-widest font-bold text-text-muted mt-2 border-t border-text/10 pt-2 w-full text-center">
                    Pearson Co-eff
                </div>
              </div>
            )}
            
            <div className="overflow-auto custom-scrollbar border border-text/5 bg-black/40 p-6 rounded-sm shadow-inner relative max-h-[800px]">
              <div 
                style={{ 
                  display: 'grid', 
                  gridTemplateColumns: `auto repeat(${n}, ${cellSize}px)`,
                  gridAutoRows: `${cellSize}px`,
                  gap: '2px'
                }}
              >
                {/* Top-left empty cell */}
                <div />
                
                {/* Top headers */}
                {symbols.map((sym: string, j: number) => (
                  <div key={`col-${j}`} className="flex items-end justify-center h-full pb-2 overflow-visible relative">
                    <span className={`text-[10px] font-mono font-bold absolute bottom-2 origin-bottom-left -rotate-45 transition-colors ${hoveredCell?.j === j ? "text-accent drop-shadow-[0_0_5px_rgba(var(--accent),0.8)] z-30" : "text-text-muted/60 hover:text-text"}`} style={{ whiteSpace: 'nowrap' }}>
                      {sym}
                    </span>
                  </div>
                ))}
                
                {/* Rows */}
                {symbols.map((symRow: string, i: number) => (
                  <div className="contents" key={`row-${i}`}>
                    {/* Row Header */}
                    <div className={`flex items-center justify-end pr-3 h-full text-[10px] font-mono font-bold transition-colors ${hoveredCell?.i === i ? "text-accent drop-shadow-[0_0_5px_rgba(var(--accent),0.8)] z-30" : "text-text-muted/60 hover:text-text"}`}>
                      {symRow}
                    </div>
                    
                    {/* Data Cells */}
                    {symbols.map((symCol: string, j: number) => {
                      const val = matrix[i][j];
                      const secA = assetMap[symRow];
                      const secB = assetMap[symCol];
                      
                      let isSectorMatch = false, isSectorPartial = false, isSectorInactive = false;
                      if (selectedSector !== "all") {
                        if (secA === selectedSector && secB === selectedSector) isSectorMatch = true;
                        else if (secA === selectedSector || secB === selectedSector) isSectorPartial = true;
                        else isSectorInactive = true;
                      }
                      
                      return (
                        <HeatmapCell 
                          key={`cell-${i}-${j}`}
                          i={i} j={j} value={val} symA={symRow} symB={symCol}
                          onEnter={setHoveredCell} onLeave={() => setHoveredCell(null)}
                          isRowActive={hoveredCell?.i === i}
                          isColActive={hoveredCell?.j === j}
                          isSectorMatch={isSectorMatch}
                          isSectorPartial={isSectorPartial}
                          isSectorInactive={isSectorInactive}
                        />
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
            
            <div className="mt-6 flex flex-wrap items-center justify-center gap-8 text-[10px] uppercase font-bold tracking-widest text-text-muted bg-surface/50 glass py-3 px-6 rounded-sm border border-text/5 inline-flex mx-auto">
              <div className="flex items-center gap-3"><div className="w-4 h-4 bg-danger rounded-sm shadow-[0_0_10px_rgba(239,68,68,0.5)]"></div> Inverse (-1.0)</div>
              <div className="flex items-center gap-3"><div className="w-4 h-4 bg-black/40 border border-text/20 rounded-sm"></div> Orthogonal (0.0)</div>
              <div className="flex items-center gap-3"><div className="w-4 h-4 bg-success rounded-sm shadow-[0_0_10px_rgba(34,197,94,0.5)]"></div> Isomorphic (+1.0)</div>
            </div>
          </div>
        </GlassCard>
        
        {/* SECTION 3 - Two Column Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          
          {/* LEFT: Top Correlated Pairs */}
          <GlassCard tier={2} shape="none" className="rounded-xl p-0 overflow-hidden">
            <div className="p-8 border-b border-text/5 bg-surface/30">
              <h3 className="text-xl font-black text-text tracking-tight flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full glass bg-success/10 border border-success/20 flex items-center justify-center">
                      <Zap className="text-success" size={16} />
                  </div>
                  High-Affinity Vectors
              </h3>
              <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-2">Nodes exhibiting maximum co-movement</p>
            </div>
            
            <div className="p-4">
              <div className="overflow-x-auto custom-scrollbar">
                <table className="w-full text-sm text-left">
                  <thead className="text-[9px] text-text-muted uppercase tracking-widest border-b border-text/5">
                    <tr>
                      <th className="px-4 py-3 font-bold">Vector</th>
                      <th className="px-4 py-3 font-bold">Node Alpha</th>
                      <th className="px-4 py-3 font-bold">Node Beta</th>
                      <th className="px-4 py-3 text-right font-bold">Tensor Value</th>
                      <th className="px-4 py-3 text-center font-bold">Topology Class</th>
                    </tr>
                  </thead>
                  <tbody>
                    {top_pairs.map((p: any, idx: number) => {
                      const sameSector = p.sector_a === p.sector_b;
                      return (
                        <tr key={idx} className={`interactive-lift border-b border-text/5 hover:bg-text/[0.02] transition-colors group ${sameSector ? "bg-success/5" : ""}`}>
                          <td className="px-4 py-4 font-mono text-[10px] text-text-muted font-bold">#{String(idx + 1).padStart(2, '0')}</td>
                          <td className="px-4 py-4 font-mono font-black text-text">
                            <Link href={`/graph?asset=${p.symbol_a}`} className="hover:text-accent transition-colors flex items-center gap-2">
                              {p.symbol_a}
                            </Link>
                          </td>
                          <td className="px-4 py-4 font-mono font-black text-text">
                            <Link href={`/graph?asset=${p.symbol_b}`} className="hover:text-accent transition-colors flex items-center gap-2">
                              {p.symbol_b}
                            </Link>
                          </td>
                          <td className={`px-4 py-4 text-right font-mono font-black tracking-tight ${p.correlation > 0 ? "text-success group-hover:drop-shadow-[0_0_5px_rgba(34,197,94,0.5)]" : "text-danger group-hover:drop-shadow-[0_0_5px_rgba(239,68,68,0.5)]"}`}>
                            {p.correlation > 0 ? "+" : ""}{p.correlation.toFixed(4)}
                          </td>
                          <td className="px-4 py-4 text-center">
                            <div className="flex justify-center items-center gap-1.5">
                              <span className="text-[10px] uppercase px-2 py-0.5 shape-tag font-black tracking-widest text-white shadow-inner" style={{ backgroundColor: getSectorColor(p.sector_a) }}>{p.sector_a}</span>
                              <span className="text-[10px] uppercase px-2 py-0.5 shape-tag font-black tracking-widest text-white shadow-inner" style={{ backgroundColor: getSectorColor(p.sector_b) }}>{p.sector_b}</span>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </GlassCard>
          
          {/* RIGHT: Sector Correlation Summary */}
          <GlassCard tier={2} shape="none" className="rounded-xl p-0 flex flex-col overflow-hidden">
            <div className="p-8 border-b border-text/5 bg-surface/30">
              <h3 className="text-xl font-black text-text tracking-tight flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full glass bg-accent/10 border border-accent/20 flex items-center justify-center">
                      <BarChart3 className="text-accent" size={16} />
                  </div>
                  Sub-graph Cohesion
              </h3>
              <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-2">Intra-class topological correlation</p>
            </div>
            
            <div className="h-[350px] w-full p-8 pb-0">
              <ResponsiveContainer width="100%" height={350} minWidth={0} minHeight={0}>
                <BarChart data={sectorBars} layout="vertical" margin={{ left: 20 }}>
                  <XAxis type="number" domain={[0, 1]} stroke={palette.muted} fontSize={10} fontFamily="monospace" tickLine={false} axisLine={false} />
                  <YAxis dataKey="name" type="category" stroke={palette.text} fontSize={10} fontFamily="monospace" tickLine={false} axisLine={false} tickFormatter={(val) => typeof val === 'string' ? val.toUpperCase() : val} />
                  <Tooltip 
                    cursor={{fill: 'rgba(var(--text), 0.05)'}}
                    contentStyle={{ backgroundColor: "rgba(var(--background), 0.9)", borderColor: "rgba(var(--text), 0.1)", borderRadius: "12px", color: palette.text, backdropFilter: "blur(10px)" }} 
                    itemStyle={{ fontFamily: 'monospace', fontWeight: 'bold' }}
                    formatter={(value: any) => [Number(value).toFixed(4), 'Affinity Score']}
                  />
                  <ReferenceLine x={0} stroke={palette.muted} />
                  <Bar 
                    dataKey="value" 
                    radius={[0, 4, 4, 0]}
                    barSize={24}
                  >
                    {
                      sectorBars.map((entry: any, index: number) => (
                        <Cell key={`cell-${index}`} fill={getSectorColor(entry.name)} className="drop-shadow-[0_0_5px_currentColor]" />
                      ))
                    }
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            
            <div className="p-8">
                <div className="p-5 glass bg-accent/5 border border-accent/20 rounded-sm shadow-inner relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-32 h-32 bg-accent/10 rounded-full blur-[40px] pointer-events-none" />
                    <div className="flex items-start gap-3 relative z-10">
                        <Zap size={16} className="text-accent mt-0.5 flex-shrink-0" />
                        <div>
                            <span className="text-[10px] uppercase tracking-widest font-black text-accent block mb-1">Neural Insight</span> 
                            <span className="text-sm text-text-muted leading-relaxed font-light">DeFi protocols display maximal isomorphic alignment due to shared layer-1 collateral vectors. Gaming substrates exhibit orthogonal divergence, indicating idiosyncratic network states.</span>
                        </div>
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

