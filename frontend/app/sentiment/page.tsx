"use client";

import { useMemo } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { AreaChart, Area, ComposedChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from "recharts";
import Link from "next/link";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { ChartSkeleton, StatCardSkeleton } from "@/components/PageSkeleton";

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

// --- SVG Gauge Component ---
const FearGreedGauge = ({ value }: { value: number }) => {
  // Convert 0-100 to rotation (-90 to +90 degrees)
  const clampedValue = Math.max(0, Math.min(100, value));
  const rotation = (clampedValue / 100) * 180 - 90;
  
  // Zones: Extreme Fear (0-24), Fear (25-44), Neutral (45-55), Greed (56-74), Extreme Greed (75-100)
  let zoneLabel = "Neutral";
  let zoneColor = "#94a3b8"; // Neutral
  if (clampedValue <= 24) { zoneLabel = "Extreme Fear"; zoneColor = "#991b1b"; }
  else if (clampedValue <= 44) { zoneLabel = "Fear"; zoneColor = "#ef4444"; }
  else if (clampedValue <= 55) { zoneLabel = "Neutral"; zoneColor = "#94a3b8"; }
  else if (clampedValue <= 74) { zoneLabel = "Greed"; zoneColor = "#22c55e"; }
  else { zoneLabel = "Extreme Greed"; zoneColor = "#14532d"; }

  // SVG Geometry
  const width = 320;
  const height = 180;
  const cx = width / 2;
  const cy = height - 20; // needle pivot
  const r = 120; // radius
  
  // Arc helper
  const describeArc = (startAngle: number, endAngle: number) => {
    // Math angles: 0 is right, 180 is left. SVG starts at right and goes down? 
    // We want 180 to 0 (left to right)
    // Angles in radians for SVG standard math. 
    // Wait, simpler to use stroke-dasharray on a circle.
    // 2 * pi * r = circumference
    return "";
  };

  // Even simpler SVG arcs:
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
  const offset1 = circ; // starts at left
  const offset2 = circ - p1;
  const offset3 = circ - p1 - p2;
  const offset4 = circ - p1 - p2 - p3;
  const offset5 = circ - p1 - p2 - p3 - p4;

  return (
    <div className="flex flex-col items-center">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {/* Base circle for path, rotated so it starts from left (180 deg) and goes to right */}
        <g transform={`rotate(180, ${cx}, ${cy})`}>
          {/* Extreme Greed */}
          <circle cx={cx} cy={cy} r={r} fill="transparent" stroke="#14532d" strokeWidth="24" strokeDasharray={`${p5} ${circ}`} strokeDashoffset={offset5} />
          {/* Greed */}
          <circle cx={cx} cy={cy} r={r} fill="transparent" stroke="#22c55e" strokeWidth="24" strokeDasharray={`${p4} ${circ}`} strokeDashoffset={offset4} />
          {/* Neutral */}
          <circle cx={cx} cy={cy} r={r} fill="transparent" stroke="#94a3b8" strokeWidth="24" strokeDasharray={`${p3} ${circ}`} strokeDashoffset={offset3} />
          {/* Fear */}
          <circle cx={cx} cy={cy} r={r} fill="transparent" stroke="#ef4444" strokeWidth="24" strokeDasharray={`${p2} ${circ}`} strokeDashoffset={offset2} />
          {/* Extreme Fear */}
          <circle cx={cx} cy={cy} r={r} fill="transparent" stroke="#991b1b" strokeWidth="24" strokeDasharray={`${p1} ${circ}`} strokeDashoffset={offset1} />
        </g>
        
        {/* Needle Group */}
        <g transform={`translate(${cx}, ${cy}) rotate(${rotation})`}>
          {/* Needle base */}
          <circle cx="0" cy="0" r="8" fill="#fff" />
          {/* Needle pointer */}
          <polygon points="-4,0 4,0 0,-100" fill="#fff" />
        </g>
        
        {/* Text */}
        <text x={cx} y={cy - 30} textAnchor="middle" fill="#fff" fontSize="48" fontWeight="bold" fontFamily="monospace">
          {Math.round(value)}
        </text>
        <text x={cx} y={cy + 15} textAnchor="middle" fill={zoneColor} fontSize="18" fontWeight="bold">
          {zoneLabel}
        </text>
      </svg>
    </div>
  );
};

export default function SentimentPage() {
  // SWR fetches
  const { data: fgHistory } = useSWR(`${BASE}/api/sentiment-data/fear-greed-history?days=365`, fetcher);
  const { data: btcHistory } = useSWR(`${BASE}/api/sentiment-data/fear-greed-vs-btc?days=365`, fetcher);
  const { data: sectorSent } = useSWR(`${BASE}/api/sentiment-data/sector-sentiment`, fetcher);
  const { data: trending } = useSWR(`${BASE}/api/sentiment-data/trending`, fetcher);

  if (!fgHistory || !btcHistory || !sectorSent || !trending) {
    return (
      <div className="space-y-6">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white font-mono">Market Sentiment Analysis</h1>
          <p className="text-sm text-[#94a3b8]">Loading sentiment data...</p>
        </div>
        <ChartSkeleton height={400} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <StatCardSkeleton />
          <StatCardSkeleton />
        </div>
      </div>
    );
  }

  // Calculate current, yesterday, 7d avg
  const today = fgHistory[fgHistory.length - 1]?.fear_greed || 50;
  const yesterday = fgHistory.length > 1 ? fgHistory[fgHistory.length - 2]?.fear_greed : today;
  const last7 = fgHistory.slice(-7);
  const avg7 = last7.reduce((sum: number, curr: any) => sum + curr.fear_greed, 0) / (last7.length || 1);

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white font-mono">Market Sentiment Analysis</h1>
        <p className="text-sm text-[#94a3b8]">AI-driven social and market sentiment metrics.</p>
      </div>
      
      {/* SECTION 1 - Large Fear & Greed Gauge */}
      <div className="bg-[#1a1a1a] p-8 rounded-xl border border-[#2a2a2a] flex flex-col items-center justify-center">
        <h3 className="text-xl font-bold text-white font-mono mb-6">Fear & Greed Index</h3>
        
        <FearGreedGauge value={today} />
        
        <div className="flex gap-6 mt-4">
          <div className="text-sm text-[#94a3b8]">
            Yesterday: <span className="font-bold text-white">{yesterday}</span>
          </div>
          <div className="text-sm text-[#94a3b8]">
            7D Avg: <span className="font-bold text-white">{Math.round(avg7)}</span>
          </div>
        </div>
        
        <div className="flex flex-wrap justify-center gap-4 mt-8 text-xs font-mono uppercase">
          <div className="flex items-center gap-2"><div className="w-3 h-3 bg-[#991b1b] rounded-sm"></div> Extreme Fear</div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 bg-[#ef4444] rounded-sm"></div> Fear</div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 bg-[#94a3b8] rounded-sm"></div> Neutral</div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 bg-[#22c55e] rounded-sm"></div> Greed</div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 bg-[#14532d] rounded-sm"></div> Extreme Greed</div>
        </div>
      </div>
      
      {/* SECTION 2 - Fear & Greed History */}
      <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
        <h3 className="text-lg font-bold text-white font-mono mb-6">Fear & Greed Index — Last 12 Months</h3>
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={fgHistory} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="colorFG" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#14532d" stopOpacity={0.8}/>
                  <stop offset="50%" stopColor="#94a3b8" stopOpacity={0.5}/>
                  <stop offset="100%" stopColor="#991b1b" stopOpacity={0.8}/>
                </linearGradient>
              </defs>
              <XAxis dataKey="date" stroke="#4a4a4a" tick={{fill: '#94a3b8', fontSize: 12}} minTickGap={30} />
              <YAxis domain={[0, 100]} stroke="#4a4a4a" tick={{fill: '#94a3b8'}} />
              <Tooltip contentStyle={{ backgroundColor: "#0f0f0f", borderColor: "#2a2a2a", color: "#fff" }} />
              <ReferenceLine y={75} stroke="#22c55e" strokeDasharray="3 3" label={{ position: 'insideTopLeft', value: 'Extreme Greed', fill: '#22c55e', fontSize: 10 }} />
              <ReferenceLine y={25} stroke="#ef4444" strokeDasharray="3 3" label={{ position: 'insideBottomLeft', value: 'Extreme Fear', fill: '#ef4444', fontSize: 10 }} />
              <Area type="monotone" dataKey="fear_greed" stroke="#6366f1" fillOpacity={1} fill="url(#colorFG)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
      
      {/* SECTION 3 - Dual Axis: Fear & Greed vs BTC Price */}
      <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
        <h3 className="text-lg font-bold text-white font-mono mb-1">Fear & Greed vs Bitcoin Price</h3>
        <p className="text-sm text-[#94a3b8] mb-6">High greed historically precedes corrections; extreme fear = buy signal</p>
        
        <div className="h-[320px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={btcHistory} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" stroke="#4a4a4a" tick={{fill: '#94a3b8', fontSize: 12}} minTickGap={30} />
              <YAxis yAxisId="left" domain={['auto', 'auto']} stroke="#ffffff" tick={{fill: '#ffffff'}} tickFormatter={(v) => `$${v.toLocaleString()}`} />
              <YAxis yAxisId="right" orientation="right" domain={[0, 100]} stroke="#6366f1" tick={{fill: '#6366f1'}} />
              <Tooltip 
                contentStyle={{ backgroundColor: "#0f0f0f", borderColor: "#2a2a2a", color: "#fff" }} 
                formatter={(val: number, name: string) => [name === 'btc_price' ? `$${val.toLocaleString()}` : val, name === 'btc_price' ? 'BTC Price' : 'Fear & Greed']}
              />
              <Area yAxisId="right" type="monotone" dataKey="fear_greed" fill="#6366f1" stroke="none" fillOpacity={0.2} />
              <Line yAxisId="left" type="monotone" dataKey="btc_price" stroke="#ffffff" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
      
      {/* SECTION 4 - Two Column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* LEFT: Sentiment by Sector */}
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <h3 className="text-lg font-bold text-white font-mono mb-6">Community Sentiment by Sector</h3>
          
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sectorSent} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <XAxis type="number" domain={[-1, 1]} stroke="#4a4a4a" tick={{fill: '#94a3b8'}} />
                <YAxis dataKey="sector" type="category" stroke="#4a4a4a" tick={{fill: '#94a3b8', fontSize: 12}} tickFormatter={(val) => typeof val === 'string' ? val.toUpperCase() : val} />
                <Tooltip 
                  cursor={{fill: '#2a2a2a'}} 
                  contentStyle={{ backgroundColor: "#0f0f0f", borderColor: "#2a2a2a", color: "#fff" }}
                  formatter={(v: number, n: string, props: any) => [`${v.toFixed(3)} (${props.payload.asset_count} assets)`, 'Avg Sentiment']}
                />
                <ReferenceLine x={0} stroke="#4a4a4a" />
                <Bar dataKey="avg_sentiment" radius={[0, 4, 4, 0]}>
                  {
                    sectorSent.map((entry: any, index: number) => (
                      <Cell key={`cell-${index}`} fill={entry.avg_sentiment >= 0 ? '#22c55e' : '#ef4444'} />
                    ))
                  }
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        
        {/* RIGHT: Trending Assets */}
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a] flex flex-col">
          <h3 className="text-lg font-bold text-white font-mono mb-6">Sentiment Movers</h3>
          
          <div className="flex-1 space-y-6">
            <div>
              <div className="flex items-center gap-2 mb-3 text-green-400 font-bold">
                <TrendingUp size={18} />
                <h4>Rising Sentiment (7d)</h4>
              </div>
              <div className="space-y-2">
                {trending.gainers.map((g: any, i: number) => (
                  <div key={i} className="flex justify-between items-center bg-[#0f0f0f] p-3 rounded-lg border border-[#2a2a2a]">
                    <div className="flex items-center gap-3">
                      <Link href={`/coin/${g.symbol}`} className="font-mono font-bold text-white hover:text-indigo-400">{g.symbol}</Link>
                      <span className="text-[10px] uppercase bg-[#2a2a2a] text-[#cbd5e1] px-1.5 py-0.5 rounded" style={{ backgroundColor: getSectorColor(g.sector) }}>{g.sector}</span>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-green-400">+{g.change.toFixed(3)}</div>
                      <div className="text-xs text-[#94a3b8]">{g.prev_sentiment.toFixed(2)} → {g.current_sentiment.toFixed(2)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            
            <div>
              <div className="flex items-center gap-2 mb-3 text-red-400 font-bold">
                <TrendingDown size={18} />
                <h4>Falling Sentiment (7d)</h4>
              </div>
              <div className="space-y-2">
                {trending.losers.map((l: any, i: number) => (
                  <div key={i} className="flex justify-between items-center bg-[#0f0f0f] p-3 rounded-lg border border-[#2a2a2a]">
                    <div className="flex items-center gap-3">
                      <Link href={`/coin/${l.symbol}`} className="font-mono font-bold text-white hover:text-indigo-400">{l.symbol}</Link>
                      <span className="text-[10px] uppercase text-[#cbd5e1] px-1.5 py-0.5 rounded" style={{ backgroundColor: getSectorColor(l.sector) }}>{l.sector}</span>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-red-400">{l.change.toFixed(3)}</div>
                      <div className="text-xs text-[#94a3b8]">{l.prev_sentiment.toFixed(2)} → {l.current_sentiment.toFixed(2)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          
        </div>
      </div>
      
    </div>
  );
}
