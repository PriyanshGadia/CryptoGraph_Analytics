"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from "recharts";
import Link from "next/link";
import { ChartSkeleton } from "@/components/PageSkeleton";
import { ScrollToTop } from "@/components/ScrollToTop";

const BASE = "http://localhost:8000";

// --- Sector Color Mapping ---
const getSectorColor = (sector: string) => {
  const colors: Record<string, string> = {
    layer1: "#3b82f6",
    defi: "#8b5cf6",
    exchange: "#f59e0b",
    payment: "#10b981",
    gaming: "#ec4899",
    privacy: "#6366f1",
    storage: "#14b8a6",
    other: "#94a3b8"
  };
  return colors[sector?.toLowerCase()] || colors.other;
};

// --- Heatmap Cell Component (Memoized) ---
import { memo } from "react";
const HeatmapCell = memo(({ 
  i, j, value, symA, symB, onEnter, onLeave, isRowActive, isColActive, isSectorMatch, isSectorPartial, isSectorInactive 
}: any) => {
  
  // Interpolate color from -1 to 1
  let bgColor = "#1a1a1a";
  if (i === j) {
    bgColor = "#6366f1"; // self-correlation
  } else if (value > 0) {
    // Green scale
    const intensity = Math.min(value, 1);
    bgColor = `rgba(34, 197, 94, ${intensity * 0.8 + 0.1})`; // From faint green to solid #22c55e
  } else if (value < 0) {
    // Red scale
    const intensity = Math.min(Math.abs(value), 1);
    bgColor = `rgba(239, 68, 68, ${intensity * 0.8 + 0.1})`; // From faint red to solid #ef4444
  }
  
  let classes = "w-full h-full transition-all ";
  
  if (isSectorMatch) {
    classes += "ring-1 ring-white z-10 ";
  } else if (isSectorInactive) {
    classes += "opacity-30 grayscale ";
  } else if (isSectorPartial) {
    classes += "opacity-80 ";
  }
  
  if (isRowActive || isColActive) {
    classes += "ring-1 ring-white/50 z-20 ";
  }

  return (
    <div 
      className={classes}
      style={{ backgroundColor: bgColor }}
      onMouseEnter={() => onEnter(i, j, value, symA, symB)}
      onMouseLeave={onLeave}
    />
  );
});
HeatmapCell.displayName = "HeatmapCell";

