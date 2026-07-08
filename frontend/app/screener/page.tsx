"use client";

import { useState, useEffect, useRef } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import Link from "next/link";
import { 
  Target, TrendingUp, Zap, Leaf, Building2, RefreshCw, 
  ChevronDown, ChevronUp, Search, Download, ShieldCheck
} from "lucide-react";
import { TableSkeleton } from "@/components/PageSkeleton";
import { useCurrency, CURRENCY_SYMBOLS } from "@/components/CurrencyContext";
import { GlassCard } from "@/components/ui/GlassCard";
import { DirectionBadge } from "@/components/ui/DirectionBadge";

const VolatilityChip = ({ level }: { level: string }) => {
  const v = level?.toLowerCase() || "medium";
  if (v === "extreme") return <span className="bg-danger/20 text-danger border border-danger/30 text-[9px] uppercase px-2 py-0.5 shape-tag font-black tracking-widest shadow-[0_0_5px_rgba(239,68,68,0.2)]">EXTREME</span>;
  if (v === "high") return <span className="bg-warning/10 text-warning border border-warning/30 text-[9px] uppercase px-2 py-0.5 shape-tag font-bold tracking-widest">HIGH</span>;
  if (v === "low") return <span className="bg-info/10 text-info border border-info/30 text-[9px] uppercase px-2 py-0.5 shape-tag font-bold tracking-widest">LOW</span>;
  return <span className="bg-text/5 text-text-muted border border-text/10 text-[9px] uppercase px-2 py-0.5 shape-tag font-bold tracking-widest">MEDIUM</span>;
};

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
    className="glass-flat shape-ledger interactive-lift hover:bg-text/5 p-5 border border-text/5 hover:border-text/20 text-left transition-all duration-[var(--dur-hover)] ease-glide flex items-start gap-4 w-full group relative overflow-hidden"
  >
    <div className="absolute top-0 left-0 w-full h-1 bg-text/5 group-hover:bg-accent/50 transition-colors" />
    <div className="glass bg-accent/10 text-accent p-3 rounded-sm shadow-inner group-hover:scale-110 transition-transform">
      <Icon size={24} />
    </div>
    <div>
      <h3 className="text-text font-black mb-1 tracking-tight group-hover:text-accent transition-colors">{title}</h3>
      <p className="text-xs text-text-muted font-light">{desc}</p>
    </div>
  </button>
);

