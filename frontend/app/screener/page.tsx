"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import Link from "next/link";
import { 
  Target, TrendingUp, Zap, Leaf, Building2, RefreshCw, 
  ChevronDown, ChevronUp, Search, Download 
} from "lucide-react";
import { TableSkeleton } from "@/components/PageSkeleton";

const DirectionBadge = ({ direction }: { direction: string }) => {
  const dir = direction?.toLowerCase() || "neutral";
  if (dir === "strong_up") return <span className="bg-green-600 text-white text-[10px] uppercase px-2 py-1 rounded font-bold">STRONG BUY</span>;
  if (dir === "up") return <span className="bg-green-500/20 text-green-400 border border-green-500/30 text-[10px] uppercase px-2 py-1 rounded font-bold">BUY</span>;
  if (dir === "down") return <span className="bg-red-500/20 text-red-400 border border-red-500/30 text-[10px] uppercase px-2 py-1 rounded font-bold">SELL</span>;
  if (dir === "strong_down") return <span className="bg-red-600 text-white text-[10px] uppercase px-2 py-1 rounded font-bold">STRONG SELL</span>;
  return <span className="bg-[#2a2a2a] text-[#94a3b8] text-[10px] uppercase px-2 py-1 rounded font-bold">NEUTRAL</span>;
};

const VolatilityChip = ({ level }: { level: string }) => {
  const v = level?.toLowerCase() || "medium";
  if (v === "extreme") return <span className="bg-purple-900/50 text-purple-400 border border-purple-800 text-[10px] uppercase px-2 py-0.5 rounded">EXTREME</span>;
  if (v === "high") return <span className="bg-orange-900/50 text-orange-400 border border-orange-800 text-[10px] uppercase px-2 py-0.5 rounded">HIGH</span>;
  if (v === "low") return <span className="bg-blue-900/50 text-blue-400 border border-blue-800 text-[10px] uppercase px-2 py-0.5 rounded">LOW</span>;
  return <span className="bg-[#2a2a2a] text-[#94a3b8] text-[10px] uppercase px-2 py-0.5 rounded">MEDIUM</span>;
};

const BASE = "http://localhost:8000";

// A simple hook for debouncing if not centrally available
function useDebounceLocal<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debouncedValue;
}

const PresetCard = ({ icon: Icon, title, desc, onClick }: any) => (
  <button 
    onClick={onClick}
    className="bg-[#1a1a1a] hover:bg-[#2a2a2a] p-4 rounded-xl border border-[#2a2a2a] text-left transition-colors flex items-start gap-4 w-full"
  >
    <div className="bg-indigo-500/20 text-indigo-400 p-3 rounded-lg">
      <Icon size={24} />
    </div>
    <div>
      <h3 className="text-white font-bold mb-1">{title}</h3>
      <p className="text-xs text-[#94a3b8]">{desc}</p>
    </div>
  </button>
);

