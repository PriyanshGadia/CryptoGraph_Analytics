"use client";

import { useEffect, useState, useRef } from "react";
import { createChart, ColorType, IChartApi } from "lightweight-charts";
import { AreaChart, Area, ComposedChart, Line, Bar, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, ReferenceLine, Cell } from "recharts";
import { ChevronRight, RefreshCw, Maximize, Minimize, Brain, Layers, Activity, ActivitySquare, ShieldAlert, CircleDot, Info, TrendingUp, TrendingDown } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

const BASE = "http://localhost:8000";
const WS_BASE = BASE.replace(/^http/, "ws");

function DirectionBadge({ dir }: { dir: string }) {
  const config: Record<string, {bg: string, text: string, label: string, border: string}> = {
    strong_up:   {bg:"bg-[#10b981]/10",  text:"text-[#10b981]", label:"STRONG BUY", border:"border-[#10b981]/20"},
    up:          {bg:"bg-[#34d399]/10",  text:"text-[#34d399]", label:"BUY", border:"border-[#34d399]/20"},
    neutral:     {bg:"bg-[#94a3b8]/10",   text:"text-[#94a3b8]",  label:"NEUTRAL", border:"border-[#94a3b8]/20"},
    down:        {bg:"bg-[#fb923c]/10",    text:"text-[#fb923c]",   label:"SELL", border:"border-[#fb923c]/20"},
    strong_down: {bg:"bg-[#f43f5e]/10",    text:"text-[#f43f5e]",   label:"STRONG SELL", border:"border-[#f43f5e]/20"},
  }
  const c = config[dir] || config["neutral"]
  return (
    <span className={`inline-flex items-center justify-center px-3 py-1 rounded-sm text-[10px] font-bold uppercase tracking-widest border ${c.bg} ${c.text} ${c.border}`}>
      {c.label}
    </span>
  )
}

