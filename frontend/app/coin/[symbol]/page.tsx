"use client";

import { useEffect, useState, useRef } from "react";
import { createChart, ColorType, IChartApi } from "lightweight-charts";
import { AreaChart, Area, ComposedChart, Line, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from "recharts";
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

const BASE = "http://localhost:8000";

function DirectionBadge({ dir }: { dir: string }) {
  if (dir === "strong_up") return <span className="px-2 py-0.5 rounded-full bg-green-950 text-green-400 border border-green-800 text-xs">Strong Buy</span>;
  if (dir === "up") return <span className="px-2 py-0.5 rounded-full bg-green-900/50 text-green-300 border border-green-700/50 text-xs">Buy</span>;
  if (dir === "strong_down") return <span className="px-2 py-0.5 rounded-full bg-red-950 text-red-400 border border-red-800 text-xs">Strong Sell</span>;
  if (dir === "down") return <span className="px-2 py-0.5 rounded-full bg-red-900/50 text-red-300 border border-red-700/50 text-xs">Sell</span>;
  return <span className="px-2 py-0.5 rounded-full bg-[#1a1a1a] text-gray-400 border border-gray-700 text-xs">Neutral</span>;
}

export default function CoinDetailPage({ params }: { params: { symbol: string } }) {
  const symbol = params.symbol.toUpperCase();
  const [period, setPeriod] = useState("3M");
  
  // Toggles
  const [showRSI, setShowRSI] = useState(false);
  const [showMACD, setShowMACD] = useState(false);
  const [showBB, setShowBB] = useState(false);
  
  // Chart refs
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  
  // Data fetching
  const { data: ohlcv } = useSWR(`${BASE}/api/coins/${symbol}/ohlcv?period=${period}`, fetcher);
  const { data: indicators } = useSWR(`${BASE}/api/coins/${symbol}/indicators?period=${period}`, fetcher);
  const { data: history } = useSWR(`${BASE}/api/coins/${symbol}/prediction-history`, fetcher);
  const { data: correlations } = useSWR(`${BASE}/api/coins/${symbol}/correlations`, fetcher);
  const { data: sentiment } = useSWR(`${BASE}/api/coins/${symbol}/sentiment-history`, fetcher);
  
  // Asset info (we can get it from the market or just use the symbol)
  const { data: assetsData } = useSWR(`${BASE}/api/assets`, fetcher);
  const asset = assetsData?.find((a: any) => a.symbol.toUpperCase() === symbol);
  
  // Lightweight charts initialization
  useEffect(() => {
    if (!chartContainerRef.current || !ohlcv) return;
    
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 480,
      layout: {
        background: { type: ColorType.Solid, color: "#0f0f0f" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "#1a1a1a" },
        horzLines: { color: "#1a1a1a" },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: "#2a2a2a" },
      timeScale: { borderColor: "#2a2a2a", timeVisible: true },
    });
    
    chartRef.current = chart;
    
    const candleSeries = chart.addCandlestickSeries({
      upColor:   "#22c55e",
      downColor: "#ef4444",
      borderUpColor:   "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor:   "#22c55e",
      wickDownColor: "#ef4444",
    });
    
    candleSeries.setData(ohlcv.map((d: any) => ({
      time:  d.date,
      open:  d.open,
      high:  d.high,
      low:   d.low,
      close: d.close,
    })));
    
    // Volume histogram
    const volumeSeries = chart.addHistogramSeries({
      color: "#6366f140",
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    
    volumeSeries.setData(ohlcv.map((d: any) => ({
      time:  d.date,
      value: d.volume,
      color: d.close >= d.open ? "#22c55e30" : "#ef444430",
    })));
    
    // Add Bollinger Bands if toggled
    if (showBB && indicators && indicators.length > 0) {
      const upperData: any[] = [];
      const lowerData: any[] = [];
      const middleData: any[] = [];
      
      // We need to compute SMA 20 from OHLCV and use bb_width from indicators
      // For simplicity here, we'll map dates.
      const indicatorMap = new Map();
      indicators.forEach((i: any) => indicatorMap.set(i.date, i));
      
      ohlcv.forEach((d: any, i: number) => {
        if (i >= 19) {
          let sum = 0;
          for (let j = 0; j < 20; j++) sum += ohlcv[i - j].close;
          const sma = sum / 20;
          const ind = indicatorMap.get(d.date);
          const width = ind?.bb_width || 0; // Using bb_width directly as percentage
          
          if (ind) {
             // approximation if bb_width is roughly (upper-lower)/middle
             // if it's std dev, this is just visual
             middleData.push({ time: d.date, value: sma });
             upperData.push({ time: d.date, value: sma * (1 + width/2) });
             lowerData.push({ time: d.date, value: sma * (1 - width/2) });
          }
        }
      });
      
      if (middleData.length > 0) {
        const upperLine = chart.addLineSeries({ color: "#6366f1", lineWidth: 1, lineStyle: 2 });
        upperLine.setData(upperData);
        
        const lowerLine = chart.addLineSeries({ color: "#6366f1", lineWidth: 1, lineStyle: 2 });
        lowerLine.setData(lowerData);
        
        const middleLine = chart.addLineSeries({ color: "#94a3b8", lineWidth: 1 });
        middleLine.setData(middleData);
      }
    }
    
    chart.timeScale().fitContent();
    
    const handleResize = () => {
      chart.applyOptions({ width: chartContainerRef.current?.clientWidth || 0 });
    };
    window.addEventListener('resize', handleResize);
    
    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [ohlcv, showBB, indicators]);
  
  if (!ohlcv || !history) return <div className="p-8 text-white">Loading...</div>;
  
  const latestOhlcv = ohlcv[ohlcv.length - 1];
  const prevOhlcv = ohlcv.length > 1 ? ohlcv[ohlcv.length - 2] : null;
  const changePct = prevOhlcv ? ((latestOhlcv.close - prevOhlcv.close) / prevOhlcv.close) * 100 : 0;
  const latestPred = history.predictions[0] || {};
  
  return (
    <div className="space-y-6">
      {/* Breadcrumb Navigation */}
      <div className="flex items-center text-sm font-mono text-[#94a3b8] mb-2">
        <Link href="/market" className="hover:text-indigo-400 transition-colors">Market Data</Link>
        <ChevronRight size={14} className="mx-2 text-[#4a4a4a]" />
        <span className="text-white">{symbol}</span>
      </div>

      {/* SECTION 1 - Header */}
      <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a] flex flex-col gap-4">
        <div className="flex justify-between items-start">
          <div className="flex flex-col">
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold text-white font-mono">{symbol}</h1>
              <span className="text-[#94a3b8]">{asset?.name || symbol}</span>
              {asset?.sector && (
                <span className="bg-[#2a2a2a] text-xs px-2 py-1 rounded text-[#cbd5e1] uppercase">
                  {asset.sector}
                </span>
              )}
            </div>
          </div>
          
          <div className="flex flex-col items-center">
            <div className="text-4xl font-mono text-white font-bold">
              ${latestOhlcv?.close > 100 ? latestOhlcv?.close.toFixed(2) : latestOhlcv?.close.toFixed(4)}
            </div>
            <div className={`text-sm font-bold ${changePct >= 0 ? "text-green-500" : "text-red-500"}`}>
              {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}% (24h)
            </div>
          </div>
          
          <div className="flex flex-col items-end gap-2">
            <div className="text-[#94a3b8] text-sm">
              Market Cap: ${asset?.market_cap_usd ? (asset.market_cap_usd / 1e9).toFixed(2) + "B" : "N/A"}
            </div>
            <div className="flex items-center gap-2">
              <DirectionBadge dir={latestPred.direction || "neutral"} />
              <div className="text-xs text-[#94a3b8]">
                Conf: {(latestPred.confidence * 100).toFixed(0)}%
              </div>
            </div>
            <div className="w-32 h-1.5 bg-[#2a2a2a] rounded-full overflow-hidden mt-1">
              <div 
                className="h-full bg-indigo-500" 
                style={{ width: `${(latestPred.confidence || 0) * 100}%` }}
              />
            </div>
          </div>
        </div>
        
        {/* Period Selector Tabs */}
        <div className="flex gap-2 border-b border-[#2a2a2a] pb-2">
          {["1W", "1M", "3M", "1Y", "ALL"].map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-4 py-1.5 rounded-t-lg text-sm font-bold transition-colors ${
                period === p ? "bg-indigo-600 text-white" : "text-[#94a3b8] hover:text-white"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>
      
      {/* SECTION 2 - Main Chart */}
      <div className="bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] overflow-hidden">
        <div ref={chartContainerRef} className="w-full" style={{ height: '480px' }} />
      </div>
      
      {/* SECTION 3 - Technical Indicator Overlays */}
      <div className="space-y-4">
        <div className="flex gap-4">
          <button 
            onClick={() => setShowRSI(!showRSI)}
            className={`px-4 py-2 rounded-lg text-sm font-bold border transition-colors ${
              showRSI ? "border-indigo-500 text-white bg-indigo-500/10" : "border-[#2a2a2a] text-[#94a3b8] hover:border-[#4a4a4a]"
            }`}
          >
            RSI
          </button>
          <button 
            onClick={() => setShowMACD(!showMACD)}
            className={`px-4 py-2 rounded-lg text-sm font-bold border transition-colors ${
              showMACD ? "border-indigo-500 text-white bg-indigo-500/10" : "border-[#2a2a2a] text-[#94a3b8] hover:border-[#4a4a4a]"
            }`}
          >
            MACD
          </button>
          <button 
            onClick={() => setShowBB(!showBB)}
            className={`px-4 py-2 rounded-lg text-sm font-bold border transition-colors ${
              showBB ? "border-indigo-500 text-white bg-indigo-500/10" : "border-[#2a2a2a] text-[#94a3b8] hover:border-[#4a4a4a]"
            }`}
          >
            Bollinger Bands
          </button>
        </div>
        
        {showRSI && indicators && (
          <div className="bg-[#1a1a1a] p-4 rounded-xl border border-[#2a2a2a]">
            <h3 className="text-sm font-mono text-[#94a3b8] mb-2">Relative Strength Index (14)</h3>
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={indicators}>
                  <XAxis dataKey="date" hide />
                  <YAxis domain={[0, 100]} hide />
                  <Tooltip contentStyle={{ backgroundColor: "#0f0f0f", borderColor: "#2a2a2a" }} />
                  <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 3" label={{ value: "Overbought", fill: "#ef4444", position: "insideTopLeft" }} />
                  <ReferenceLine y={30} stroke="#22c55e" strokeDasharray="3 3" label={{ value: "Oversold", fill: "#22c55e", position: "insideBottomLeft" }} />
                  <Area type="monotone" dataKey="rsi_14" stroke="#6366f1" fill="#6366f1" fillOpacity={0.3} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
        
        {showMACD && indicators && (
          <div className="bg-[#1a1a1a] p-4 rounded-xl border border-[#2a2a2a]">
            <h3 className="text-sm font-mono text-[#94a3b8] mb-2">MACD</h3>
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={indicators}>
                  <XAxis dataKey="date" hide />
                  <YAxis hide />
                  <Tooltip contentStyle={{ backgroundColor: "#0f0f0f", borderColor: "#2a2a2a" }} />
                  <ReferenceLine y={0} stroke="#4a4a4a" />
                  <Bar dataKey={(d) => d.macd - d.macd_signal}>
                    {indicators.map((entry: any, index: number) => (
                      <Cell key={`cell-${index}`} fill={entry.macd >= entry.macd_signal ? "#22c55e" : "#ef4444"} />
                    ))}
                  </Bar>
                  <Line type="monotone" dataKey="macd" stroke="#6366f1" dot={false} />
                  <Line type="monotone" dataKey="macd_signal" stroke="#f59e0b" dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
      
      {/* SECTION 4 - Two Column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* LEFT COLUMN: Prediction History */}
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-bold text-white font-mono">Prediction History</h3>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold text-indigo-400">{history.summary.accuracy_pct.toFixed(0)}%</span>
              <span className="text-sm text-[#94a3b8]">accuracy</span>
            </div>
          </div>
          
          <div className="space-y-2 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
            {history.predictions.map((p: any, i: number) => (
              <div key={i} className={`flex items-center justify-between p-3 rounded-lg ${i % 2 === 0 ? "bg-[#2a2a2a]/30" : "bg-transparent"}`}>
                <div className="flex items-center gap-4">
                  <span className="text-xs font-mono text-[#94a3b8] w-24">{p.date}</span>
                  <div className="w-24"><DirectionBadge dir={p.direction} /></div>
                  <span className="text-xs text-[#94a3b8] w-12">{(p.confidence * 100).toFixed(0)}%</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`text-xs font-bold ${p.actual_return > 0 ? "text-green-500" : p.actual_return < 0 ? "text-red-500" : "text-gray-500"}`}>
                    {p.actual_return !== null ? (p.actual_return > 0 ? "+" : "") + (p.actual_return * 100).toFixed(2) + "%" : "-"}
                  </span>
                  <div className="w-6 text-center">
                    {p.was_correct === true && "✅"}
                    {p.was_correct === false && "❌"}
                    {p.was_correct === null && "⏳"}
                  </div>
                </div>
              </div>
            ))}
          </div>
          
          <div className="mt-4 pt-4 border-t border-[#2a2a2a] text-center text-sm font-mono text-[#94a3b8]">
            ✅ {history.summary.correct_count} correct &nbsp;&nbsp; ❌ {history.summary.total_scored - history.summary.correct_count} wrong &nbsp;&nbsp; ⏳ {history.predictions.length - history.summary.total_scored} pending
          </div>
        </div>
        
        {/* RIGHT COLUMN: Correlated Coins */}
        <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
          <h3 className="text-lg font-bold text-white font-mono mb-2">Most Correlated Assets</h3>
          <p className="text-xs text-[#94a3b8] mb-6">
            Positive correlation = moves in same direction as {symbol}<br/>
            Negative correlation = moves in opposite direction
          </p>
          
          <div className="space-y-3">
            {correlations?.map((c: any, i: number) => (
              <Link href={`/coin/${c.symbol}`} key={c.symbol} className="flex items-center justify-between p-2 hover:bg-[#2a2a2a]/50 rounded-lg transition group">
                <div className="flex items-center gap-3 w-1/3">
                  <span className="text-xs text-[#64748b] w-4">{i + 1}</span>
                  <span className="font-mono font-bold text-white group-hover:text-indigo-400">{c.symbol}</span>
                  <span className="text-[10px] uppercase bg-[#2a2a2a] text-[#cbd5e1] px-1.5 py-0.5 rounded">{c.sector}</span>
                </div>
                
                <div className="flex-1 flex items-center px-4">
                  <div className="w-full bg-[#0f0f0f] h-2 rounded-full overflow-hidden flex relative">
                    {/* Zero line marker implicitly in middle, range is -1 to 1 */}
                    <div className="absolute left-1/2 top-0 bottom-0 w-px bg-[#4a4a4a] z-10" />
                    {c.correlation > 0 ? (
                      <div className="h-full bg-green-500 absolute left-1/2" style={{ width: `${c.correlation * 50}%` }} />
                    ) : (
                      <div className="h-full bg-red-500 absolute right-1/2" style={{ width: `${Math.abs(c.correlation) * 50}%` }} />
                    )}
                  </div>
                </div>
                
                <div className="flex items-center justify-end gap-3 w-1/4">
                  <span className={`text-xs font-mono ${c.correlation > 0 ? "text-green-400" : "text-red-400"}`}>
                    {c.correlation > 0 ? "+" : ""}{c.correlation.toFixed(2)}
                  </span>
                  <DirectionBadge dir={c.direction} />
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
      
      {/* SECTION 5 - Sentiment Row */}
      {sentiment && sentiment.length > 0 && (() => {
        // Find latest valid sentiment (some days might be null if incomplete)
        const validSents = sentiment.filter((s: any) => s.sentiment_score !== null);
        const latestSent = validSents.length > 0 ? validSents[validSents.length - 1] : {};
        
        return (
          <div className="bg-[#1a1a1a] p-6 rounded-xl border border-[#2a2a2a]">
            <h3 className="text-lg font-bold text-white font-mono mb-6">Community Sentiment — Last 90 Days</h3>
            
            <div className="h-[200px] mb-6">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={sentiment}>
                  <XAxis dataKey="date" stroke="#4a4a4a" tick={{fill: '#94a3b8', fontSize: 12}} />
                  <YAxis yAxisId="left" domain={[-1, 1]} orientation="left" stroke="#6366f1" hide />
                  <YAxis yAxisId="right" domain={[0, 1]} orientation="right" stroke="#f59e0b" hide />
                  <Tooltip contentStyle={{ backgroundColor: "#0f0f0f", borderColor: "#2a2a2a", color: "#fff" }} />
                  <ReferenceLine yAxisId="left" y={0} stroke="#4a4a4a" />
                  <Area yAxisId="left" type="monotone" dataKey="sentiment_score" fill="#6366f1" stroke="#6366f1" fillOpacity={0.3} />
                  <Line yAxisId="right" type="monotone" dataKey="fear_greed_norm" stroke="#f59e0b" dot={false} strokeWidth={2} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-[#0f0f0f] p-3 rounded-lg border border-[#2a2a2a] text-center">
                <div className="text-xs text-[#94a3b8] mb-1">Current Sentiment</div>
                <div className="text-lg font-mono font-bold text-white">{(latestSent.sentiment_score || 0).toFixed(2)}</div>
              </div>
              <div className="bg-[#0f0f0f] p-3 rounded-lg border border-[#2a2a2a] text-center">
                <div className="text-xs text-[#94a3b8] mb-1">Community Score</div>
                <div className="text-lg font-mono font-bold text-white">{(latestSent.community_score || 0).toFixed(0)}%</div>
              </div>
              <div className="bg-[#0f0f0f] p-3 rounded-lg border border-[#2a2a2a] text-center">
                <div className="text-xs text-[#94a3b8] mb-1">Public Interest</div>
                <div className="text-lg font-mono font-bold text-white">{(latestSent.public_interest || 0).toFixed(0)}</div>
              </div>
              <div className="bg-[#0f0f0f] p-3 rounded-lg border border-[#2a2a2a] text-center">
                <div className="text-xs text-[#94a3b8] mb-1">Fear & Greed</div>
                <div className="text-lg font-mono font-bold text-white">{latestSent.fear_greed || 'N/A'}</div>
              </div>
            </div>
          </div>
        );
      })()}
      
    </div>
  );
}