export default function CorrelationsPage() {
  const [days, setDays] = useState(30);
  const [selectedSector, setSelectedSector] = useState("all");
  const [cellSize, setCellSize] = useState(14);
  
  // Hover state
  const [hoveredCell, setHoveredCell] = useState<{i: number, j: number, val: number, symA: string, symB: string} | null>(null);

  const { data: matrixData, isLoading: matrixLoading } = useSWR(`${BASE}/api/correlations/matrix?days=${days}`, fetcher);
  const { data: sectorData, isLoading: sectorLoading } = useSWR(`${BASE}/api/correlations/sector-average?days=${days}`, fetcher);
  const { data: assetsData } = useSWR(`${BASE}/api/assets`, fetcher);
  
  const assetMap = useMemo(() => {
    if (!assetsData) return {};
    const map: Record<string, string> = {};
    assetsData.forEach((a: any) => map[a.symbol] = a.sector);
    return map;
  }, [assetsData]);

  if (matrixLoading || sectorLoading) return (
    <div className="space-y-6">
      <div className="flex justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white font-mono">Correlation Analysis</h1>
          <p className="text-sm text-[#94a3b8]">Loading correlation matrices...</p>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ChartSkeleton height={100} />
        <ChartSkeleton height={100} />
        <ChartSkeleton height={100} />
      </div>
      <ChartSkeleton height={600} />
    </div>
  );
  
  if (!matrixData || !sectorData) return <div className="p-8 text-red-400">Failed to load data.</div>;

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
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white font-mono">Correlation Analysis</h1>
          <p className="text-sm text-[#94a3b8]">How strongly do crypto assets move together?</p>
        </div>
        
        <div className="flex items-center gap-4">
          <select 
            value={selectedSector}
            onChange={(e) => setSelectedSector(e.target.value)}
            className="bg-[#1a1a1a] text-sm text-white font-bold px-3 py-1.5 rounded-lg border border-[#2a2a2a] focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Sectors</option>
            {sectorsList.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          
          <div className="flex bg-[#1a1a1a] rounded-lg border border-[#2a2a2a] p-1">
            {[7, 30, 90, 365].map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1 rounded-md text-sm font-bold transition-colors ${
                  days === d ? "bg-indigo-600 text-white" : "text-[#94a3b8] hover:text-white"
                }`}
              >
                {d === 365 ? "1Y" : `${d}D`}
              </button>
            ))}
          </div>
        </div>
      </div>
      
      {/* SECTION 1 - Header Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <div className="text-sm text-[#94a3b8] mb-2 font-mono">Assets Analyzed</div>
          <div className="text-3xl font-bold font-mono text-white">{symbols.length}</div>
        </div>
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <div className="text-sm text-[#94a3b8] mb-2 font-mono">Avg Correlation</div>
          <div className="text-3xl font-bold font-mono text-indigo-400">{avgCorr.toFixed(2)}</div>
        </div>
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <div className="text-sm text-[#94a3b8] mb-2 font-mono">Highest Pair</div>
          <div className="text-3xl font-bold font-mono text-green-400">
            {top_pairs[0]?.symbol_a}/{top_pairs[0]?.symbol_b} <span className="text-xl">({top_pairs[0]?.correlation.toFixed(2)})</span>
          </div>
        </div>
      </div>
      
      {/* SECTION 2 - 50x50 Correlation Heatmap */}
      <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a] relative">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-bold text-white font-mono">Asset Correlation Heatmap</h3>
          
          <div className="flex items-center gap-3">
            <span className="text-xs text-[#94a3b8]">Zoom:</span>
            <input 
              type="range" 
              min="10" 
              max="24" 
              value={cellSize} 
              onChange={(e) => setCellSize(Number(e.target.value))}
              className="w-24 accent-indigo-500"
            />
          </div>
        </div>
        
        {hoveredCell && (
          <div className="absolute top-6 right-6 bg-[#0f0f0f] border border-indigo-500/50 rounded-lg p-3 shadow-xl z-50 flex flex-col items-center">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono font-bold text-white">{hoveredCell.symA}</span>
              <span className="text-[#94a3b8]">↔</span>
              <span className="font-mono font-bold text-white">{hoveredCell.symB}</span>
            </div>
            <div className={`text-xl font-bold font-mono ${(hoveredCell.val || 0) > 0 ? "text-green-400" : "text-red-400"}`}>
              {(hoveredCell.val || 0) > 0 ? "+" : ""}{(hoveredCell.val || 0).toFixed(3)}
            </div>
          </div>
        )}
        
        <div className="overflow-auto custom-scrollbar border border-[#2a2a2a] bg-[#0f0f0f] p-4 rounded-lg">
          <div 
            style={{ 
              display: 'grid', 
              gridTemplateColumns: `auto repeat(${n}, ${cellSize}px)`,
              gridAutoRows: `${cellSize}px`,
              gap: '1px'
            }}
          >
            {/* Top-left empty cell */}
            <div />
            
            {/* Top headers */}
            {symbols.map((sym: string, j: number) => (
              <div key={`col-${j}`} className="flex items-end justify-center h-full pb-1 overflow-visible relative">
                <span className="text-[9px] font-mono text-[#94a3b8] absolute bottom-1 origin-bottom-left -rotate-45" style={{ whiteSpace: 'nowrap' }}>
                  {sym}
                </span>
              </div>
            ))}
            
            {/* Rows */}
            {symbols.map((symRow: string, i: number) => (
              <div className="contents" key={`row-${i}`}>
                {/* Row Header */}
                <div className="flex items-center justify-end pr-2 h-full text-[9px] font-mono text-[#94a3b8]">
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
        
        <div className="mt-4 flex items-center justify-center gap-6 text-xs font-mono text-[#94a3b8]">
          <div className="flex items-center gap-2"><div className="w-3 h-3 bg-red-600 rounded-sm"></div> -1.0</div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 bg-[#1a1a1a] border border-[#4a4a4a] rounded-sm"></div> 0.0</div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 bg-green-500 rounded-sm"></div> +1.0</div>
        </div>
      </div>
      
      {/* SECTION 3 - Two Column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* LEFT: Top Correlated Pairs */}
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <h3 className="text-lg font-bold text-white font-mono">Most Correlated Pairs</h3>
          <p className="text-xs text-[#94a3b8] mb-4">Assets that move most similarly</p>
          
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-[10px] text-[#94a3b8] uppercase bg-[#0f0f0f] border-b border-[#2a2a2a]">
                <tr>
                  <th className="px-3 py-2">Rank</th>
                  <th className="px-3 py-2">Asset A</th>
                  <th className="px-3 py-2">Asset B</th>
                  <th className="px-3 py-2 text-right">Correlation</th>
                  <th className="px-3 py-2 text-center">Sectors</th>
                </tr>
              </thead>
              <tbody>
                {top_pairs.map((p: any, idx: number) => {
                  const sameSector = p.sector_a === p.sector_b;
                  return (
                    <tr key={idx} className={`border-b border-[#2a2a2a]/50 hover:bg-[#2a2a2a]/50 transition-colors ${sameSector ? "bg-green-900/10" : ""}`}>
                      <td className="px-3 py-3 font-mono text-[#64748b]">#{idx + 1}</td>
                      <td className="px-3 py-3 font-mono font-bold text-white">
                        <Link href={`/coin/${p.symbol_a}`} className="hover:text-indigo-400">{p.symbol_a}</Link>
                      </td>
                      <td className="px-3 py-3 font-mono font-bold text-white">
                        <Link href={`/coin/${p.symbol_b}`} className="hover:text-indigo-400">{p.symbol_b}</Link>
                      </td>
                      <td className={`px-3 py-3 text-right font-mono font-bold ${p.correlation > 0 ? "text-green-400" : "text-red-400"}`}>
                        {p.correlation > 0 ? "+" : ""}{p.correlation.toFixed(3)}
                      </td>
                      <td className="px-3 py-3 text-center">
                        <div className="flex justify-center items-center gap-1">
                          <span className="text-[9px] uppercase px-1 py-0.5 rounded text-white" style={{ backgroundColor: getSectorColor(p.sector_a) }}>{p.sector_a}</span>
                          <span className="text-[9px] uppercase px-1 py-0.5 rounded text-white" style={{ backgroundColor: getSectorColor(p.sector_b) }}>{p.sector_b}</span>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
        
        {/* RIGHT: Sector Correlation Summary */}
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a] flex flex-col">
          <h3 className="text-lg font-bold text-white font-mono">Average Intra-Sector Correlation</h3>
          <p className="text-xs text-[#94a3b8] mb-6">How much do assets within each sector move together?</p>
          
          <div className="flex-1 min-h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sectorBars} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" domain={[0, 1]} stroke="#4a4a4a" tick={{fill: '#94a3b8'}} />
                <YAxis dataKey="name" type="category" stroke="#4a4a4a" tick={{fill: '#94a3b8', fontSize: 12}} tickFormatter={(val) => typeof val === 'string' ? val.toUpperCase() : val} />
                <Tooltip 
                  cursor={{fill: '#2a2a2a'}} 
                  contentStyle={{ backgroundColor: "#0f0f0f", borderColor: "#2a2a2a", color: "#fff" }} 
                  formatter={(value: number) => [value.toFixed(3), 'Avg Correlation']}
                />
                <ReferenceLine x={0} stroke="#4a4a4a" />
                <Bar 
                  dataKey="value" 
                  radius={[0, 4, 4, 0]}
                >
                  {
                    sectorBars.map((entry: any, index: number) => (
                      <Cell key={`cell-${index}`} fill={getSectorColor(entry.name)} />
                    ))
                  }
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          
          <div className="mt-6 p-4 bg-[#0f0f0f] border border-[#2a2a2a] rounded-lg text-sm text-[#94a3b8]">
            <span className="text-indigo-400 font-bold">Insight:</span> DeFi tokens often move together because they share Ethereum gas costs and protocol risks. Layer 1 chains correlate due to a shared investor base. Gaming tokens are often less correlated, driven by individual game success and separate ecosystems.
          </div>
        </div>
        
      </div>
      <ScrollToTop />
    </div>
  );
}