function VolatilityChip({ regime }: { regime: string }) {
  const colors: Record<string,string> = {
    low:"bg-blue-500/10 text-blue-400 border-blue-500/20", medium:"bg-amber-500/10 text-amber-400 border-amber-500/20",
    high:"bg-orange-500/10 text-orange-400 border-orange-500/20", extreme:"bg-red-500/10 text-red-400 border-red-500/20"
  }
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] border font-mono uppercase tracking-widest ${colors[regime] || colors.medium}`}>
      {regime}
    </span>
  )
}

// Math Helpers for Live Edge Calculations
function calculateRSI(prices: number[], period: number = 14) {
  if (prices.length < period + 1) return 50;
  let gains = 0, losses = 0;
  for (let i = prices.length - period; i < prices.length; i++) {
    const diff = prices[i] - prices[i-1];
    if (diff > 0) gains += diff;
    else losses -= diff;
  }
  if (losses === 0) return 100;
  const rs = (gains / period) / (losses / period);
  return 100 - (100 / (1 + rs));
}

function calculateMACD(prices: number[]) {
  if (prices.length < 26) return 0;
  // Simple EMA implementation
  const ema = (data: number[], span: number) => {
    const k = 2 / (span + 1);
    let emaVal = data[data.length - span] || data[0];
    for (let i = data.length - span + 1; i < data.length; i++) {
      emaVal = (data[i] - emaVal) * k + emaVal;
    }
    return emaVal;
  }
  return ema(prices, 12) - ema(prices, 26);
}

function calculateBB(prices: number[], period: number = 20) {
  if (prices.length < period) return { upper: 0, lower: 0, sma: 0, width: 0 };
  const slice = prices.slice(-period);
  const sma = slice.reduce((a, b) => a + b, 0) / period;
  const variance = slice.reduce((a, b) => a + Math.pow(b - sma, 2), 0) / period;
  const std = Math.sqrt(variance);
  const width = (4 * std) / sma;
  return { sma, std, upper: sma + 2*std, lower: sma - 2*std, width };
}


export default function CoinDetailPage({ params }: { params: { symbol: string } }) {
  const symbol = params.symbol.toUpperCase();
  const [period, setPeriod] = useState("3M");
  const [interval, setIntervalState] = useState("1h");
  
  // Toggles & State
  const [showRSI, setShowRSI] = useState(false);
  const [showMACD, setShowMACD] = useState(false);
  const [showBB, setShowBB] = useState(false);
  const [chartType, setChartType] = useState<"candlestick" | "line">("candlestick");
  const [tooltipData, setTooltipData] = useState<any>(null);
  const [syncing, setSyncing] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [livePrice, setLivePrice] = useState<number | null>(null);
  const [liveVolume24h, setLiveVolume24h] = useState<number>(0);
  const [liveATH, setLiveATH] = useState<number>(0);
  
  // Chart refs
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);
  
  // Data fetching
  const { data: ohlcv, mutate: mutateOhlcv } = useSWR(`${BASE}/api/coins/${symbol}/ohlcv?interval=${interval}`, fetcher);
  const { data: history } = useSWR(`${BASE}/api/coins/${symbol}/prediction-history`, fetcher);
  const { data: correlations } = useSWR(`${BASE}/api/coins/${symbol}/correlations`, fetcher);
  const { data: sentiment } = useSWR(`${BASE}/api/coins/${symbol}/sentiment-history`, fetcher);
  
  const { data: assetsData } = useSWR(`${BASE}/api/assets`, fetcher);
  const asset = assetsData?.find((a: any) => a.symbol.toUpperCase() === symbol);

  const handleForceSync = async () => {
    setSyncing(true);
    try {
      await fetch(`${BASE}/api/screener/refresh`, { method: "POST" });
      await mutateOhlcv();
    } finally {
      setSyncing(false);
    }
  };
  
  // Live Edge Calculations (Fundamentals)
  useEffect(() => {
    if (ohlcv && ohlcv.length > 0) {
      // Volume 24h (assuming interval is 1h, sum last 24 items)
      const is1h = interval === "1h";
      const lookback = is1h ? Math.min(24, ohlcv.length) : Math.min(ohlcv.length, 10);
      const vol24 = ohlcv.slice(-lookback).reduce((acc: number, curr: any) => acc + curr.volume, 0);
      setLiveVolume24h(vol24);

      // ATH
      const ath = Math.max(...ohlcv.map((d: any) => d.high));
      setLiveATH(ath);
    }
  }, [ohlcv, interval]);

  // Live Ticker WebSocket
  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/api/stream/ticker/${symbol}`);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (seriesRef.current) {
        seriesRef.current.update({
          time: data.time,
          open: data.open,
          high: data.high,
          low: data.low,
          close: data.close,
          value: data.close,
        });
      }
      if (volumeSeriesRef.current) {
        volumeSeriesRef.current.update({
          time: data.time,
          value: data.volume,
          color: data.close >= data.open ? "#10b98130" : "#f43f5e30",
        });
      }
      setLivePrice(data.close);
    };
    return () => ws.close();
  }, [symbol]);
  
  // Lightweight charts initialization
  useEffect(() => {
    if (!chartContainerRef.current || !ohlcv) return;
    
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }
    
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: isFullscreen ? window.innerHeight - 100 : 480,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#64748b",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.03)" },
        horzLines: { color: "rgba(255, 255, 255, 0.03)" },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: "rgba(255, 255, 255, 0.1)" },
      timeScale: { borderColor: "rgba(255, 255, 255, 0.1)", timeVisible: true },
    });
    
    chartRef.current = chart;
    
    const series = chartType === 'candlestick' ? chart.addCandlestickSeries({
      upColor:   "#10b981",
      downColor: "#f43f5e",
      borderUpColor:   "#10b981",
      borderDownColor: "#f43f5e",
      wickUpColor:   "#10b981",
      wickDownColor: "#f43f5e",
    }) : chart.addLineSeries({
      color: "#6366f1",
      lineWidth: 2,
    });
    
    seriesRef.current = series;
    
    const mapData = ohlcv.map((d: any) => ({
      time:  d.time,
      open:  d.open,
      high:  d.high,
      low:   d.low,
      close: d.close,
      value: d.close
    }));
    series.setData(mapData);
    
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
      time:  d.time,
      value: d.volume,
      color: d.close >= d.open ? "#10b98130" : "#f43f5e30",
    })));
    volumeSeriesRef.current = volumeSeries;
    
    // Add Bollinger Bands dynamically if toggled
    if (showBB) {
      const upperData: any[] = [];
      const lowerData: any[] = [];
      const middleData: any[] = [];
      
      const prices = ohlcv.map((d:any) => d.close);
      
      ohlcv.forEach((d: any, i: number) => {
        if (i >= 19) {
          const bb = calculateBB(prices.slice(0, i + 1), 20);
          middleData.push({ time: d.time, value: bb.sma });
          upperData.push({ time: d.time, value: bb.upper });
          lowerData.push({ time: d.time, value: bb.lower });
        }
      });
      
      if (middleData.length > 0) {
        const upperLine = chart.addLineSeries({ color: "#818cf8", lineWidth: 1, lineStyle: 2 });
        upperLine.setData(upperData);
        const lowerLine = chart.addLineSeries({ color: "#818cf8", lineWidth: 1, lineStyle: 2 });
        lowerLine.setData(lowerData);
        const middleLine = chart.addLineSeries({ color: "#64748b", lineWidth: 1 });
        middleLine.setData(middleData);
      }
    }
    
    chart.subscribeCrosshairMove((param) => {
      if (
        param.point === undefined ||
        !param.time ||
        param.point.x < 0 ||
        param.point.x > chartContainerRef.current!.clientWidth ||
        param.point.y < 0 ||
        param.point.y > chartContainerRef.current!.clientHeight
      ) {
        setTooltipData(null);
      } else {
        const data = param.seriesData.get(series) as any;
        if (data) {
          setTooltipData({
            time: param.time as number,
            open: data.open ?? data.value,
            high: data.high ?? data.value,
            low: data.low ?? data.value,
            close: data.close ?? data.value,
            volume: (param.seriesData.get(volumeSeries) as any)?.value || 0
          });
        }
      }
    });

    const handleResize = () => {
      chart.applyOptions({ width: chartContainerRef.current?.clientWidth || 0 });
    };
    window.addEventListener('resize', handleResize);
    
    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [ohlcv, showBB, chartType, isFullscreen]); 
  
  useEffect(() => {
    if (chartRef.current && ohlcv && ohlcv.length > 0) {
      const last = ohlcv[ohlcv.length - 1];
      const toTs = last.time;
      let fromTs = ohlcv[0].time;
      
      if (period === "1D") fromTs = toTs - 24 * 60 * 60;
      else if (period === "1W") fromTs = toTs - 7 * 24 * 60 * 60;
      else if (period === "1M") fromTs = toTs - 30 * 24 * 60 * 60;
      else if (period === "3M") fromTs = toTs - 90 * 24 * 60 * 60;
      else if (period === "1Y") fromTs = toTs - 365 * 24 * 60 * 60;
      
      if (fromTs < ohlcv[0].time) fromTs = ohlcv[0].time;
      
      chartRef.current.timeScale().setVisibleRange({
        from: fromTs as any,
        to: (toTs + 3600) as any
      });
    }
  }, [period, ohlcv]);
  
  if (!ohlcv || !history) return (
    <div className="h-screen flex items-center justify-center text-slate-500 font-mono text-sm tracking-widest uppercase bg-[#030712]">
        Loading Asset Profile...
    </div>
  );
  
  const latestOhlcv = ohlcv[ohlcv.length - 1];
  const prevOhlcv = ohlcv.length > 1 ? ohlcv[ohlcv.length - 2] : null;
  const displayPrice = livePrice !== null ? livePrice : latestOhlcv?.close;
  const changePct = prevOhlcv ? ((displayPrice - prevOhlcv.close) / prevOhlcv.close) * 100 : 0;
  const latestPred = history.predictions[0] || {};
  
  // Realtime Market Cap & Supply Scaling
  let displayMcap = asset?.market_cap_usd;
  let circSupply = 0;
  if (asset?.market_cap_usd && latestOhlcv?.close && latestOhlcv.close > 0 && livePrice) {
    displayMcap = (livePrice / latestOhlcv.close) * asset.market_cap_usd;
  }
  if (displayMcap && displayPrice) {
      circSupply = displayMcap / displayPrice;
  }

  // Calculate live technical indicators right now
  const livePrices = ohlcv.map((d: any) => d.close);
  if (livePrice !== null) livePrices[livePrices.length - 1] = livePrice; // update with absolute latest tick
  
  const liveRSI = calculateRSI(livePrices, 14);
  const liveMACD = calculateMACD(livePrices);
  const liveBB = calculateBB(livePrices, 20);
  
  return (
    <div className="space-y-6 bg-[#030712] min-h-screen text-slate-200 pb-12 relative overflow-hidden">
      
      {/* Subtle Glow Backgrounds */}
      <div className="absolute top-0 right-0 w-[600px] h-[600px] bg-indigo-900/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute top-[40%] left-[-100px] w-[500px] h-[500px] bg-emerald-900/5 rounded-full blur-[100px] pointer-events-none" />

      {/* Breadcrumb Navigation */}
      <div className="flex items-center text-xs font-mono text-slate-500 uppercase tracking-widest mb-2 relative z-10 p-4 pb-0 max-w-[1600px] mx-auto">
        <Link href="/market" className="hover:text-indigo-400 transition-colors">Market Data</Link>
        <ChevronRight size={14} className="mx-2 text-slate-700" />
        <span className="text-slate-300">{symbol}</span>
      </div>

      <div className="max-w-[1600px] mx-auto px-4 relative z-10 space-y-6">
          {/* SECTION 1 - Header */}
          <div className="bg-white/[0.02] border border-white/[0.05] p-6 lg:p-8 rounded-3xl shadow-2xl backdrop-blur-xl flex flex-col gap-4">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
              <div className="flex flex-col">
                <div className="flex items-center gap-3">
                  <h1 className="text-4xl lg:text-5xl font-black text-white tracking-tight">{symbol}</h1>
                  <span className="text-slate-400 text-lg font-light tracking-wide">{asset?.name || symbol}</span>
                  {asset?.sector && (
                    <span className="bg-indigo-500/10 border border-indigo-500/20 text-[10px] px-2 py-1 rounded text-indigo-400 uppercase font-mono tracking-widest">
                      {asset.sector}
                    </span>
                  )}
                </div>
                <div className="flex items-center mt-4 gap-4">
                    <div className={`text-4xl font-mono transition-colors duration-300 ${livePrice ? 'text-indigo-300' : 'text-white'}`}>
                    ${displayPrice > 100 ? displayPrice.toFixed(2) : displayPrice.toFixed(4)}
                    </div>
                    <div className={`text-sm font-bold flex items-center ${changePct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {changePct >= 0 ? <TrendingUp size={16} className="mr-1"/> : <TrendingDown size={16} className="mr-1"/>}
                    {Math.abs(changePct).toFixed(2)}% (24h)
                    </div>
                </div>
              </div>
              
              <div className="flex flex-col items-end gap-3 w-full md:w-auto">
                <Link 
                  href={`/predictions?symbol=${symbol}`}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-3 rounded-xl text-sm font-bold tracking-wide transition-all shadow-[0_0_15px_rgba(99,102,241,0.2)] flex items-center gap-2 hover:scale-105"
                >
                  <Brain size={16} /> Analyze in Prediction Studio
                </Link>
                <div className="flex items-center gap-3 bg-black/40 border border-white/5 rounded-lg p-3 w-full md:w-auto justify-between">
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-500 uppercase font-mono tracking-widest">Latest Signal</span>
                        <DirectionBadge dir={latestPred.direction || "neutral"} />
                    </div>
                    <div className="flex flex-col items-end">
                        <span className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Confidence</span>
                        <div className="w-24 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                        <div 
                            className="h-full bg-indigo-500" 
                            style={{ width: `${latestPred.confidence || 0}%` }}
                        />
                        </div>
                    </div>
                </div>
              </div>
            </div>
          </div>
          
          {/* SECTION 2 - Main Chart */}
          <div className={`bg-white/[0.02] border border-white/[0.05] shadow-2xl backdrop-blur-xl rounded-3xl overflow-hidden p-4 ${isFullscreen ? 'fixed inset-0 z-50 rounded-none m-0 bg-[#030712] border-0' : ''}`}>
            
            {/* Chart Actions Toolbar */}
            <div className="flex flex-wrap justify-between items-center mb-4 gap-4">
              <div className="flex gap-2 items-center">
                <div className="flex bg-black/40 rounded-lg border border-white/5 p-1">
                  {["1m", "5m", "15m", "1h", "4h", "1d", "1w"].map(i => (
                    <button
                      key={i}
                      onClick={() => setIntervalState(i)}
                      className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all ${
                        interval === i ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500 hover:text-slate-300 hover:bg-white/5"
                      }`}
                    >
                      {i}
                    </button>
                  ))}
                </div>
                
                <div className="w-px h-6 bg-white/10 mx-2" />
                
                <button 
                  onClick={() => setChartType('candlestick')}
                  className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all ${chartType === 'candlestick' ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-white/5"}`}
                >
                  Candles
                </button>
                <button 
                  onClick={() => setChartType('line')}
                  className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all ${chartType === 'line' ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-white/5"}`}
                >
                  Line
                </button>
                <div className="w-px h-6 bg-white/10 mx-2" />
                <div className="flex items-center gap-2">
                  <span className="relative flex h-2 w-2 mr-1">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                  <span className="text-xs font-bold text-emerald-500 uppercase tracking-widest">Live</span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <div className="flex bg-black/40 rounded-lg border border-white/5 p-1 mr-2">
                  {["1D", "1W", "1M", "3M", "1Y", "ALL"].map(p => (
                    <button
                      key={p}
                      onClick={() => setPeriod(p)}
                      className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all ${
                        period === p ? "bg-slate-800 text-white" : "text-slate-500 hover:text-slate-300"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
                
                <button 
                  onClick={() => setIsFullscreen(!isFullscreen)}
                  className="p-2 rounded-lg text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
                  title="Toggle Fullscreen"
                >
                  {isFullscreen ? <Minimize size={16} /> : <Maximize size={16} />}
                </button>
                <button 
                  onClick={handleForceSync}
                  disabled={syncing}
                  className="flex items-center gap-2 bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500 hover:text-white px-4 py-2 rounded-lg text-xs font-bold transition-colors border border-indigo-500/30 disabled:opacity-50"
                >
                  <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
                  {syncing ? "Syncing..." : "Force Sync"}
                </button>
              </div>
            </div>
            
            <div className="relative" style={{ height: isFullscreen ? 'calc(100vh - 100px)' : '480px' }}>
              <div ref={chartContainerRef} className="w-full h-full" />
              
              {/* Intraday Floating Tooltip */}
              {tooltipData && (
                <div className="absolute top-4 left-4 z-10 bg-[#0a0a0a]/90 backdrop-blur-md border border-white/10 p-3 rounded-xl shadow-2xl flex gap-5 text-[10px] font-mono pointer-events-none tracking-widest uppercase">
                  <div className="text-indigo-300 font-bold">{new Date(tooltipData.time * 1000).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit'})}</div>
                  <div className="text-slate-500">O <span className="text-white ml-1">{tooltipData.open?.toFixed(2)}</span></div>
                  <div className="text-slate-500">H <span className="text-white ml-1">{tooltipData.high?.toFixed(2)}</span></div>
                  <div className="text-slate-500">L <span className="text-white ml-1">{tooltipData.low?.toFixed(2)}</span></div>
                  <div className="text-slate-500">C <span className="text-white ml-1">{tooltipData.close?.toFixed(2)}</span></div>
                  <div className="text-slate-500">V <span className="text-white ml-1">{(tooltipData.volume / 1000).toFixed(1)}k</span></div>
                </div>
              )}
            </div>
          </div>

          {/* SECTION 2B - Real-Time Analysis Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            
            {/* Real-Time Fundamentals */}
            <div className="bg-white/[0.02] border border-white/[0.05] p-6 lg:p-8 rounded-3xl shadow-2xl backdrop-blur-xl">
              <div className="flex justify-between items-center mb-8">
                <h3 className="text-lg font-light text-white tracking-wide flex items-center gap-3">
                    <div className="p-2 bg-indigo-500/10 rounded-lg"><Layers size={18} className="text-indigo-400" /></div>
                    Fundamental Snapshot
                </h3>
                <span className="flex h-2 w-2 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
                </span>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-black/30 p-5 rounded-2xl border border-white/5 hover:border-white/10 transition-colors">
                    <div className="text-[10px] text-slate-500 mb-2 font-mono uppercase tracking-widest flex items-center gap-2"><Info size={12}/> Market Cap</div>
                    <div className={`text-xl font-mono transition-colors duration-300 ${livePrice ? 'text-white' : 'text-slate-400'}`}>
                        ${displayMcap ? (displayMcap / 1e9).toFixed(2) + "B" : "N/A"}
                    </div>
                </div>
                <div className="bg-black/30 p-5 rounded-2xl border border-white/5 hover:border-white/10 transition-colors">
                    <div className="text-[10px] text-slate-500 mb-2 font-mono uppercase tracking-widest flex items-center gap-2"><ActivitySquare size={12}/> 24h Volume</div>
                    <div className={`text-xl font-mono transition-colors duration-300 ${liveVolume24h > 0 ? 'text-white' : 'text-slate-400'}`}>
                        ${liveVolume24h > 0 ? (liveVolume24h / 1e6).toFixed(2) + "M" : "Loading..."}
                    </div>
                </div>
                <div className="bg-black/30 p-5 rounded-2xl border border-white/5 hover:border-white/10 transition-colors">
                    <div className="text-[10px] text-slate-500 mb-2 font-mono uppercase tracking-widest flex items-center gap-2"><CircleDot size={12}/> Circ. Supply</div>
                    <div className={`text-xl font-mono transition-colors duration-300 ${circSupply > 0 ? 'text-white' : 'text-slate-400'}`}>
                        {circSupply > 0 ? (circSupply / 1e6).toFixed(2) + "M" : "Loading..."}
                    </div>
                </div>
                <div className="bg-black/30 p-5 rounded-2xl border border-white/5 hover:border-white/10 transition-colors">
                    <div className="text-[10px] text-slate-500 mb-2 font-mono uppercase tracking-widest flex items-center gap-2"><TrendingUp size={12}/> All-Time High</div>
                    <div className={`text-xl font-mono transition-colors duration-300 ${liveATH > 0 ? 'text-white' : 'text-slate-400'}`}>
                        ${liveATH > 0 ? liveATH.toFixed(2) : "Loading..."}
                    </div>
                </div>
              </div>
            </div>

            {/* Real-Time Technical Analysis */}
            <div className="bg-white/[0.02] border border-white/[0.05] p-6 lg:p-8 rounded-3xl shadow-2xl backdrop-blur-xl">
              <div className="flex justify-between items-center mb-8">
                <h3 className="text-lg font-light text-white tracking-wide flex items-center gap-3">
                    <div className="p-2 bg-emerald-500/10 rounded-lg"><Activity size={18} className="text-emerald-400" /></div>
                    Technical Indicators
                </h3>
                <span className="flex h-2 w-2 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
              </div>
              
              <div className="space-y-4">
                  <div className="flex justify-between items-center bg-black/30 p-4 rounded-2xl border border-white/5">
                      <span className="text-xs text-slate-500 uppercase tracking-widest font-mono">RSI (14)</span>
                      <div className="flex items-center gap-4">
                          <span className="font-mono text-white text-lg">{liveRSI.toFixed(2)}</span>
                          <DirectionBadge dir={liveRSI > 60 ? "down" : liveRSI < 40 ? "up" : "neutral"} />
                      </div>
                  </div>
                  <div className="flex justify-between items-center bg-black/30 p-4 rounded-2xl border border-white/5">
                      <span className="text-xs text-slate-500 uppercase tracking-widest font-mono">MACD Div</span>
                      <div className="flex items-center gap-4">
                          <span className="font-mono text-white text-lg">{liveMACD.toFixed(4)}</span>
                          <DirectionBadge dir={liveMACD > 0 ? "up" : "down"} />
                      </div>
                  </div>
                  <div className="flex justify-between items-center bg-black/30 p-4 rounded-2xl border border-white/5">
                      <span className="text-xs text-slate-500 uppercase tracking-widest font-mono">Volatility (BB)</span>
                      <div className="flex items-center gap-4">
                          <span className="font-mono text-white text-lg">{liveBB.width.toFixed(4)}</span>
                          <VolatilityChip regime={liveBB.width > 0.1 ? "high" : liveBB.width > 0.05 ? "medium" : "low"} />
                      </div>
                  </div>
              </div>
            </div>
          </div>
          
          {/* SECTION 3 - Chart Overlay Toggles */}
          <div className="space-y-4">
            <div className="flex gap-4">
              <button 
                onClick={() => setShowRSI(!showRSI)}
                className={`px-5 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest border transition-all ${
                  showRSI ? "border-indigo-500 text-indigo-300 bg-indigo-500/10 shadow-[0_0_15px_rgba(99,102,241,0.2)]" : "border-white/10 text-slate-500 hover:border-white/20 hover:text-slate-300"
                }`}
              >
                Toggle Chart RSI
              </button>
              <button 
                onClick={() => setShowBB(!showBB)}
                className={`px-5 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest border transition-all ${
                  showBB ? "border-indigo-500 text-indigo-300 bg-indigo-500/10 shadow-[0_0_15px_rgba(99,102,241,0.2)]" : "border-white/10 text-slate-500 hover:border-white/20 hover:text-slate-300"
                }`}
              >
                Toggle Chart BB
              </button>
            </div>
            
            {showRSI && (
              <div className="bg-white/[0.02] border border-white/[0.05] p-6 rounded-3xl shadow-2xl backdrop-blur-xl">
                <h3 className="text-xs font-mono uppercase tracking-widest text-slate-500 mb-4">Relative Strength Index History (14)</h3>
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={ohlcv.map((d:any, i:number) => ({ time: d.time, rsi: calculateRSI(ohlcv.map((x:any)=>x.close).slice(0, i+1), 14) }))}>
                      <XAxis dataKey="time" hide />
                      <YAxis domain={[0, 100]} hide />
                      <RechartsTooltip 
                        contentStyle={{ backgroundColor: "#0a0a0a", borderColor: "rgba(255,255,255,0.1)", borderRadius: "8px", fontFamily: "monospace", fontSize: "10px" }} 
                        labelFormatter={(label) => new Date(label * 1000).toLocaleString()}
                      />
                      <ReferenceLine y={70} stroke="#f43f5e" strokeDasharray="3 3" label={{ value: "Overbought", fill: "#f43f5e", position: "insideTopLeft", fontSize: 10, fontFamily: "monospace" }} />
                      <ReferenceLine y={30} stroke="#10b981" strokeDasharray="3 3" label={{ value: "Oversold", fill: "#10b981", position: "insideBottomLeft", fontSize: 10, fontFamily: "monospace" }} />
                      <Area type="monotone" dataKey="rsi" stroke="#818cf8" fill="#818cf8" fillOpacity={0.1} strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </div>
          
          {/* SECTION 4 - Two Column Grid (History & Correlations) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            
            {/* LEFT COLUMN: Prediction History */}
            <div className="bg-white/[0.02] border border-white/[0.05] p-6 lg:p-8 rounded-3xl shadow-2xl backdrop-blur-xl">
              <div className="flex justify-between items-center mb-8">
                <h3 className="text-lg font-light text-white tracking-wide">Prediction History</h3>
                <div className="flex items-center gap-3">
                  <span className="text-2xl font-mono font-bold text-indigo-400">{history.summary.accuracy_pct.toFixed(0)}%</span>
                  <span className="text-[10px] uppercase tracking-widest text-slate-500">accuracy</span>
                </div>
              </div>
              
              <div className="space-y-3 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
                {history.predictions.map((p: any, i: number) => (
                  <div key={i} className={`flex items-center justify-between p-4 rounded-2xl border ${i % 2 === 0 ? "bg-black/30 border-white/5" : "bg-transparent border-transparent"}`}>
                    <div className="flex items-center gap-4">
                      <span className="text-xs font-mono text-slate-500 w-24">{p.date}</span>
                      <div className="w-24"><DirectionBadge dir={p.direction} /></div>
                      <span className="text-[10px] font-mono text-slate-500 w-12">{p.confidence ? p.confidence.toFixed(0) : 0}%</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className={`text-sm font-mono font-bold ${p.actual_return > 0 ? "text-emerald-400" : p.actual_return < 0 ? "text-red-400" : "text-slate-500"}`}>
                        {p.actual_return !== null ? (p.actual_return > 0 ? "+" : "") + (p.actual_return * 100).toFixed(2) + "%" : "-"}
                      </span>
                      <div className="w-6 text-center text-lg">
                        {p.was_correct === true && "✅"}
                        {p.was_correct === false && "❌"}
                        {p.was_correct === null && "⏳"}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            
            {/* RIGHT COLUMN: Correlated Coins */}
            <div className="bg-white/[0.02] border border-white/[0.05] p-6 lg:p-8 rounded-3xl shadow-2xl backdrop-blur-xl">
              <h3 className="text-lg font-light text-white tracking-wide mb-2">Matrix Correlations</h3>
              <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-8 font-mono">
                Asset relationship structural mapping
              </p>
              
              <div className="space-y-3">
                {correlations?.map((c: any, i: number) => (
                  <Link href={`/coin/${c.symbol}`} key={c.symbol} className="flex items-center justify-between p-3 hover:bg-black/40 rounded-2xl border border-transparent hover:border-white/5 transition-all group">
                    <div className="flex items-center gap-4 w-1/3">
                      <span className="text-xs text-slate-600 font-mono">{i + 1}</span>
                      <span className="font-mono font-bold text-white group-hover:text-indigo-400 transition-colors">{c.symbol}</span>
                    </div>
                    
                    <div className="flex-1 flex items-center px-4">
                      <div className="w-full bg-black/50 h-1.5 rounded-full overflow-hidden flex relative">
                        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-white/20 z-10" />
                        {c.correlation > 0 ? (
                          <div className="h-full bg-emerald-500 absolute left-1/2" style={{ width: `${c.correlation * 50}%` }} />
                        ) : (
                          <div className="h-full bg-red-500 absolute right-1/2" style={{ width: `${Math.abs(c.correlation) * 50}%` }} />
                        )}
                      </div>
                    </div>
                    
                    <div className="flex items-center justify-end gap-4 w-1/4">
                      <span className={`text-xs font-mono font-bold ${c.correlation > 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {c.correlation > 0 ? "+" : ""}{c.correlation.toFixed(2)}
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </div>
          
      </div>
    </div>
  );
}