export default function ScreenerPage() {
  // Filter States
  const [direction, setDirection] = useState("all");
  const [sector, setSector] = useState("all");
  const [volatility, setVolatility] = useState("all");
  const [minConf, setMinConf] = useState(0);
  const [maxConf, setMaxConf] = useState(100);
  const [minRsi, setMinRsi] = useState(0);
  const [maxRsi, setMaxRsi] = useState(100);
  const [minMcap, setMinMcap] = useState(0);
  const [sortBy, setSortBy] = useState("confidence");
  const [sortDir, setSortDir] = useState("desc");
  
  const [filtersOpen, setFiltersOpen] = useState(true);
  
  // Debounce for SWR
  const dMinConf = useDebounceLocal(minConf, 300);
  const dMaxConf = useDebounceLocal(maxConf, 300);
  const dMinRsi = useDebounceLocal(minRsi, 300);
  const dMaxRsi = useDebounceLocal(maxRsi, 300);
  const dMinMcap = useDebounceLocal(minMcap, 300);

  // Build query string
  const query = new URLSearchParams({
    direction,
    sector,
    volatility,
    min_confidence: (dMinConf / 100).toString(),
    max_confidence: (dMaxConf / 100).toString(),
    min_rsi: dMinRsi.toString(),
    max_rsi: dMaxRsi.toString(),
    min_market_cap: dMinMcap.toString(),
    sort_by: sortBy,
    sort_dir: sortDir
  }).toString();

  const { data: results, isLoading } = useSWR(`${BASE}/api/screener/?${query}`, fetcher);

  const applyPreset = (preset: string) => {
    // Reset defaults first
    setDirection("all"); setSector("all"); setVolatility("all");
    setMinConf(0); setMaxConf(100); setMinRsi(0); setMaxRsi(100); setMinMcap(0);
    setSortBy("confidence"); setSortDir("desc");
    
    // Apply specific
    if (preset === "high_confidence_buys") {
      setDirection("strong_up"); // Simplified for UI
      setMinConf(75);
    } else if (preset === "oversold_bounces") {
      setMaxRsi(30);
      setDirection("up");
    } else if (preset === "volatility_breakouts") {
      setDirection("strong_up");
      setVolatility("extreme");
    } else if (preset === "defi_opportunities") {
      setSector("defi");
      setMinConf(60);
      setDirection("up");
    } else if (preset === "large_cap_only") {
      setMinMcap(10000000000);
      setDirection("up");
    } else if (preset === "contrarian_signals") {
      setDirection("strong_up");
      setVolatility("extreme");
    }
  };

  const handleReset = () => {
    setDirection("all"); setSector("all"); setVolatility("all");
    setMinConf(0); setMaxConf(100); setMinRsi(0); setMaxRsi(100); setMinMcap(0);
    setSortBy("confidence"); setSortDir("desc");
  };
  
  const formatMcap = (val: number) => {
    if (val >= 1e12) return `$${(val / 1e12).toFixed(1)}T`;
    if (val >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
    if (val >= 1e6) return `$${(val / 1e6).toFixed(1)}M`;
    return `$${val.toLocaleString()}`;
  };

  const exportCSV = () => {
    if (!results || results.length === 0) return;
    
    const headers = ["Symbol", "Name", "Sector", "Direction", "Confidence", "RSI", "7D Return", "Volatility", "Market Cap"];
    const rows = results.map((r: any) => [
      r.symbol, r.name, r.sector, r.direction, r.confidence, r.rsi_14, r.returns_7d, r.volatility_regime, r.market_cap_usd
    ]);
    
    const csvContent = [
      headers.join(","),
      ...rows.map((row: any) => row.join(","))
    ].join("\n");
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", `screener_export_${new Date().toISOString().slice(0,10)}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      
      {/* HEADER */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white font-mono">Market Scanner</h1>
        <p className="text-sm text-[#94a3b8]">Find opportunities using AI-powered filters</p>
      </div>
      
      {/* SECTION 1 - Presets */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <PresetCard icon={Target} title="High Confidence Buys" desc="ST-GCN predicts up/strong_up with >75% confidence" onClick={() => applyPreset("high_confidence_buys")} />
        <PresetCard icon={TrendingUp} title="Oversold Bounces" desc="RSI below 30 with bullish prediction — potential reversals" onClick={() => applyPreset("oversold_bounces")} />
        <PresetCard icon={Zap} title="Volatility Breakouts" desc="Extreme volatility with strong buy signal — high risk/reward" onClick={() => applyPreset("volatility_breakouts")} />
        <PresetCard icon={Leaf} title="DeFi Opportunities" desc="DeFi sector assets with bullish signals" onClick={() => applyPreset("defi_opportunities")} />
        <PresetCard icon={Building2} title="Large Cap Only" desc="Market cap >$10B — lower risk signals" onClick={() => applyPreset("large_cap_only")} />
        <PresetCard icon={RefreshCw} title="Contrarian Signals" desc="Extreme volatility buy signals — against the trend" onClick={() => applyPreset("contrarian_signals")} />
      </div>
      
      {/* SECTION 2 - Filters */}
      <div className="bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] overflow-hidden">
        <div 
          className="p-4 bg-[#232323] flex justify-between items-center cursor-pointer hover:bg-[#2a2a2a] transition-colors"
          onClick={() => setFiltersOpen(!filtersOpen)}
        >
          <h2 className="text-white font-bold flex items-center gap-2">
            Advanced Filters
          </h2>
          {filtersOpen ? <ChevronUp className="text-[#94a3b8]" /> : <ChevronDown className="text-[#94a3b8]" />}
        </div>
        
        {filtersOpen && (
          <div className="p-6 grid grid-cols-1 md:grid-cols-3 gap-8">
            
            {/* Column 1 */}
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-[#94a3b8] uppercase mb-1">Direction</label>
                <select className="w-full bg-[#0f0f0f] text-white p-2 rounded-md border border-[#2a2a2a]" value={direction} onChange={e => setDirection(e.target.value)}>
                  <option value="all">All Directions</option>
                  <option value="strong_up">Strong Buy</option>
                  <option value="up">Buy</option>
                  <option value="neutral">Neutral</option>
                  <option value="down">Sell</option>
                  <option value="strong_down">Strong Sell</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-[#94a3b8] uppercase mb-1">Sector</label>
                <select className="w-full bg-[#0f0f0f] text-white p-2 rounded-md border border-[#2a2a2a]" value={sector} onChange={e => setSector(e.target.value)}>
                  <option value="all">All Sectors</option>
                  <option value="layer1">Layer 1</option>
                  <option value="defi">DeFi</option>
                  <option value="exchange">Exchange</option>
                  <option value="payment">Payment</option>
                  <option value="gaming">Gaming</option>
                  <option value="privacy">Privacy</option>
                  <option value="storage">Storage</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-[#94a3b8] uppercase mb-1">Volatility</label>
                <select className="w-full bg-[#0f0f0f] text-white p-2 rounded-md border border-[#2a2a2a]" value={volatility} onChange={e => setVolatility(e.target.value)}>
                  <option value="all">All</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="extreme">Extreme</option>
                </select>
              </div>
            </div>
            
            {/* Column 2 */}
            <div className="space-y-4">
              <div>
                <div className="flex justify-between items-end mb-1">
                  <label className="block text-xs font-bold text-[#94a3b8] uppercase">Min Confidence</label>
                  <span className="text-xs text-indigo-400 font-mono">{minConf}%</span>
                </div>
                <input type="range" min="0" max="100" value={minConf} onChange={e => setMinConf(Number(e.target.value))} className="w-full accent-indigo-500" />
              </div>
              <div>
                <div className="flex justify-between items-end mb-1">
                  <label className="block text-xs font-bold text-[#94a3b8] uppercase">Max Confidence</label>
                  <span className="text-xs text-indigo-400 font-mono">{maxConf}%</span>
                </div>
                <input type="range" min="0" max="100" value={maxConf} onChange={e => setMaxConf(Number(e.target.value))} className="w-full accent-indigo-500" />
              </div>
              <div>
                <label className="block text-xs font-bold text-[#94a3b8] uppercase mb-1">Sort By</label>
                <select className="w-full bg-[#0f0f0f] text-white p-2 rounded-md border border-[#2a2a2a]" value={sortBy} onChange={e => setSortBy(e.target.value)}>
                  <option value="confidence">Confidence</option>
                  <option value="market_cap_usd">Market Cap</option>
                  <option value="returns_1d">24h Return</option>
                  <option value="returns_7d">7d Return</option>
                  <option value="rsi_14">RSI</option>
                  <option value="volatility_7d">Volatility</option>
                </select>
              </div>
            </div>
            
            {/* Column 3 */}
            <div className="space-y-4 flex flex-col h-full">
              <div>
                <div className="flex justify-between items-end mb-1">
                  <label className="block text-xs font-bold text-[#94a3b8] uppercase">RSI Range</label>
                  <span className="text-xs text-[#94a3b8] font-mono">{minRsi} - {maxRsi}</span>
                </div>
                <div className="flex gap-2">
                  <input type="range" min="0" max="100" value={minRsi} onChange={e => setMinRsi(Math.min(Number(e.target.value), maxRsi))} className="w-1/2 accent-indigo-500" />
                  <input type="range" min="0" max="100" value={maxRsi} onChange={e => setMaxRsi(Math.max(Number(e.target.value), minRsi))} className="w-1/2 accent-indigo-500" />
                </div>
                <div className="flex justify-between text-[10px] mt-1 uppercase text-[#64748b]">
                  <span className="text-green-500">&lt;30 Oversold</span>
                  <span>Normal</span>
                  <span className="text-red-500">&gt;70 Overbought</span>
                </div>
              </div>
              
              <div className="mt-2">
                <label className="block text-xs font-bold text-[#94a3b8] uppercase mb-1">Sort Direction</label>
                <div className="flex bg-[#0f0f0f] rounded-md border border-[#2a2a2a] overflow-hidden">
                  <button onClick={() => setSortDir("asc")} className={`flex-1 py-1.5 text-xs font-bold transition-colors ${sortDir === "asc" ? "bg-indigo-600 text-white" : "text-[#94a3b8] hover:text-white"}`}>↑ Asc</button>
                  <button onClick={() => setSortDir("desc")} className={`flex-1 py-1.5 text-xs font-bold transition-colors ${sortDir === "desc" ? "bg-indigo-600 text-white" : "text-[#94a3b8] hover:text-white"}`}>↓ Desc</button>
                </div>
              </div>
              
              <div className="mt-auto pt-4">
                <button onClick={handleReset} className="w-full py-2 bg-[#2a2a2a] hover:bg-[#3a3a3a] text-white font-bold rounded-md transition-colors text-sm">
                  Reset Filters
                </button>
              </div>
            </div>
            
          </div>
        )}
      </div>
      
      {/* SECTION 3 - Results Table */}
      <div className="bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] overflow-hidden">
        <div className="p-4 border-b border-[#2a2a2a] flex justify-between items-center bg-[#232323]">
          <h2 className="text-white font-bold">
            Showing {results ? results.length : "..."} assets
          </h2>
          <button onClick={exportCSV} className="flex items-center gap-2 text-sm text-indigo-400 hover:text-indigo-300 transition-colors bg-indigo-500/10 px-3 py-1.5 rounded-md border border-indigo-500/30">
            <Download size={16} /> Export CSV
          </button>
        </div>
        
        {isLoading ? (
          <div className="p-6">
            <TableSkeleton rows={15} />
          </div>
        ) : results && results.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-[10px] text-[#94a3b8] uppercase bg-[#0f0f0f]">
                <tr>
                  <th className="px-4 py-3">Asset</th>
                  <th className="px-4 py-3">Direction</th>
                  <th className="px-4 py-3">Confidence</th>
                  <th className="px-4 py-3">RSI (14d)</th>
                  <th className="px-4 py-3">7D Return</th>
                  <th className="px-4 py-3">Volatility</th>
                  <th className="px-4 py-3 text-right">Market Cap</th>
                  <th className="px-4 py-3 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#2a2a2a]/50">
                {results.map((row: any, i: number) => (
                  <tr key={i} className="hover:bg-[#2a2a2a]/30 transition-colors">
                    <td className="px-4 py-3">
                      <Link href={`/coin/${row.symbol}`} className="flex items-center gap-2 group">
                        <span className="font-bold font-mono text-white group-hover:text-indigo-400">{row.symbol}</span>
                        <span className="text-[9px] uppercase bg-[#2a2a2a] text-[#cbd5e1] px-1.5 py-0.5 rounded">{row.sector}</span>
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <DirectionBadge direction={row.direction} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1 w-32">
                        <span className="text-xs text-white font-mono">{(row.confidence * 100).toFixed(0)}%</span>
                        <div className="w-full bg-[#2a2a2a] h-1.5 rounded-full overflow-hidden">
                          <div className="bg-indigo-500 h-full" style={{ width: `${row.confidence * 100}%` }}></div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono">
                      <div className="flex items-center gap-2">
                        <span className="text-white">{row.rsi_14?.toFixed(1) || 'N/A'}</span>
                        {row.rsi_14 < 30 && <span className="text-[9px] bg-green-900/50 text-green-400 px-1 py-0.5 rounded border border-green-800">OVERSOLD</span>}
                        {row.rsi_14 > 70 && <span className="text-[9px] bg-red-900/50 text-red-400 px-1 py-0.5 rounded border border-red-800">OVERBOUGHT</span>}
                      </div>
                    </td>
                    <td className={`px-4 py-3 font-mono font-bold ${row.returns_7d > 0 ? "text-green-400" : "text-red-400"}`}>
                      {row.returns_7d > 0 ? "+" : ""}{(row.returns_7d * 100).toFixed(2)}%
                    </td>
                    <td className="px-4 py-3">
                      <VolatilityChip level={row.volatility_regime} />
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-[#cbd5e1]">
                      {formatMcap(row.market_cap_usd)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-center gap-2">
                        <Link href={`/coin/${row.symbol}`} className="text-xs bg-[#2a2a2a] hover:bg-[#3a3a3a] text-white px-3 py-1.5 rounded transition-colors font-bold border border-[#3a3a3a]">
                          View
                        </Link>
                        <Link href={`/predictions`} className="text-xs bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 px-3 py-1.5 rounded transition-colors font-bold border border-indigo-500/30">
                          Forecast
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-16 flex flex-col items-center justify-center text-center">
            <div className="bg-[#2a2a2a] p-4 rounded-full mb-4">
              <Search size={32} className="text-[#94a3b8]" />
            </div>
            <h3 className="text-lg font-bold text-white mb-1">No assets match your filters</h3>
            <p className="text-[#94a3b8] mb-6">Try relaxing the confidence or direction filters</p>
            <button onClick={handleReset} className="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2 rounded-lg font-bold transition-colors">
              Reset Filters
            </button>
          </div>
        )}
      </div>
      
    </div>
  );
}
