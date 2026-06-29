"use client";

import { useEffect, useState, useRef, use } from "react";
import { useChartPalette } from "@/lib/useChartPalette";
import { createChart, ColorType, IChartApi } from "lightweight-charts";
import { AreaChart, Area, ComposedChart, Line, Bar, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, ReferenceLine, Cell } from "recharts";
import { ChevronRight, RefreshCw, Maximize, Minimize, Brain, Layers, Activity, ActivitySquare, ShieldAlert, CircleDot, Info, TrendingUp, TrendingDown } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { GlassCard } from "@/components/ui/GlassCard";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_BASE = BASE.replace(/^http/, "ws");

function DirectionBadge({ dir }: { dir: string }) {
  const config: Record<string, {bg: string, text: string, label: string, border: string, shadow: string}> = {
    strong_up:   {bg:"bg-success/10",  text:"text-success", label:"STRONG BUY", border:"border-success/30", shadow:"shadow-[0_0_10px_rgba(34,197,94,0.2)]"},
    up:          {bg:"bg-success/5",  text:"text-success", label:"BUY", border:"border-success/20", shadow:""},
    neutral:     {bg:"bg-white/5",   text:"text-text-muted",  label:"NEUTRAL", border:"border-white/10", shadow:""},
    down:        {bg:"bg-danger/5",    text:"text-danger",   label:"SELL", border:"border-danger/20", shadow:""},
    strong_down: {bg:"bg-danger/10",    text:"text-danger",   label:"STRONG SELL", border:"border-danger/30", shadow:"shadow-[0_0_10px_rgba(239,68,68,0.2)]"},
  }
  const c = config[dir] || config["neutral"]
  return (
    <span className={`inline-flex items-center justify-center px-3 py-1 rounded-sm text-[10px] font-black uppercase tracking-widest border ${c.bg} ${c.text} ${c.border} ${c.shadow}`}>
      {c.label}
    </span>
  )
}