export default function ScreenerPage() {
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
  const [liveData, setLiveData] = useState<Record<string, {price: number, volume: number}>>({});
  
  const { currency, formatPrice, exchangeRate } = useCurrency();
  
  const updatesRef = useRef<Record<string, {price: number, volume: number}>>({});
  
  useEffect(() => {
    const ws = new WebSocket(`${BASE.replace("http", "ws")}/api/v1/stream/screener?api_key=${process.env.NEXT_PUBLIC_API_KEY}`);
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === "LIVE_PRICES" && payload.data) {
          Object.assign(updatesRef.current, payload.data);
        }
      } catch (e) {
        console.error(e);
      }
    };
    
    const interval = setInterval(() => {
      if (Object.keys(updatesRef.current).length > 0) {
        setLiveData(prev => ({...prev, ...updatesRef.current}));
        updatesRef.current = {};
      }
    }, 1000);
    
    return () => {
      ws.close();
      clearInterval(interval);
    };
  }, []);
  
  const dMinConf = useDebounceLocal(minConf, 300);
  const dMaxConf = useDebounceLocal(maxConf, 300);
  const dMinRsi = useDebounceLocal(minRsi, 300);
  const dMaxRsi = useDebounceLocal(maxRsi, 300);
  const dMinMcap = useDebounceLocal(minMcap, 300);

  const query = new URLSearchParams({
    direction,
    sector,
    volatility,
    min_confidence: dMinConf.toString(),
    max_confidence: dMaxConf.toString(),
    min_rsi: dMinRsi.toString(),
    max_rsi: dMaxRsi.toString(),
    min_market_cap: dMinMcap.toString(),
    sort_by: sortBy,
    sort_dir: sortDir
  }).toString();

  const { data: results, isLoading, mutate } = useSWR(`${BASE}/api/screener/?${query}`, fetcher);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const refreshLiveTechnicals = async () => {
    setIsRefreshing(true);
    try {
      const res = await fetch(`${BASE}/api/screener/refresh`, { method: "POST" });
      if (res.ok) mutate();
    } catch (err) {
      console.error(err);
    }
    setIsRefreshing(false);
  };

  const applyPreset = (preset: string) => {
    setDirection("all"); setSector("all"); setVolatility("all");
    setMinConf(0); setMaxConf(100); setMinRsi(0); setMaxRsi(100); setMinMcap(0);
    setSortBy("confidence"); setSortDir("desc");
    
    if (preset === "high_confidence_buys") {
      setDirection("strong_up");
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

  const exportCSV = () => {
    if (!results || results.length === 0) return;
    const headers = ["Symbol", "Name", "Sector", "Direction", "Confidence", "RSI", "7D Return", "Volatility", "Market Cap"];
    const rows = results.map((r: any) => [
      r.symbol, r.name, r.sector, r.predicted_direction, r.confidence, r.rsi_14, r.returns_7d, r.volatility_regime, r.market_cap_usd
    ]);
    const escapeCsvField = (field: any) => {
      if (field == null) return "";
      const str = String(field);
      if (str.includes(",") || str.includes('"') || str.includes("\n")) {
        return '"' + str.replace(/"/g, '""') + '"';
      }
      return str;
    };
    const csvContent = "\uFEFF" + [
      headers.map(escapeCsvField).join(","),
      ...rows.map((row: any) => row.map(escapeCsvField).join(","))
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
    <div className="space-y-8 p-8 max-w-[1600px] mx-auto glass-2 shape-seal overflow-hidden relative">
      
      {/* HEADER */}
      <div className="relative">
        <div className="absolute top-[-50px] left-[-50px] w-64 h-64 bg-accent/5 rounded-full blur-[80px] pointer-events-none" />
        <div className="relative z-10">
          <h1 className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted tracking-tight font-sans">Market Scanner</h1>
          <p className="text-text-muted font-light tracking-wide mt-2">Find opportunities using AI-powered filters and neural signals</p>
        </div>
      </div>
      
      {/* SECTION 1 - Presets */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 relative z-10">
        <PresetCard icon={Target} title="High Confidence Buys" desc="ST-GCN predicts up/strong_up with >75% confidence" onClick={() => applyPreset("high_confidence_buys")} />
        <PresetCard icon={TrendingUp} title="Oversold Bounces" desc="RSI below 30 with bullish prediction — potential reversals" onClick={() => applyPreset("oversold_bounces")} />
        <PresetCard icon={Zap} title="Volatility Breakouts" desc="Extreme volatility with strong buy signal — high risk/reward" onClick={() => applyPreset("volatility_breakouts")} />
        <PresetCard icon={Leaf} title="DeFi Opportunities" desc="DeFi sector assets with bullish signals" onClick={() => applyPreset("defi_opportunities")} />
        <PresetCard icon={Building2} title="Large Cap Only" desc="Market cap >$10B — lower risk signals" onClick={() => applyPreset("large_cap_only")} />
        <PresetCard icon={RefreshCw} title="Contrarian Signals" desc="Extreme volatility buy signals — against the trend" onClick={() => applyPreset("contrarian_signals")} />
      </div>
      
      {/* SECTION 2 - Filters */}
      <GlassCard tier="flat" shape="shape-ledger" className="p-0 overflow-hidden relative z-10">
        <div 
          className="p-6 bg-surface/30 flex justify-between items-center cursor-pointer hover:bg-surface/50 transition-colors border-b border-text/5"
          onClick={() => setFiltersOpen(!filtersOpen)}
        >
          <h2 className="text-text font-black flex items-center gap-3 tracking-tight">
            <Search size={20} className="text-accent" />
            Advanced Filtering Engine
          </h2>
          <div className="p-2 glass bg-text/5 rounded-full hover:bg-text/10 transition-colors">
            {filtersOpen ? <ChevronUp size={16} className="text-text-muted" /> : <ChevronDown size={16} className="text-text-muted" />}
          </div>
        </div>
        
        {filtersOpen && (
          <div className="p-8 grid grid-cols-1 md:grid-cols-3 gap-10 bg-surface/20">
            
            {/* Column 1 */}
            <div className="space-y-6">
              <div>
                <label className="block text-[10px] font-bold text-text-muted uppercase tracking-widest mb-2">Direction</label>
                <select className="w-full bg-surface/50 text-text p-3 rounded-sm border border-text/10 focus:border-accent focus:outline-none transition-colors font-mono text-sm" value={direction} onChange={e => setDirection(e.target.value)}>
                  <option value="all">All Directions</option>
                  <option value="strong_up">Strong Buy</option>
                  <option value="up">Buy</option>
                  <option value="neutral">Neutral</option>
                  <option value="down">Sell</option>
                  <option value="strong_down">Strong Sell</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-bold text-text-muted uppercase tracking-widest mb-2">Sector</label>
                <select className="w-full bg-surface/50 text-text p-3 rounded-sm border border-text/10 focus:border-accent focus:outline-none transition-colors font-mono text-sm" value={sector} onChange={e => setSector(e.target.value)}>
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
                <label className="block text-[10px] font-bold text-text-muted uppercase tracking-widest mb-2">Volatility</label>
                <select className="w-full bg-surface/50 text-text p-3 rounded-sm border border-text/10 focus:border-accent focus:outline-none transition-colors font-mono text-sm" value={volatility} onChange={e => setVolatility(e.target.value)}>
                  <option value="all">All Regime</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="extreme">Extreme</option>
                </select>
              </div>
            </div>
            
            {/* Column 2 */}
            <div className="space-y-6">
              <div>
                <div className="flex justify-between items-end mb-2">
                  <label className="block text-[10px] font-bold text-text-muted uppercase tracking-widest">Min Confidence</label>
                  <span className="text-xs text-accent font-mono font-bold bg-accent/10 px-2 py-0.5 rounded border border-accent/20">{minConf}%</span>
                </div>
                <input type="range" min="0" max="100" value={minConf} onChange={e => setMinConf(Number(e.target.value))} className="w-full accent-accent" />
              </div>
              <div>
                <div className="flex justify-between items-end mb-2">
                  <label className="block text-[10px] font-bold text-text-muted uppercase tracking-widest">Max Confidence</label>
                  <span className="text-xs text-accent font-mono font-bold bg-accent/10 px-2 py-0.5 rounded border border-accent/20">{maxConf}%</span>
                </div>
                <input type="range" min="0" max="100" value={maxConf} onChange={e => setMaxConf(Number(e.target.value))} className="w-full accent-accent" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-text-muted uppercase tracking-widest mb-2">Sort By</label>
                <select className="w-full bg-surface/50 text-text p-3 rounded-sm border border-text/10 focus:border-accent focus:outline-none transition-colors font-mono text-sm" value={sortBy} onChange={e => setSortBy(e.target.value)}>
                  <option value="symbol">Symbol</option>
                  <option value="sector">Sector</option>
                  <option value="current_price">Price</option>
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
            <div className="space-y-6 flex flex-col h-full">
              <div>
                <div className="flex justify-between items-end mb-2">
                  <label className="block text-[10px] font-bold text-text-muted uppercase tracking-widest">RSI Range</label>
                  <span className="text-xs text-text-muted font-mono font-bold bg-text/5 px-2 py-0.5 rounded border border-text/10">{minRsi} - {maxRsi}</span>
                </div>
                <div className="flex gap-4">
                  <input type="range" min="0" max="100" value={minRsi} onChange={e => setMinRsi(Math.min(Number(e.target.value), maxRsi))} className="w-1/2 accent-accent" />
                  <input type="range" min="0" max="100" value={maxRsi} onChange={e => setMaxRsi(Math.max(Number(e.target.value), minRsi))} className="w-1/2 accent-accent" />
                </div>
                <div className="flex justify-between text-[9px] mt-2 uppercase tracking-widest font-bold">
                  <span className="text-success">&lt;30 Oversold</span>
                  <span className="text-text-muted">Normal</span>
                  <span className="text-danger">&gt;70 Overbought</span>
                </div>
              </div>
              
              <div>
                <label className="block text-[10px] font-bold text-text-muted uppercase tracking-widest mb-2">Sort Direction</label>
                <div className="flex bg-surface/50 rounded-sm border border-text/10 overflow-hidden p-1 gap-1">
                  <button onClick={() => setSortDir("asc")} className={`flex-1 py-2 text-[10px] uppercase tracking-widest font-bold transition-all rounded-sm ${sortDir === "asc" ? "bg-accent/20 text-accent border border-accent/30 shadow-inner" : "text-text-muted hover:text-text hover:bg-text/5"}`}>↑ Ascending</button>
                  <button onClick={() => setSortDir("desc")} className={`flex-1 py-2 text-[10px] uppercase tracking-widest font-bold transition-all rounded-sm ${sortDir === "desc" ? "bg-accent/20 text-accent border border-accent/30 shadow-inner" : "text-text-muted hover:text-text hover:bg-text/5"}`}>↓ Descending</button>
                </div>
              </div>
              
              <div className="mt-auto pt-4">
                <button onClick={handleReset} className="w-full py-3 glass bg-text/5 hover:bg-text/10 text-text font-bold rounded-sm transition-all text-xs uppercase tracking-widest border border-text/10 hover:border-text/20">
                  Reset Constraints
                </button>
              </div>
            </div>
            
          </div>
        )}
      </GlassCard>
      
      {/* SECTION 3 - Results Table */}
      <GlassCard tier="flat" shape="shape-ledger" className="p-0 overflow-hidden relative z-10">
        <div className="p-6 border-b border-text/5 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-surface/30">
          <h2 className="text-text font-black text-lg tracking-tight flex items-center gap-3">
            <span className="bg-accent/10 text-accent border border-accent/20 px-3 py-1 rounded-sm text-sm font-mono font-bold shadow-inner">
                {results ? results.length : "..."}
            </span>
            Assets Discovered
          </h2>
          <div className="flex flex-wrap gap-3">
            <button 
              onClick={refreshLiveTechnicals} 
              disabled={isRefreshing}
              className="flex items-center gap-2 text-[10px] uppercase tracking-widest font-bold text-success hover:text-success/80 transition-all glass bg-success/10 px-4 py-2 rounded-sm border border-success/30 disabled:opacity-50 shadow-[0_0_15px_rgba(34,197,94,0.1)]"
            >
              <RefreshCw size={14} className={isRefreshing ? "animate-spin" : ""} /> {isRefreshing ? "Synchronizing..." : "Live Sync"}
            </button>
            <button onClick={exportCSV} className="flex items-center gap-2 text-[10px] uppercase tracking-widest font-bold text-accent hover:text-accent/80 transition-all glass bg-accent/10 px-4 py-2 rounded-sm border border-accent/30 shadow-[0_0_15px_rgba(var(--accent),0.1)]">
              <Download size={14} /> Export CSV
            </button>
          </div>
        </div>
        
        {isLoading ? (
          <div className="p-8">
            <TableSkeleton rows={15} />
          </div>
        ) : results && results.length > 0 ? (
          <div className="overflow-x-auto custom-scrollbar relative overflow-hidden">
            {isRefreshing && (
              <div className="absolute left-0 right-0 h-32 bg-gradient-to-b from-transparent via-accent/5 to-accent/20 border-b border-accent/40 z-20 pointer-events-none animate-scanline mix-blend-plus-lighter" />
            )}
            <table className="w-full text-sm text-left">
              <thead className="text-[10px] text-text-muted uppercase tracking-widest bg-surface/50 font-mono border-b border-text/5 sticky top-0 z-10 backdrop-blur-md">
                <tr>
                  <th className="px-6 py-4 cursor-pointer hover:text-text transition-colors" onClick={() => {setSortBy('symbol'); setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}}>Asset</th>
                  <th className="px-6 py-4 cursor-pointer hover:text-text transition-colors" onClick={() => {setSortBy('sector'); setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}}>Sector</th>
                  <th className="px-6 py-4 cursor-pointer hover:text-text transition-colors text-right" onClick={() => {setSortBy('current_price'); setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}}>Live Price</th>
                  <th className="px-6 py-4 cursor-pointer hover:text-text transition-colors" onClick={() => {setSortBy('predicted_direction'); setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}}>AI Direction</th>
                  <th className="px-6 py-4 cursor-pointer hover:text-text transition-colors" onClick={() => {setSortBy('confidence'); setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}}>Confidence</th>
                  <th className="px-6 py-4 cursor-pointer hover:text-text transition-colors" onClick={() => {setSortBy('rsi_14'); setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}}>RSI (14d)</th>
                  <th className="px-6 py-4 cursor-pointer hover:text-text transition-colors" onClick={() => {setSortBy('returns_7d'); setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}}>7D Return</th>
                  <th className="px-6 py-4 cursor-pointer hover:text-text transition-colors" onClick={() => {setSortBy('volatility_7d'); setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}}>Volatility</th>
                  <th className="px-6 py-4 text-right cursor-pointer hover:text-text transition-colors" onClick={() => {setSortBy('market_cap_usd'); setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}}>Market Cap</th>
                  <th className="px-6 py-4 text-center">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-text/5">
                {results.map((row: any, i: number) => {
                  const live = liveData[row.symbol];
                  const displayPrice = live ? live.price : row.current_price;
                  
                  let displayMcapUsd = row.market_cap_usd;
                  if (live && row.current_price && row.current_price > 0) {
                    displayMcapUsd = (live.price / row.current_price) * row.market_cap_usd;
                  }
                  
                  const getFormattedMcap = (usdVal: number) => {
                      if (!usdVal) return "—";
                      const localVal = usdVal * exchangeRate;
                      const sym = CURRENCY_SYMBOLS[currency];
                      if (localVal >= 1e12) return `${sym}${(localVal / 1e12).toFixed(1)}T`;
                      if (localVal >= 1e9) return `${sym}${(localVal / 1e9).toFixed(1)}B`;
                      if (localVal >= 1e6) return `${sym}${(localVal / 1e6).toFixed(1)}M`;
                      return `${sym}${localVal.toLocaleString(undefined, {maximumFractionDigits: 0})}`;
                  };
                  
                  return (
                  <tr key={i} className="hover:bg-text/[0.02] transition-colors group">
                    <td className="px-6 py-4">
                      <Link href={`/coin/${row.symbol}`} className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-surface/50 border border-text/10 flex items-center justify-center font-bold text-xs shadow-inner">
                            {row.symbol.charAt(0)}
                        </div>
                        <span className="font-black font-sans tracking-tight text-text text-lg group-hover:text-accent transition-colors">{row.symbol}</span>
                      </Link>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-[9px] uppercase bg-surface/80 border border-text/10 text-text-muted px-2.5 py-1 rounded-sm font-mono tracking-widest font-bold">{row.sector}</span>
                    </td>
                    <td className="px-6 py-4 text-right font-mono font-bold text-text transition-all duration-300">
                      <div className="flex items-center justify-end gap-2">
                          {live && <span className="relative flex h-2 w-2"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"></span><span className="relative inline-flex rounded-full h-2 w-2 bg-accent"></span></span>}
                          <span className={live ? "text-accent drop-shadow-[0_0_5px_rgba(var(--accent),0.5)]" : ""}>
                            {formatPrice(displayPrice)}
                          </span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <DirectionBadge direction={row.predicted_direction} />
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col gap-1.5 w-32">
                        <div className="flex justify-between items-center text-[10px] text-text font-mono font-bold">
                            <span>CONFIDENCE</span>
                            <span>{(row.confidence).toFixed(1)}%</span>
                        </div>
                        <div className="w-full bg-background h-1.5 rounded-full overflow-hidden border border-text/5">
                          <div className="bg-accent h-full shadow-[0_0_10px_currentColor] transition-all" style={{ width: `${row.confidence}%` }}></div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 font-mono font-bold text-xs">
                      <div className="flex items-center gap-2">
                        <span className="text-text">{row.rsi_14?.toFixed(1) || 'N/A'}</span>
                        {row.rsi_14 < 30 && <span className="text-[9px] bg-success/10 text-success px-1.5 py-0.5 shape-tag border border-success/30 uppercase tracking-widest">OVS</span>}
                        {row.rsi_14 > 70 && <span className="text-[9px] bg-danger/10 text-danger px-1.5 py-0.5 shape-tag border border-danger/30 uppercase tracking-widest">OVB</span>}
                      </div>
                    </td>
                    <td className={`px-6 py-4 font-mono font-black text-xs ${row.returns_7d > 0 ? "text-success" : "text-danger"}`}>
                      {row.returns_7d > 0 ? "+" : ""}{(row.returns_7d * 100).toFixed(2)}%
                    </td>
                    <td className="px-6 py-4">
                      <VolatilityChip level={row.volatility_regime} />
                    </td>
                    <td className="px-6 py-4 text-right font-mono text-text-muted text-xs transition-all duration-300">
                      <span className={live ? "text-accent/70" : ""}>
                        {getFormattedMcap(displayMcapUsd)}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex justify-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Link href={`/coin/${row.symbol}`} className="text-[10px] uppercase tracking-widest glass bg-text/5 hover:bg-text/10 text-text px-3 py-2 rounded-sm transition-all font-bold border border-text/10 hover:border-text/20">
                          Inspect
                        </Link>
                        <Link href={`/predictions?symbol=${row.symbol}`} className="text-[10px] uppercase tracking-widest glass bg-accent/10 hover:bg-accent/20 text-accent px-3 py-2 rounded-sm transition-all font-bold border border-accent/20 hover:border-accent/40 shadow-inner hover:shadow-[0_0_15px_rgba(var(--accent),0.2)]">
                          Pipeline
                        </Link>
                      </div>
                    </td>
                  </tr>
                )})}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-20 flex flex-col items-center justify-center text-center">
            <div className="glass bg-text/5 p-6 rounded-full mb-6 border border-text/10">
              <Search size={48} className="text-text-muted opacity-50" />
            </div>
            <h3 className="text-2xl font-black text-text mb-2 tracking-tight">No assets match criteria</h3>
            <p className="text-text-muted mb-8 font-light tracking-wide max-w-md">Try relaxing the confidence or direction constraints to find more opportunities.</p>
            <button onClick={handleReset} className="glass bg-accent hover:bg-accent/90 text-white px-8 py-3.5 rounded-sm font-black transition-all shadow-[0_0_20px_rgba(var(--accent),0.3)] hover:shadow-[0_0_30px_rgba(var(--accent),0.5)] uppercase tracking-widest text-xs">
              Clear Constraints
            </button>
          </div>
        )}
      </GlassCard>
      
    </div>
  );
}

