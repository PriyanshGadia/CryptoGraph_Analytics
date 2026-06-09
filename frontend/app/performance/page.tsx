"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { ComposedChart, Area, Line, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import Link from "next/link";
import { ChartSkeleton, StatCardSkeleton } from "@/components/PageSkeleton";
import { ScrollToTop } from "@/components/ScrollToTop";

const BASE = "http://localhost:8000";

function DirectionBadge({ dir }: { dir: string }) {
  if (dir === "strong_up") return <span className="px-2 py-0.5 rounded-full bg-green-950 text-green-400 border border-green-800 text-xs">Strong Buy</span>;
  if (dir === "up") return <span className="px-2 py-0.5 rounded-full bg-green-900/50 text-green-300 border border-green-700/50 text-xs">Buy</span>;
  if (dir === "strong_down") return <span className="px-2 py-0.5 rounded-full bg-red-950 text-red-400 border border-red-800 text-xs">Strong Sell</span>;
  if (dir === "down") return <span className="px-2 py-0.5 rounded-full bg-red-900/50 text-red-300 border border-red-700/50 text-xs">Sell</span>;
  return <span className="px-2 py-0.5 rounded-full bg-[#1a1a1a] text-gray-400 border border-gray-700 text-xs">Neutral</span>;
}

export default function PerformancePage() {
  const [days, setDays] = useState(30);
  const [search, setSearch] = useState("");
  const [showAll, setShowAll] = useState(false);
  
  const { data, isLoading } = useSWR(`${BASE}/api/performance?days=${days}`, fetcher);
  
  if (isLoading) return (
    <div className="space-y-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-white font-mono">Model Performance Tracker</h1>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
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
  if (!data) return <div className="p-8 text-red-400">Error loading metrics.</div>;
  
  const overallAcc = data.overall_accuracy * 100;
  const accColor = overallAcc > 55 ? "text-green-400" : overallAcc > 45 ? "text-amber-400" : "text-red-400";
  
  const stratRet = data.strategy_return_pct;
  const retColor = stratRet > 0 ? "text-green-400" : "text-red-400";
  
  const sharpe = data.strategy_sharpe;
  const sharpeColor = sharpe > 1.0 ? "text-green-400" : sharpe > 0.5 ? "text-amber-400" : "text-red-400";
  
  const assetEntries = Object.entries(data.per_asset_accuracy || {}).map(([sym, stats]: [string, any]) => ({
    symbol: sym,
    ...stats
  })).filter(a => a.symbol.toLowerCase().includes(search.toLowerCase()))
     .sort((a, b) => b.accuracy - a.accuracy);
     
  const visibleAssets = showAll ? assetEntries : assetEntries.slice(0, 20);

  // Confusion matrix max value for color scaling
  let maxVal = 1;
  data.confusion_matrix.forEach((row: number[]) => {
    row.forEach(val => { if (val > maxVal) maxVal = val; });
  });

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-white font-mono">Model Performance Tracker</h1>
        <div className="flex bg-[#1a1a1a] rounded-lg border border-[#2a2a2a] p-1">
          {[7, 30, 90].map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-4 py-1.5 rounded-md text-sm font-bold transition-colors ${
                days === d ? "bg-indigo-600 text-white" : "text-[#94a3b8] hover:text-white"
              }`}
            >
              {d}D
            </button>
          ))}
        </div>
      </div>
      
      {/* SECTION 1 - Hero Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <div className="text-sm text-[#94a3b8] mb-2 font-mono">Overall Accuracy</div>
          <div className={`text-4xl font-bold font-mono ${accColor}`}>
            {overallAcc.toFixed(1)}%
          </div>
        </div>
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <div className="text-sm text-[#94a3b8] mb-2 font-mono">Total Scored</div>
          <div className="text-4xl font-bold font-mono text-white">
            {data.total_scored}
          </div>
        </div>
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <div className="text-sm text-[#94a3b8] mb-2 font-mono">Strategy Return</div>
          <div className={`text-4xl font-bold font-mono ${retColor}`}>
            {stratRet > 0 ? "+" : ""}{stratRet.toFixed(1)}%
          </div>
        </div>
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <div className="text-sm text-[#94a3b8] mb-2 font-mono">Strategy Sharpe</div>
          <div className={`text-4xl font-bold font-mono ${sharpeColor}`}>
            {sharpe.toFixed(2)}
          </div>
        </div>
      </div>
      
      {/* SECTION 2 - Rolling Accuracy */}
      <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
        <h3 className="text-lg font-bold text-white font-mono mb-1">Rolling Prediction Accuracy Over Time</h3>
        <p className="text-sm text-[#94a3b8] mb-6">50% = random baseline — anything above is model skill</p>
        
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data.rolling_accuracy}>
              <XAxis dataKey="date" stroke="#4a4a4a" tick={{fill: '#94a3b8', fontSize: 12}} />
              <YAxis domain={[0, 100]} stroke="#4a4a4a" tick={{fill: '#94a3b8'}} />
              <Tooltip contentStyle={{ backgroundColor: "#0f0f0f", borderColor: "#2a2a2a", color: "#fff" }} />
              <ReferenceLine y={50} stroke="#f59e0b" strokeDasharray="3 3" />
              <Area type="monotone" dataKey="accuracy_7d" fill="#6366f1" stroke="none" fillOpacity={0.1} />
              <Line type="monotone" dataKey="accuracy_7d" stroke="#6366f1" strokeWidth={2} dot={false} name="7-Day Acc" />
              <Line type="monotone" dataKey="accuracy_30d" stroke="#f59e0b" strokeWidth={2} strokeDasharray="5 5" dot={false} name="30-Day Acc" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
      
      {/* SECTION 3 - Matrix & Calibration */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Confusion Matrix */}
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <h3 className="text-lg font-bold text-white font-mono mb-1">Prediction Confusion Matrix</h3>
          <p className="text-sm text-[#94a3b8] mb-6">Rows = predicted, Columns = actual outcome</p>
          
          <div className="grid grid-cols-6 gap-1">
            {/* Header row */}
            <div className="text-[10px] text-center p-1"></div>
            {data.confusion_labels.map((l: string) => (
              <div key={`col-${l}`} className="text-[10px] uppercase text-[#94a3b8] font-mono text-center flex items-center justify-center">
                {l.replace("_", " ")}
              </div>
            ))}
            
            {/* Data rows */}
            {data.confusion_matrix.map((row: number[], i: number) => (
              <div className="contents" key={`row-${i}`}>
                <div className="text-[10px] uppercase text-[#94a3b8] font-mono flex items-center justify-end pr-2 text-right break-words">
                  {data.confusion_labels[i].replace("_", " ")}
                </div>
                {row.map((val: number, j: number) => {
                  const isDiagonal = i === j;
                  const intensity = Math.min(val / maxVal, 1);
                  
                  let bgColor = `rgba(99, 102, 241, ${intensity * 0.8 + 0.1})`; // indigo scale
                  if (isDiagonal) {
                    bgColor = `rgba(34, 197, 94, ${intensity * 0.8 + 0.1})`; // green scale for correct
                  }
                  if (val === 0) bgColor = "#1a1a1a";
                  
                  return (
                    <div 
                      key={`cell-${i}-${j}`} 
                      className="aspect-square flex items-center justify-center rounded text-white text-sm font-bold font-mono cursor-pointer transition-transform hover:scale-105"
                      style={{ backgroundColor: bgColor }}
                      title={`Predicted ${data.confusion_labels[i]}, actually ${data.confusion_labels[j]}: ${val} times`}
                    >
                      {val > 0 ? val : ""}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
        
        {/* Confidence Calibration */}
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <h3 className="text-lg font-bold text-white font-mono mb-1">Confidence Calibration</h3>
          <p className="text-sm text-[#94a3b8] mb-6">When the model says 80% confident, is it right 80% of the time?</p>
          
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data.confidence_calibration}>
                <XAxis dataKey="confidence_range" stroke="#4a4a4a" tick={{fill: '#94a3b8', fontSize: 10}} angle={-45} textAnchor="end" />
                <YAxis domain={[0, 100]} stroke="#4a4a4a" tick={{fill: '#94a3b8', fontSize: 10}} />
                <Tooltip contentStyle={{ backgroundColor: "#0f0f0f", borderColor: "#2a2a2a", color: "#fff" }} />
                {/* Diagonal line logic: just draw a line from (x=0, y=0) to (x=end, y=100), Recharts ReferenceLine segment works */}
                <Bar dataKey="actual_accuracy" fill="#6366f1" radius={[4, 4, 0, 0]} name="Actual Accuracy" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-[#64748b] mt-4 text-center">
             Bars above the line = model is conservative with confidence (good)<br/>
             Bars below the line = model is overconfident (bad)
          </p>
        </div>
      </div>
      
      {/* SECTION 4 - Per Direction */}
      <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
        <h3 className="text-lg font-bold text-white font-mono mb-4">Accuracy by Predicted Direction</h3>
        <div className="space-y-4">
          {[
            { label: "Strong Buy", key: "strong_up", color: "bg-green-500" },
            { label: "Buy", key: "up", color: "bg-green-400" },
            { label: "Neutral", key: "neutral", color: "bg-gray-500" },
            { label: "Sell", key: "down", color: "bg-red-400" },
            { label: "Strong Sell", key: "strong_down", color: "bg-red-500" },
          ].map(d => {
            const acc = (data.per_direction_accuracy?.[d.key] || 0) * 100;
            return (
              <div key={d.key} className="flex items-center gap-4">
                <div className="w-28 text-right"><DirectionBadge dir={d.key} /></div>
                <div className="flex-1 h-3 bg-[#0f0f0f] rounded-full overflow-hidden relative">
                  <div className="absolute left-[50%] top-0 bottom-0 w-px bg-[#4a4a4a] z-10" />
                  <div className={`h-full ${d.color}`} style={{ width: `${acc}%` }} />
                </div>
                <div className="w-16 text-right font-mono text-white font-bold">{acc.toFixed(0)}%</div>
              </div>
            );
          })}
        </div>
      </div>
      
      {/* SECTION 5 - Per Asset */}
      <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
        <div className="flex justify-between items-center mb-6">
          <h3 className="text-lg font-bold text-white font-mono">Accuracy by Asset</h3>
          <input 
            type="text" 
            placeholder="Search symbol..." 
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-[#0f0f0f] border border-[#2a2a2a] rounded-lg px-3 py-1.5 text-sm text-white placeholder-[#4a4a4a] focus:outline-none focus:border-indigo-500"
          />
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-[#94a3b8] uppercase bg-[#0f0f0f] border-b border-[#2a2a2a]">
              <tr>
                <th className="px-4 py-3">Asset</th>
                <th className="px-4 py-3 text-right">Accuracy</th>
                <th className="px-4 py-3 text-right">Correct</th>
                <th className="px-4 py-3 text-right">Wrong</th>
                <th className="px-4 py-3 text-right">Avg Conf</th>
                <th className="px-4 py-3 text-right">Best Dir</th>
              </tr>
            </thead>
            <tbody>
              {visibleAssets.map(a => {
                const a_acc = a.accuracy * 100;
                const a_color = a_acc >= 60 ? "text-green-400" : a_acc >= 50 ? "text-amber-400" : "text-red-400";
                return (
                  <tr key={a.symbol} className="border-b border-[#2a2a2a]/50 hover:bg-[#2a2a2a]/30">
                    <td className="px-4 py-3 font-mono font-bold text-white">
                      <Link href={`/coin/${a.symbol}`} className="hover:text-indigo-400">{a.symbol}</Link>
                    </td>
                    <td className={`px-4 py-3 text-right font-mono font-bold ${a_color}`}>{a_acc.toFixed(1)}%</td>
                    <td className="px-4 py-3 text-right text-green-400">{a.correct}</td>
                    <td className="px-4 py-3 text-right text-red-400">{a.wrong}</td>
                    <td className="px-4 py-3 text-right text-[#94a3b8]">{(a.avg_confidence * 100).toFixed(1)}%</td>
                    <td className="px-4 py-3 text-right"><DirectionBadge dir={a.best_direction} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        
        {!showAll && assetEntries.length > 20 && (
          <button 
            onClick={() => setShowAll(true)}
            className="w-full mt-4 py-2 border border-[#2a2a2a] rounded-lg text-sm text-[#94a3b8] hover:text-white hover:border-[#4a4a4a] transition-colors"
          >
            Show All
          </button>
        )}
      </div>
      
      <ScrollToTop />
    </div>
  );
}