function VolatilityChip({ regime }: { regime: string }) {
  const colors: Record<string,string> = {
    low:"bg-success/10 text-success border-success/20 shadow-[0_0_5px_rgba(34,197,94,0.2)]", 
    medium:"bg-accent/10 text-accent border-accent/20 shadow-[0_0_5px_rgba(var(--accent),0.2)]",
    high:"bg-orange-500/10 text-orange-400 border-orange-500/20 shadow-[0_0_5px_rgba(249,115,22,0.2)]", 
    extreme:"bg-danger/10 text-danger border-danger/20 shadow-[0_0_5px_rgba(239,68,68,0.2)]"
  }
  return (
    <span className={`px-2 py-0.5 rounded-sm text-[10px] border font-black uppercase tracking-widest ${colors[regime] || colors.medium}`}>
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


export default function CoinDetailPage({ params }: { params: Promise<{ symbol: string }> }) {
  const palette = useChartPalette();
  
  const resolvedParams = use(params);
  const symbol = resolvedParams.symbol.toUpperCase();
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
  const [liveVolume24h, setLiveVolume24h] = useState<number | null>(null);
  const [liveMarketCap, setLiveMarketCap] = useState<number | null>(null);
  const [livePriceChangePct, setLivePriceChangePct] = useState<number | null>(null);
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
  
  // ATH from chart
  useEffect(() => {
    if (ohlcv && ohlcv.length > 0) {
      const ath = Math.max(...ohlcv.map((d: any) => d.high));
      setLiveATH(ath);
    }
  }, [ohlcv]);

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
      if (volumeSeriesRef.current && data.volume) {
        // Here data.volume from WS might be total 24h vol, but the chart expects interval volume. 
        // For simplicity, we just leave it or use close/open color.
        volumeSeriesRef.current.update({
          time: data.time,
          value: data.volume,
          color: data.close >= data.open ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)",
        });
      }
      setLivePrice(data.close);
      if (data.volume) setLiveVolume24h(data.volume);
      if (data.market_cap_usd) setLiveMarketCap(data.market_cap_usd);
      if (data.price_change_24h_pct !== undefined) setLivePriceChangePct(data.price_change_24h_pct);
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
        textColor: palette.muted,
      },
      grid: {
        vertLines: { color: `${palette.muted}15` },
        horzLines: { color: `${palette.muted}15` },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: `${palette.muted}25` },
      timeScale: { borderColor: `${palette.muted}25`, timeVisible: true },
    });
    
    chartRef.current = chart;
    
    const series = chartType === 'candlestick' ? chart.addCandlestickSeries({
      upColor:   "rgb(34, 197, 94)",
      downColor: "rgb(239, 68, 68)",
      borderUpColor:   "rgb(34, 197, 94)",
      borderDownColor: "rgb(239, 68, 68)",
      wickUpColor:   "rgb(34, 197, 94)",
      wickDownColor: "rgb(239, 68, 68)",
    }) : chart.addLineSeries({
      color: "rgb(212, 165, 71)",
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
      color: "rgba(212, 165, 71, 0.2)",
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    
    volumeSeries.setData(ohlcv.map((d: any) => ({
      time:  d.time,
      value: d.volume,
      color: d.close >= d.open ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)",
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
        const upperLine = chart.addLineSeries({ color: "rgba(212, 165, 71, 0.8)", lineWidth: 1, lineStyle: 2 });
        upperLine.setData(upperData);
        const lowerLine = chart.addLineSeries({ color: "rgba(212, 165, 71, 0.8)", lineWidth: 1, lineStyle: 2 });
        lowerLine.setData(lowerData);
        const middleLine = chart.addLineSeries({ color: "rgba(255,255,255,0.5)", lineWidth: 1 });
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
  }, [ohlcv, showBB, chartType, isFullscreen, palette.muted]); 
  
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
    <div className="h-[50vh] flex flex-col items-center justify-center space-y-6">
      <div className="text-text bg-surface/30 p-6 rounded-sm border border-white/10 font-mono text-center flex flex-col items-center gap-4 shadow-inner">
          <RefreshCw size={32} className="text-accent animate-spin" />
          <p className="uppercase tracking-widest text-[10px] font-bold text-text-muted">Loading Asset Profile...</p>
      </div>
    </div>
  );
  
  const latestOhlcv = ohlcv[ohlcv.length - 1];
  const displayPrice = livePrice !== null ? livePrice : latestOhlcv?.close;
  const changePct = livePriceChangePct !== null ? livePriceChangePct : (ohlcv.length > 1 ? ((displayPrice - ohlcv[ohlcv.length - 2].close) / ohlcv[ohlcv.length - 2].close) * 100 : 0);
  const latestPred = history.predictions[0] || {};
  
  // Realtime Market Cap & Supply Scaling
  let displayMcap = liveMarketCap !== null ? liveMarketCap : asset?.market_cap_usd;
  let circSupply = 0;
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
    <div className="space-y-6 min-h-screen pb-12 p-6 glass-2 rounded-2xl overflow-hidden relative">
      
      {/* Subtle Glow Backgrounds */}
      <div className="absolute top-0 right-0 w-[600px] h-[600px] bg-accent/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute top-[40%] left-[-100px] w-[500px] h-[500px] bg-success/5 rounded-full blur-[100px] pointer-events-none" />

      {/* Breadcrumb Navigation */}
      <div className="flex items-center text-[10px] font-mono font-bold text-text-muted uppercase tracking-widest mb-2 relative z-10 pt-4 max-w-[1600px] mx-auto px-4">
        <Link href="/market" className="hover:text-accent transition-colors">Market Data</Link>
        <ChevronRight size={14} className="mx-2 text-white/20" />
        <span className="text-text">{symbol}</span>
      </div>

      <div className="max-w-[1600px] mx-auto px-4 relative z-10 space-y-6">
          {/* SECTION 1 - Header */}
          <GlassCard tier={2} shape="none" className="rounded-xl p-6 lg:p-8 flex flex-col gap-4 overflow-visible">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
              <div className="flex flex-col">
                <div className="flex items-center gap-4">
                  <h1 className="text-4xl lg:text-5xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted tracking-tight drop-shadow-sm">{symbol}</h1>
                  <span className="text-text-muted text-lg font-light tracking-wide">{asset?.name || symbol}</span>
                  {asset?.sector && (
                    <span className="glass bg-accent/10 border border-accent/20 text-[10px] px-2 py-1 rounded-sm text-accent uppercase font-black tracking-widest shadow-[0_0_10px_rgba(var(--accent),0.2)]">
                      {asset.sector}
                    </span>
                  )}
                </div>
                <div className="flex items-center mt-4 gap-4">
                    <div className={`text-4xl font-mono font-black tracking-tighter transition-colors duration-300 ${livePrice ? 'text-accent drop-shadow-[0_0_10px_rgba(var(--accent),0.3)]' : 'text-text'}`}>
                    ${displayPrice > 100 ? displayPrice.toFixed(2) : displayPrice.toFixed(4)}
                    </div>
                    <div className={`text-sm font-black flex items-center gap-1 ${changePct >= 0 ? "text-success drop-shadow-[0_0_5px_rgba(34,197,94,0.5)]" : "text-danger drop-shadow-[0_0_5px_rgba(239,68,68,0.5)]"}`}>
                    {changePct >= 0 ? <TrendingUp size={16}/> : <TrendingDown size={16}/>}
                    {Math.abs(changePct).toFixed(2)}% (24h)
                    </div>
                </div>
              </div>
              
              <div className="flex flex-col items-end gap-4 w-full md:w-auto">
                <Link 
                  href={`/predictions?symbol=${symbol}`}
                  className="glass bg-accent hover:bg-accent/90 text-white px-6 py-3 rounded-sm text-[10px] uppercase font-black tracking-widest transition-all shadow-[0_0_20px_rgba(var(--accent),0.4)] flex items-center gap-2 hover:scale-105 border border-white/20"
                >
                  <Brain size={16} /> Analyze in Prediction Studio
                </Link>
                <div className="flex items-center gap-4 glass bg-surface/50 border border-white/10 rounded-sm p-4 w-full md:w-auto justify-between shadow-inner">
                    <div className="flex items-center gap-3">
                        <span className="text-[9px] text-text-muted uppercase font-black tracking-widest">Latest Signal</span>
                        <DirectionBadge dir={latestPred.direction || "neutral"} />
                    </div>
                    <div className="w-px h-6 bg-white/10 hidden md:block" />
                    <div className="flex flex-col items-end">
                        <span className="text-[9px] text-text-muted uppercase tracking-widest mb-1.5 font-black">Confidence</span>
                        <div className="w-24 h-1.5 bg-black/50 rounded-full overflow-hidden border border-white/5">
                        <div 
                            className="h-full bg-accent shadow-[0_0_5px_rgba(var(--accent),0.5)]" 
                            style={{ width: `${latestPred.confidence || 0}%` }}
                        />
                        </div>
                    </div>
                </div>
              </div>
            </div>
          </GlassCard>
          
          {/* SECTION 2 - Main Chart */}
          <GlassCard tier={2} shape="none" className={`rounded-xl p-4 overflow-hidden ${isFullscreen ? 'fixed inset-0 z-50 rounded-none m-0 bg-background border-0 backdrop-blur-none' : ''}`}>
            
            {/* Chart Actions Toolbar */}
            <div className="flex flex-wrap justify-between items-center mb-4 gap-4 bg-surface/30 p-2 rounded-sm border border-white/5">
              <div className="flex gap-2 items-center">
                <div className="flex bg-black/40 rounded-sm border border-white/5 p-1 shadow-inner">
                  {["1m", "5m", "15m", "1h", "4h", "1d", "1w"].map(i => (
                    <button
                      key={i}
                      onClick={() => setIntervalState(i)}
                      className={`px-3 py-1.5 rounded-sm text-[10px] font-black uppercase tracking-widest transition-all ${
                        interval === i ? "bg-accent/20 text-accent border border-accent/30 shadow-[0_0_10px_rgba(var(--accent),0.2)]" : "text-text-muted hover:text-text hover:bg-white/5 border border-transparent"
                      }`}
                    >
                      {i}
                    </button>
                  ))}
                </div>
                
                <div className="w-px h-6 bg-white/10 mx-2" />
                
                <div className="flex bg-black/40 rounded-sm border border-white/5 p-1 shadow-inner">
                  <button 
                    onClick={() => setChartType('candlestick')}
                    className={`px-3 py-1.5 rounded-sm text-[10px] font-black uppercase tracking-widest transition-all ${chartType === 'candlestick' ? "bg-white/10 text-text border border-white/20" : "text-text-muted hover:bg-white/5 border border-transparent"}`}
                  >
                    Candles
                  </button>
                  <button 
                    onClick={() => setChartType('line')}
                    className={`px-3 py-1.5 rounded-sm text-[10px] font-black uppercase tracking-widest transition-all ${chartType === 'line' ? "bg-white/10 text-text border border-white/20" : "text-text-muted hover:bg-white/5 border border-transparent"}`}
                  >
                    Line
                  </button>
                </div>
                <div className="w-px h-6 bg-white/10 mx-2" />
                <div className="flex items-center gap-2 px-2">
                  <span className="relative flex h-2 w-2 mr-1">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success/80"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-success shadow-[0_0_5px_rgba(34,197,94,0.8)]"></span>
                  </span>
                  <span className="text-[10px] font-black text-success uppercase tracking-widest drop-shadow-[0_0_5px_rgba(34,197,94,0.5)]">Live</span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <div className="flex bg-black/40 rounded-sm border border-white/5 p-1 shadow-inner mr-2">
                  {["1D", "1W", "1M", "3M", "1Y", "ALL"].map(p => (
                    <button
                      key={p}
                      onClick={() => setPeriod(p)}
                      className={`px-3 py-1.5 rounded-sm text-[10px] font-black uppercase tracking-widest transition-all ${
                        period === p ? "bg-white/10 text-text border border-white/20" : "text-text-muted hover:text-text border border-transparent"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
                
                <button 
                  onClick={() => setIsFullscreen(!isFullscreen)}
                  className="p-2 rounded-sm text-text-muted hover:bg-white/10 hover:text-text transition-colors border border-transparent hover:border-white/10"
                  title="Toggle Fullscreen"
                >
                  {isFullscreen ? <Minimize size={14} /> : <Maximize size={14} />}
                </button>
                <button 
                  onClick={handleForceSync}
                  disabled={syncing}
                  className="flex items-center gap-2 glass bg-accent/10 text-accent hover:bg-accent hover:text-white px-4 py-2 rounded-sm text-[10px] font-black uppercase tracking-widest transition-colors border border-accent/30 disabled:opacity-50"
                >
                  <RefreshCw size={12} className={syncing ? "animate-spin" : ""} />
                  {syncing ? "Syncing..." : "Force Sync"}
                </button>
              </div>
            </div>
            
            <div className="relative border border-white/5 rounded-sm bg-black/20 p-2" style={{ height: isFullscreen ? 'calc(100vh - 100px)' : '480px' }}>
              <div ref={chartContainerRef} className="w-full h-full" />
              
              {/* Intraday Floating Tooltip */}
              {tooltipData && (
                <div className="absolute top-4 left-4 z-10 glass bg-surface/90 backdrop-blur-xl border border-white/10 p-4 rounded-sm shadow-2xl flex gap-6 text-[10px] font-mono pointer-events-none tracking-widest uppercase font-bold">
                  <div className="text-accent drop-shadow-[0_0_5px_rgba(var(--accent),0.5)]">{new Date(tooltipData.time * 1000).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit'})}</div>
                  <div className="text-text-muted">O <span className="text-text ml-1">{tooltipData.open?.toFixed(2)}</span></div>
                  <div className="text-text-muted">H <span className="text-text ml-1">{tooltipData.high?.toFixed(2)}</span></div>
                  <div className="text-text-muted">L <span className="text-text ml-1">{tooltipData.low?.toFixed(2)}</span></div>
                  <div className="text-text-muted">C <span className="text-text ml-1">{tooltipData.close?.toFixed(2)}</span></div>
                  <div className="text-text-muted">V <span className="text-text ml-1">{(tooltipData.volume / 1000).toFixed(1)}k</span></div>
                </div>
              )}
            </div>
          </GlassCard>

          {/* SECTION 2B - Real-Time Analysis Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            
            {/* Real-Time Fundamentals */}
            <GlassCard tier={2} shape="none" className="rounded-xl p-8 relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-6 opacity-10 group-hover:opacity-20 transition-opacity">
                  <Layers size={100} className="text-text-muted" />
              </div>
              <div className="flex justify-between items-center mb-8 relative z-10">
                <h3 className="text-xl font-black text-text tracking-tight flex items-center gap-3">
                    <div className="p-2 glass bg-white/5 rounded-sm border border-white/10 shadow-inner"><Layers size={18} className="text-text" /></div>
                    Fundamental Snapshot
                </h3>
                <span className="flex h-2 w-2 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent/80"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-accent shadow-[0_0_5px_rgba(var(--accent),0.8)]"></span>
                </span>
              </div>
              <div className="grid grid-cols-2 gap-4 relative z-10">
                <div className="glass bg-black/40 p-5 rounded-sm border border-white/5 hover:border-white/20 transition-colors shadow-inner">
                    <div className="text-[9px] text-text-muted mb-2 font-mono font-black uppercase tracking-widest flex items-center gap-2"><Info size={12}/> Market Cap</div>
                    <div className={`text-2xl font-mono font-black tracking-tighter transition-colors duration-300 ${livePrice ? 'text-text' : 'text-text-muted'}`}>
                        ${displayMcap ? (displayMcap / 1e9).toFixed(2) + "B" : "N/A"}
                    </div>
                </div>
                <div className="glass bg-black/40 p-5 rounded-sm border border-white/5 hover:border-white/20 transition-colors shadow-inner">
                    <div className="text-[9px] text-text-muted mb-2 font-mono font-black uppercase tracking-widest flex items-center gap-2"><ActivitySquare size={12}/> 24h Volume</div>
                    <div className={`text-2xl font-mono font-black tracking-tighter transition-colors duration-300 ${(liveVolume24h !== null && liveVolume24h > 0) ? 'text-text' : 'text-text-muted'}`}>
                        ${(liveVolume24h !== null && liveVolume24h > 0) ? (liveVolume24h / 1e6).toFixed(2) + "M" : "Loading..."}
                    </div>
                </div>
                <div className="glass bg-black/40 p-5 rounded-sm border border-white/5 hover:border-white/20 transition-colors shadow-inner">
                    <div className="text-[9px] text-text-muted mb-2 font-mono font-black uppercase tracking-widest flex items-center gap-2"><CircleDot size={12}/> Circ. Supply</div>
                    <div className={`text-2xl font-mono font-black tracking-tighter transition-colors duration-300 ${circSupply > 0 ? 'text-text' : 'text-text-muted'}`}>
                        {circSupply > 0 ? (circSupply / 1e6).toFixed(2) + "M" : "Loading..."}
                    </div>
                </div>
                <div className="glass bg-black/40 p-5 rounded-sm border border-white/5 hover:border-white/20 transition-colors shadow-inner">
                    <div className="text-[9px] text-text-muted mb-2 font-mono font-black uppercase tracking-widest flex items-center gap-2"><TrendingUp size={12}/> All-Time High</div>
                    <div className={`text-2xl font-mono font-black tracking-tighter transition-colors duration-300 ${liveATH > 0 ? 'text-text' : 'text-text-muted'}`}>
                        ${liveATH > 0 ? liveATH.toFixed(2) : "Loading..."}
                    </div>
                </div>
              </div>
            </GlassCard>

            {/* Real-Time Technical Analysis */}
            <GlassCard tier={2} shape="none" className="rounded-xl p-8 relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-6 opacity-10 group-hover:opacity-20 transition-opacity">
                  <Activity size={100} className="text-text-muted" />
              </div>
              <div className="flex justify-between items-center mb-8 relative z-10">
                <h3 className="text-xl font-black text-text tracking-tight flex items-center gap-3">
                    <div className="p-2 glass bg-success/10 rounded-sm border border-success/20 shadow-inner"><Activity size={18} className="text-success drop-shadow-[0_0_5px_currentColor]" /></div>
                    Technical Indicators
                </h3>
                <span className="flex h-2 w-2 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success/80"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-success shadow-[0_0_5px_rgba(34,197,94,0.8)]"></span>
                </span>
              </div>
              
              <div className="space-y-4 relative z-10">
                  <div className="flex justify-between items-center glass bg-black/40 p-4 rounded-sm border border-white/5 hover:border-white/20 transition-colors shadow-inner">
                      <span className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-black">RSI (14)</span>
                      <div className="flex items-center gap-4">
                          <span className="font-mono font-black text-text text-xl">{liveRSI.toFixed(2)}</span>
                          <DirectionBadge dir={liveRSI > 60 ? "down" : liveRSI < 40 ? "up" : "neutral"} />
                      </div>
                  </div>
                  <div className="flex justify-between items-center glass bg-black/40 p-4 rounded-sm border border-white/5 hover:border-white/20 transition-colors shadow-inner">
                      <span className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-black">MACD Div</span>
                      <div className="flex items-center gap-4">
                          <span className="font-mono font-black text-text text-xl">{liveMACD.toFixed(4)}</span>
                          <DirectionBadge dir={liveMACD > 0 ? "up" : "down"} />
                      </div>
                  </div>
                  <div className="flex justify-between items-center glass bg-black/40 p-4 rounded-sm border border-white/5 hover:border-white/20 transition-colors shadow-inner">
                      <span className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-black">Volatility (BB)</span>
                      <div className="flex items-center gap-4">
                          <span className="font-mono font-black text-text text-xl">{liveBB.width.toFixed(4)}</span>
                          <VolatilityChip regime={liveBB.width > 0.1 ? "high" : liveBB.width > 0.05 ? "medium" : "low"} />
                      </div>
                  </div>
              </div>
            </GlassCard>
          </div>
          
          {/* SECTION 3 - Chart Overlay Toggles */}
          <div className="space-y-4">
            <div className="flex gap-4">
              <button 
                onClick={() => setShowRSI(!showRSI)}
                className={`px-5 py-2.5 rounded-sm text-[10px] font-black uppercase tracking-widest border transition-all ${
                  showRSI ? "border-accent/50 text-accent glass bg-accent/10 shadow-[0_0_15px_rgba(var(--accent),0.2)]" : "border-white/10 text-text-muted hover:border-white/20 hover:text-text glass bg-surface/30"
                }`}
              >
                Toggle Chart RSI
              </button>
              <button 
                onClick={() => setShowBB(!showBB)}
                className={`px-5 py-2.5 rounded-sm text-[10px] font-black uppercase tracking-widest border transition-all ${
                  showBB ? "border-accent/50 text-accent glass bg-accent/10 shadow-[0_0_15px_rgba(var(--accent),0.2)]" : "border-white/10 text-text-muted hover:border-white/20 hover:text-text glass bg-surface/30"
                }`}
              >
                Toggle Chart BB
              </button>
            </div>
            
            {showRSI && (
              <GlassCard tier={2} shape="none" className="rounded-xl p-6 overflow-hidden">
                <h3 className="text-[10px] font-mono font-black uppercase tracking-widest text-text-muted mb-4">Relative Strength Index History (14)</h3>
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={ohlcv.map((d:any, i:number) => ({ time: d.time, rsi: calculateRSI(ohlcv.map((x:any)=>x.close).slice(0, i+1), 14) }))}>
                      <XAxis dataKey="time" hide />
                      <YAxis domain={[0, 100]} hide />
                      <RechartsTooltip 
                        contentStyle={{ backgroundColor: "rgba(var(--background), 0.9)", borderColor: "rgba(var(--text), 0.1)", borderRadius: "8px", fontFamily: "monospace", fontSize: "10px", fontWeight: "bold" }} 
                        labelFormatter={(label) => new Date(label * 1000).toLocaleString()}
                      />
                      <ReferenceLine y={70} stroke={palette.danger} strokeDasharray="3 3" label={{ value: "OVERBOUGHT", fill: "rgba(239,68,68,0.8)", position: "insideTopLeft", fontSize: 9, fontFamily: "sans-serif", fontWeight: "bold", letterSpacing: "0.1em" }} />
                      <ReferenceLine y={30} stroke={palette.success} strokeDasharray="3 3" label={{ value: "OVERSOLD", fill: "rgba(34,197,94,0.8)", position: "insideBottomLeft", fontSize: 9, fontFamily: "sans-serif", fontWeight: "bold", letterSpacing: "0.1em" }} />
                      <Area type="monotone" dataKey="rsi" stroke="rgb(212, 165, 71)" fill="rgba(212, 165, 71, 0.1)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </GlassCard>
            )}
          </div>
          
          {/* SECTION 4 - Two Column Grid (History & Correlations) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            
            {/* LEFT COLUMN: Prediction History */}
            <GlassCard tier={2} shape="none" className="rounded-xl p-0 overflow-hidden flex flex-col">
              <div className="p-8 border-b border-white/5 bg-surface/30">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="text-xl font-black text-text tracking-tight">Prediction History</h3>
                    <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-1">AI signal accuracy audit log</p>
                  </div>
                  <div className="flex items-center gap-3 bg-black/40 px-4 py-2 rounded-sm border border-white/5">
                    <span className="text-2xl font-mono font-black text-accent drop-shadow-[0_0_10px_rgba(var(--accent),0.5)]">{history.summary.accuracy_pct.toFixed(0)}%</span>
                    <span className="text-[8px] uppercase tracking-widest font-black text-text-muted">accuracy</span>
                  </div>
                </div>
              </div>
              
              <div className="flex-1 p-8">
                <div className="space-y-3 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
                  {history.predictions.map((p: any, i: number) => (
                    <div key={i} className={`flex items-center justify-between p-4 rounded-sm border transition-colors ${i % 2 === 0 ? "glass bg-black/30 border-white/5 hover:border-white/10" : "bg-transparent border-transparent hover:bg-white/[0.02]"}`}>
                      <div className="flex items-center gap-4">
                        <span className="text-[10px] font-mono font-bold text-text-muted w-28">{p.date}</span>
                        <div className="w-28"><DirectionBadge dir={p.direction} /></div>
                        <span className="text-[10px] font-mono font-black text-text-muted/60 w-12">{p.confidence ? p.confidence.toFixed(0) : 0}%</span>
                      </div>
                      <div className="flex items-center gap-4">
                        <span className={`text-sm font-mono font-black ${p.actual_return > 0 ? "text-success drop-shadow-[0_0_5px_rgba(34,197,94,0.5)]" : p.actual_return < 0 ? "text-danger drop-shadow-[0_0_5px_rgba(239,68,68,0.5)]" : "text-text-muted"}`}>
                          {p.actual_return !== null ? (p.actual_return > 0 ? "+" : "") + (p.actual_return * 100).toFixed(2) + "%" : "-"}
                        </span>
                        <div className="w-6 text-center text-lg">
                          {p.was_correct === true && <span className="drop-shadow-[0_0_5px_rgba(34,197,94,0.5)]">✅</span>}
                          {p.was_correct === false && <span className="drop-shadow-[0_0_5px_rgba(239,68,68,0.5)]">❌</span>}
                          {p.was_correct === null && <span className="opacity-50">⏳</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </GlassCard>
            
            {/* RIGHT COLUMN: Correlated Coins */}
            <GlassCard tier={2} shape="none" className="rounded-xl p-0 overflow-hidden flex flex-col">
              <div className="p-8 border-b border-white/5 bg-surface/30">
                <h3 className="text-xl font-black text-text tracking-tight">Matrix Correlations</h3>
                <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-1">Asset relationship structural mapping</p>
              </div>
              
              <div className="flex-1 p-8">
                <div className="space-y-2">
                  {correlations?.map((c: any, i: number) => (
                    <Link href={`/coin/${c.symbol}`} key={c.symbol} className="flex items-center justify-between p-4 glass bg-surface/30 hover:bg-white/5 rounded-sm border border-white/5 hover:border-white/20 transition-all group shadow-inner">
                      <div className="flex items-center gap-4 w-1/3">
                        <span className="text-[10px] text-text-muted font-mono font-black opacity-50">#{String(i + 1).padStart(2, '0')}</span>
                        <span className="font-mono font-black text-text group-hover:text-accent transition-colors text-lg tracking-tight">{c.symbol}</span>
                      </div>
                      
                      <div className="flex-1 flex items-center px-6">
                        <div className="w-full bg-black/60 h-2 rounded-full overflow-hidden flex relative shadow-inner border border-white/5">
                          <div className="absolute left-1/2 top-0 bottom-0 w-px bg-white/20 z-10" />
                          {c.correlation > 0 ? (
                            <div className="h-full bg-success absolute left-1/2 shadow-[0_0_5px_rgba(34,197,94,0.8)]" style={{ width: `${c.correlation * 50}%` }} />
                          ) : (
                            <div className="h-full bg-danger absolute right-1/2 shadow-[0_0_5px_rgba(239,68,68,0.8)]" style={{ width: `${Math.abs(c.correlation) * 50}%` }} />
                          )}
                        </div>
                      </div>
                      
                      <div className="flex items-center justify-end gap-4 w-1/4">
                        <span className={`text-xs font-mono font-black tracking-tight ${c.correlation > 0 ? "text-success drop-shadow-[0_0_5px_rgba(34,197,94,0.5)]" : "text-danger drop-shadow-[0_0_5px_rgba(239,68,68,0.5)]"}`}>
                          {c.correlation > 0 ? "+" : ""}{c.correlation.toFixed(3)}
                        </span>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            </GlassCard>
          </div>
          
      </div>
    </div>
  );
}
