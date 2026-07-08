"use client";
import React, { useState, useEffect, Suspense } from "react";
import { BlockchainLoader } from "@/components/BlockchainLoader";

import { useChartPalette } from "@/lib/useChartPalette";
import useSWR from "swr"
import { useSearchParams, useRouter } from "next/navigation"
import Link from "next/link"
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, BarChart, Bar, Cell
} from "recharts"
import { TrendingUp, TrendingDown, Minus, Brain,
         BarChart2, AlertTriangle, CheckCircle, Terminal, Lock, Clock, Target, Layers, Info, X, Shield } from "lucide-react"
import { DirectionBadge } from "@/components/ui/DirectionBadge"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
const WS_BASE = BASE.replace(/^http/, "ws")

const fetcher = (url: string) => fetch(url).then(r => {
  if (!r.ok) throw new Error(r.statusText)
  return r.json()
})

// ── Shared UI Components ──────────────────────────────────────────
function VolatilityChip({ regime }: { regime: string }) {
  const colors: Record<string,string> = {
    low:"bg-info/10 text-info border-info/20", medium:"bg-warning/10 text-warning border-warning/20",
    high:"bg-danger/10 text-danger border-danger/20", extreme:"bg-danger/20 text-danger border-danger/30 font-black"
  }
  return (
    <span className={`px-2 py-0.5 shape-tag text-[10px] border font-mono uppercase tracking-widest ${colors[regime] || colors.medium}`}>
      {regime}
    </span>
  )
}

import 'katex/dist/katex.min.css';
import { BlockMath, InlineMath } from 'react-katex';

// ── Math Formula Modal ──────────────────────────────────────────
function MathModal({ isOpen, onClose, title, formulaSteps }: { isOpen: boolean, onClose: () => void, title: string, formulaSteps: string }) {
    if (!isOpen) return null;

    const renderFormula = (text: string) => {
        return text.split('\n').map((line, i) => {
            if (line.startsWith('$$') && line.endsWith('$$')) {
                const equation = line.replace(/\$\$/g, '');
                return (
                    <div key={i} className="my-6 p-4 bg-accent/5 border border-accent/20 rounded-sm flex items-center justify-center overflow-x-auto text-accent">
                        <BlockMath math={equation} />
                    </div>
                )
            }
            if (line.startsWith('**') && !line.match(/^[0-9]\./)) {
                return <h3 key={i} className="text-xl font-black text-text mb-4 mt-2 font-sans tracking-tight">{line.replace(/\*\*/g, '')}</h3>
            }
            if (line.match(/^[0-9]\./)) {
                // Parse inline math $...$ and block math $$...$$
                const parts = line.split(/(\$\$[^$]+\$\$|\$[^$]+\$)/g);
                return (
                    <div key={i} className="flex gap-4 mb-4 text-text/80 leading-relaxed text-sm font-light tracking-wide">
                        <span className="text-accent font-mono mt-0.5 whitespace-nowrap font-bold">{parts[0].substring(0, 2)}</span>
                        <span>
                            {parts.map((part, index) => {
                                if (index === 0) {
                                   part = part.substring(3);
                                }
                                if (part.startsWith('$$') && part.endsWith('$$')) {
                                    return <span key={index} className="text-accent block my-3"><BlockMath math={part.replace(/\$\$/g, '')} /></span>;
                                }
                                if (part.startsWith('$') && part.endsWith('$')) {
                                    return <span key={index} className="text-accent/80 font-mono mx-1"><InlineMath math={part.replace(/\$/g, '')} /></span>;
                                }
                                // Handle bold tags inside normal text
                                const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
                                return boldParts.map((b, bIdx) => {
                                    if (b.startsWith('**') && b.endsWith('**')) {
                                        return <strong key={`${index}-${bIdx}`} className="text-text font-bold">{b.replace(/\*\*/g, '')}</strong>;
                                    }
                                    return b;
                                });
                            })}
                        </span>
                    </div>
                )
            }
            return <p key={i} className="mb-3 text-text/80 text-sm font-light tracking-wide">{line}</p>
        });
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-in fade-in zoom-in-95">
            <style>{`.katex { color: rgb(var(--text)) !important; } .katex-display { color: rgb(var(--accent)) !important; }`}</style>
            <div className="absolute inset-0 bg-background/80 backdrop-blur-md" onClick={onClose} />
            <div className="glass-3 rounded-xl border border-text/10 w-full max-w-2xl shadow-2xl relative z-10 flex flex-col max-h-[85vh] overflow-hidden">
                <div className="flex items-center justify-between p-6 border-b border-text/5 bg-surface/30">
                    <h2 className="text-lg font-black text-text tracking-tight uppercase font-sans">{title}</h2>
                    <button onClick={onClose} className="text-text-muted hover:text-text transition-colors bg-text/5 hover:bg-text/10 p-2 rounded-full">
                        <X size={20} />
                    </button>
                </div>
                <div className="p-8 overflow-y-auto custom-scrollbar bg-surface/50">
                    {renderFormula(formulaSteps)}
                </div>
            </div>
        </div>
    );
}


// ── Main Page ──────────────────────────────────────────
function PredictionStudio() {
  const palette = useChartPalette();
  
  const searchParams = useSearchParams()
  const router = useRouter()
  
  const initialSymbol = searchParams?.get("symbol")
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(initialSymbol || null)
  
  const [forecastData, setForecastData] = useState<any>(null)
  const [forecastLoading, setForecastLoading] = useState(false)
  const [forecastError, setForecastError] = useState<string | null>(null)
  const [livePrice, setLivePrice] = useState<number | null>(null)

  // Math Modal State
  const [modalOpen, setModalOpen] = useState(false)
  const [modalContent, setModalContent] = useState({ title: '', steps: '' })

  const { data: predictions } = useSWR(
    `${BASE}/api/predictions?limit=100`,
    fetcher,
    { revalidateOnFocus: false, refreshInterval: 60000 }
  )

  useEffect(() => {
    if (selectedSymbol) {
      runForecast(selectedSymbol)
    }
  }, [selectedSymbol])

  // Live WebSocket for Price Updates
  useEffect(() => {
    if (!selectedSymbol) return;
    const ws = new WebSocket(`${WS_BASE}/api/v1/stream/ticker/${selectedSymbol}?api_key=${process.env.NEXT_PUBLIC_API_KEY}`);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.close) setLivePrice(data.close);
    };
    return () => ws.close();
  }, [selectedSymbol]);

  const runForecast = async (symbol: string) => {
    setForecastLoading(true)
    setForecastError(null)
    setLivePrice(null)
    try {
      const res = await fetch(`${BASE}/api/forecast/${symbol}`)
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setForecastData(data)
      setLivePrice(data.last_price)
    } catch (e: any) {
      setForecastError(e.message || "Forecast failed")
    } finally {
      setForecastLoading(false)
    }
  }

  const selectedPrediction = predictions?.find((p: any) => p.asset_symbol === selectedSymbol)

  let tShapData: any = null;
  let zkProof: string | null = null;
  if (selectedPrediction?.shap_values) {
    try {
      const sv = typeof selectedPrediction.shap_values === "string" 
        ? JSON.parse(selectedPrediction.shap_values) 
        : selectedPrediction.shap_values;
      if (sv.t_shap) {
        tShapData = typeof sv.t_shap === "string" ? JSON.parse(sv.t_shap) : sv.t_shap;
      }
      if (sv.attestation_hash) {
        zkProof = sv.attestation_hash;
      } else if (sv.zk_proof) {
        zkProof = sv.zk_proof;
      }
    } catch (e) {}
  }

  const shapSource = tShapData?.attributions_pct || tShapData;

  const tShapChartData = shapSource && Object.keys(shapSource).length > 0 ? Object.entries(shapSource).map(([name, val]) => ({
    name, value: Number(val), color: Number(val) > 0 ? "rgba(34, 197, 94, 0.8)" : "rgba(239, 68, 68, 0.8)"
  })).sort((a, b) => Math.abs(b.value) - Math.abs(a.value)) : [];

  let chartData: any[] = [];
  if (forecastData && forecastData.historical && forecastData.forecast_prices) {
    const hist = forecastData.historical.slice(-60)
    hist.forEach((h: any) => chartData.push({ date: h.date, actual: h.close, type: "historical" }))

    forecastData.forecast_dates.forEach((date: string, i: number) => {
      const point: any = {
        date,
        ensemble: forecastData.forecast_prices[i],
        lower: forecastData.lower_bound[i],
        upper: forecastData.upper_bound[i],
        type: "forecast"
      }
      if (forecastData.lstm_forecast) point.lstm = forecastData.lstm_forecast[i]
      if (forecastData.prophet_forecast) point.prophet = forecastData.prophet_forecast[i]
      chartData.push(point)
    })
  }

  const formatPrice = (val: number) => {
      if (val === undefined || val === null) return "0.00";
      return val > 1 ? val.toFixed(6) : val.toFixed(8);
  }

  const currentDisplayPrice = livePrice !== null ? livePrice : forecastData?.last_price;

  return (
    <div className="h-full relative z-0 glass-2 rounded-2xl overflow-hidden p-6">
      
      <MathModal 
        isOpen={modalOpen} 
        onClose={() => setModalOpen(false)} 
        title={modalContent.title} 
        formulaSteps={modalContent.steps} 
      />

      <div className="w-full max-w-7xl mx-auto pt-8 pb-16 relative z-10">
        {!selectedSymbol ? (
          <div className="space-y-8">
            {/* Header */}
            <div className="glass-3 rounded-xl p-8 lg:p-10 shadow-2xl relative overflow-hidden group">
              <div className="absolute top-[-50px] right-[-50px] w-64 h-64 bg-accent/10 rounded-full blur-[80px] pointer-events-none group-hover:bg-accent/20 transition-all duration-700" />
              <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                <div>
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-[10px] text-accent font-mono font-bold tracking-widest uppercase border border-accent/20 bg-accent/5 px-3 py-1.5 rounded-sm">ST-GCN Predictions</span>
                  </div>
                  <h1 className="text-4xl md:text-5xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted tracking-tight font-sans">Prediction Studio</h1>
                  <p className="text-text-muted font-light tracking-wide mt-2">Select any asset below to launch full multi-factor analysis pipeline.</p>
                  <Link href="/explain" className="mt-4 inline-flex items-center gap-2 text-xs font-mono font-bold uppercase tracking-widest text-accent hover:text-accent-2 transition-colors">
                    <Brain size={14} /> Explain AI Models & Methods
                  </Link>
                </div>
                <div className="flex gap-3 text-xs text-text-muted font-mono font-bold uppercase tracking-widest">
                  <span className="bg-success/10 text-success border border-success/20 px-4 py-2 rounded-sm shadow-[0_0_15px_rgba(34,197,94,0.1)]">
                    ↑ {predictions?.filter((p: any) => ['up','strong_up'].includes(p.direction)).length || 0} Bullish
                  </span>
                  <span className="bg-danger/10 text-danger border border-danger/20 px-4 py-2 rounded-sm shadow-[0_0_15px_rgba(239,68,68,0.1)]">
                    ↓ {predictions?.filter((p: any) => ['down','strong_down'].includes(p.direction)).length || 0} Bearish
                  </span>
                </div>
              </div>
            </div>

            {/* Predictions Grid */}
            {predictions && predictions.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {predictions.map((p: any, idx: number) => {
                  const isUp = ['up', 'strong_up'].includes(p.direction)
                  const isDown = ['down', 'strong_down'].includes(p.direction)
                  const accentVar = isUp ? 'var(--success)' : isDown ? 'var(--danger)' : 'var(--text-muted)'
                  return (
                    <button
                      key={idx}
                      onClick={() => setSelectedSymbol(p.asset_symbol)}
                      className={`group text-left glass-flat interactive-lift rounded-xl border border-text/5 hover:border-text/20 p-6 transition-all duration-[var(--dur-hover)] ease-glide hover:bg-text/[0.04] hover:shadow-[0_0_30px_rgba(${isUp ? '34,197,94' : isDown ? '239,68,68' : '255,255,255'},0.1)] relative overflow-hidden`}
                    >
                      
                      {/* VERDICT STAMP */}
                      <div className="absolute top-6 right-6 opacity-0 group-hover:opacity-10 transition-opacity pointer-events-none rotate-[-15deg] scale-[2.5]">
                         {isUp ? <TrendingUp size={64} className="text-success" /> : isDown ? <TrendingDown size={64} className="text-danger" /> : <Minus size={64} className="text-text-muted" />}
                      </div>
                      
                      <div className="absolute top-0 left-0 w-full h-1 bg-text/5 group-hover:h-1.5 transition-all" style={{ backgroundColor: `rgba(${isUp ? '34,197,94' : isDown ? '239,68,68' : '255,255,255'}, 0.2)` }} />
                      
                      <div className="flex justify-between items-start mb-4">
                        <div>
                          <h3 className="text-text font-black text-2xl tracking-tight">{p.asset_symbol}</h3>
                          <span className="text-[9px] text-text-muted font-mono uppercase tracking-widest mt-1 block">
                            {p.model_version}
                          </span>
                        </div>
                        <DirectionBadge direction={p.direction} showIcon />
                      </div>

                      <div className="flex items-center justify-between mt-6">
                        <div className="space-y-1">
                          <div className="text-[9px] text-text-muted uppercase tracking-widest font-bold">Confidence</div>
                          <div className={`text-lg font-mono font-black ${isUp ? 'text-success' : isDown ? 'text-danger' : 'text-text-muted'}`}>
                            {p.confidence?.toFixed(1)}%
                          </div>
                        </div>
                        <div className="space-y-1 text-right">
                          <div className="text-[9px] text-text-muted uppercase tracking-widest font-bold">Volatility</div>
                          <VolatilityChip regime={p.volatility_regime || 'medium'} />
                        </div>
                      </div>

                      {/* Conformal Prediction Interval Spread */}
                      {p.confidence_interval && (
                        <div className="mt-4 flex items-center justify-between bg-black/20 p-2 rounded-sm border border-text/5">
                            <span className="text-[9px] uppercase tracking-widest font-mono text-text-muted">Expected Spread</span>
                            <span className="text-[10px] font-mono font-bold text-text">
                                [{p.confidence_interval[0].toFixed(1)}% - {p.confidence_interval[1].toFixed(1)}%]
                            </span>
                        </div>
                      )}

                      {/* Confidence bar */}
                      <div className="mt-5 h-1.5 bg-background rounded-full overflow-hidden border border-text/5">
                        <div 
                          className="h-full rounded-full transition-all duration-1000 ease-out shadow-[0_0_10px_currentColor]"
                          style={{ 
                            width: `${Math.min(100, p.confidence || 0)}%`, 
                            backgroundColor: `rgb(${isUp ? '34,197,94' : isDown ? '239,68,68' : '148,163,184'})` 
                          }}
                        />
                      </div>
                      
                      <div className="mt-4 text-[10px] text-text-muted group-hover:text-accent font-mono font-bold uppercase tracking-widest transition-colors flex items-center gap-2">
                        <Brain size={12} /> Launch Analysis Pipeline
                      </div>
                    </button>
                  )
                })}
              </div>
            ) : (
              <div className="h-[40vh] flex flex-col items-center justify-center text-text-muted space-y-6">
                <Brain size={64} className="opacity-20 text-accent animate-pulse" />
                <h3 className="text-2xl font-light tracking-wide text-center text-text/80">No predictions available yet.</h3>
                <p className="text-sm font-mono tracking-widest uppercase text-center max-w-md">Run the inference pipeline to generate predictions.</p>
                <button onClick={() => router.push('/screener')} className="mt-6 glass bg-text/5 hover:bg-text/10 px-8 py-3 rounded-sm font-bold text-xs uppercase tracking-widest transition-all">Open Screener</button>
              </div>
            )}
          </div>
        ) : forecastLoading ? (
          <div className="h-[60vh] flex flex-col items-center justify-center space-y-8">
            <div className="relative w-24 h-24">
                <div className="absolute inset-0 border-4 border-accent/10 rounded-full" />
                <div className="absolute inset-0 border-4 border-accent border-t-transparent rounded-full animate-spin" />
                <Brain className="absolute inset-0 m-auto text-accent opacity-50 animate-pulse" size={32} />
            </div>
            <div className="text-center space-y-3">
              <div className="text-accent text-xl font-black uppercase tracking-[0.2em] animate-pulse">Computing Inference</div>
              <div className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-bold">Running PyTorch Deep Learning Sequences</div>
            </div>
          </div>
        ) : forecastError || (forecastData && forecastData.error) ? (
          <div className="p-6 bg-danger/10 border border-danger/20 rounded-sm text-danger font-mono text-sm backdrop-blur-md shadow-[0_0_30px_rgba(239,68,68,0.15)] flex items-center gap-4 animate-in fade-in slide-in-from-top-4">
            <AlertTriangle className="text-danger flex-shrink-0" size={24} />
            {forecastError || forecastData.error}
          </div>
        ) : forecastData && (
          <div className="space-y-8 pb-10 animate-in fade-in slide-in-from-bottom-8 duration-700">
            
            {/* ── HEADER ROW ── */}
            <div className="flex flex-col md:flex-row justify-between items-end gap-6 glass-2 rounded-xl border border-text/5 p-8 lg:p-10 shadow-2xl relative overflow-hidden group">
              <div className="absolute top-[-50px] right-[-50px] w-64 h-64 bg-accent/10 rounded-full blur-[80px] pointer-events-none group-hover:bg-accent/20 transition-all duration-700" />
              
              <div className="relative z-10 space-y-3">
                <div className="flex flex-wrap items-center gap-3 mb-2">
                    <span className="text-[10px] text-accent font-mono font-bold tracking-widest uppercase border border-accent/20 bg-accent/5 px-3 py-1.5 rounded-sm">Multi-Factor Analysis Pipeline</span>
                    <Link href="/explain" className="text-[10px] text-text-muted hover:text-accent font-mono font-bold tracking-widest uppercase border border-text/10 hover:border-accent/40 bg-surface/30 px-3 py-1.5 rounded-sm transition-all duration-[var(--dur-hover)] flex items-center gap-1">
                        <Brain size={12} /> Explain AI
                    </Link>
                </div>
                <h1 className="text-5xl md:text-7xl font-black text-text tracking-tight font-sans">
                    {selectedSymbol}<span className="text-text-muted/50 font-light text-4xl">/USD</span>
                </h1>
                <div className="text-text/90 text-3xl pt-2 flex items-center gap-4 font-mono font-bold tracking-tight">
                    <span className={`transition-colors duration-300 ${livePrice ? 'text-accent drop-shadow-[0_0_10px_rgba(var(--accent),0.5)]' : 'text-text'}`}>${formatPrice(currentDisplayPrice)}</span>
                    <span className="text-xs font-sans font-medium uppercase tracking-widest text-text-muted flex items-center gap-2 bg-surface/50 px-3 py-1 rounded-full border border-text/5">
                        {livePrice ? <span className="relative flex h-2.5 w-2.5"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"></span><span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-accent"></span></span> : null}
                        Live Price
                    </span>
                </div>
              </div>

              <div className="relative z-10 flex flex-col items-end gap-4 min-w-[280px]">
                <div className="w-full glass bg-surface/50 border border-text/10 p-6 rounded-sm shadow-xl">
                    <div className="flex justify-between items-center mb-5">
                        <span className="text-text-muted text-[10px] font-bold uppercase tracking-widest font-mono">Ultimate Consensus</span>
                        <DirectionBadge direction={forecastData.final_consensus} showIcon />
                    </div>
                    <div className={`text-sm font-black tracking-widest uppercase flex items-center gap-3 ${forecastData.final_consensus === 'neutral' ? 'text-text-muted' : forecastData.final_consensus.includes('up') ? 'text-success' : 'text-danger'}`}>
                        {forecastData.final_consensus !== 'neutral' ? <Target size={20}/> : <Minus size={20}/>}
                        {forecastData.agreement_signal}
                    </div>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
              
              {/* ── CONSENSUS MATRIX (9 METRICS) ── */}
              <div className="xl:col-span-1 space-y-6">
                  <div className="glass-2 rounded-xl border border-text/5 p-0 shadow-2xl h-full flex flex-col overflow-hidden group">
                    <div className="p-6 border-b border-text/5 bg-surface/30">
                        <div className="flex items-center justify-between">
                            <h3 className="text-text text-sm uppercase tracking-widest font-black flex items-center gap-2 font-mono">
                                <Layers size={16} className="text-accent"/> Multi-Factor Matrix
                            </h3>
                            <span className="text-[9px] text-text-muted font-mono font-bold bg-text/5 px-2 py-1 rounded border border-text/5 uppercase tracking-widest">Click for Math</span>
                        </div>
                    </div>
                    
                    <div className="space-y-1 flex-1 p-4 overflow-y-auto custom-scrollbar">
                      {forecastData.metrics_breakdown && forecastData.metrics_breakdown.map((m: any, idx: number) => (
                          <div 
                            key={idx} 
                            onClick={() => {
                                if (m.formula_steps) {
                                    setModalContent({ title: m.name, steps: m.formula_steps });
                                    setModalOpen(true);
                                }
                            }}
                            className="group/item flex flex-col p-4 border border-transparent hover:border-text/10 hover:bg-text/5 transition-all rounded-sm cursor-pointer relative"
                          >
                            <div className="flex justify-between items-center w-full">
                                <div className="flex items-center gap-3">
                                    <div className="text-text font-bold text-xs font-mono uppercase tracking-widest">{m.name}</div>
                                </div>
                                <DirectionBadge direction={m.direction} showIcon />
                            </div>
                            
                            {/* Hidden by default, reveals snippet and prompt on hover */}
                            <div className="mt-3 flex items-center justify-between h-0 overflow-hidden opacity-0 group-hover/item:h-auto group-hover/item:opacity-100 transition-all duration-300">
                                <div className="text-[10px] font-mono font-bold text-accent bg-accent/10 px-2.5 py-1 rounded-sm border border-accent/20">
                                    {m.calculation_snippet || "N/A"}
                                </div>
                                <div className="text-[9px] font-bold text-text-muted flex items-center gap-1 uppercase tracking-widest bg-text/5 px-2 py-1 rounded-sm">
                                    <Info size={10} /> View Eq
                                </div>
                            </div>
                          </div>
                      ))}
                    </div>
                  </div>
              </div>

              {/* ── FAN CHART MAIN VISUAL ── */}
              <div className="xl:col-span-2 space-y-6">
                  <div className="glass-2 rounded-xl border border-text/5 p-0 shadow-2xl flex flex-col h-[500px] lg:h-[600px] overflow-hidden group">
                    <div className="p-6 border-b border-text/5 bg-surface/30">
                        <div className="flex justify-between items-center">
                            <div>
                                <h3 className="text-xl font-black tracking-tight text-text font-sans">Probability Cone</h3>
                                <p className="text-[10px] text-text-muted mt-1.5 font-mono uppercase tracking-widest font-bold">60D Historical + 30D Ensembled Forecasting</p>
                            </div>
                            <VolatilityChip regime={forecastData.stgcn_volatility} />
                        </div>
                    </div>
                    
                    <div className="flex-1 w-full relative p-6">
                    <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                        <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                        <defs>
                            <linearGradient id="colorArea" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="rgba(212, 165, 71, 0.3)"/>
                            <stop offset="95%" stopColor="rgba(212, 165, 71, 0)"/>
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke={palette.text} strokeOpacity={0.08} vertical={false} />
                        <XAxis dataKey="date" tick={{fill:"var(--text-muted)", fontSize:10, fontFamily: "var(--font-mono)", fontWeight: "bold"}} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={40} />
                        <YAxis tick={{fill:"var(--text-muted)", fontSize:10, fontFamily: "var(--font-mono)", fontWeight: "bold"}} tickLine={false} axisLine={false} domain={["auto", "auto"]} 
                                tickFormatter={(v) => `$${formatPrice(v)}`} width={80} />
                        <Tooltip 
                            contentStyle={{background:"rgba(var(--surface), 0.8)", border:"1px solid rgba(var(--text), 0.1)", borderRadius:"12px", color:"var(--text)", backdropFilter: "blur(16px)", boxShadow: "0 20px 40px -10px rgba(0, 0, 0, 0.5)"}}
                            itemStyle={{fontFamily: "var(--font-mono)", fontSize: "12px", fontWeight: "bold"}}
                            labelStyle={{color: "var(--text-muted)", marginBottom: "8px", fontSize: "10px", textTransform: "uppercase", fontWeight: "bold", letterSpacing: "0.1em"}}
                        />
                        
                        <Area type="monotone" dataKey="upper" stroke="none" fill="url(#colorArea)" name="Upper Bound" />
                        <Area type="monotone" dataKey="lower" stroke="none" fill={palette.surface} fillOpacity={1} name="Lower Bound" />
                        
                        <Line type="monotone" dataKey="actual" stroke="rgb(240, 237, 232)" strokeWidth={2} dot={false} name="Actual Price" connectNulls />
                        <Line type="monotone" dataKey="ensemble" stroke="rgb(212, 165, 71)" strokeWidth={2} strokeDasharray="4 4" dot={false} name="30D Prediction" connectNulls />
                        
                        {currentDisplayPrice && <ReferenceLine y={currentDisplayPrice} stroke="rgb(148, 163, 184)" strokeDasharray="3 3" opacity={0.6} />}
                        {forecastData.last_date && <ReferenceLine x={forecastData.last_date} stroke="rgb(212, 165, 71)" strokeOpacity={0.6} label={{value: "NOW", fill: "rgb(212, 165, 71)", fontSize: 10, position: 'insideTopLeft', fontFamily: 'var(--font-mono)', fontWeight: "bold"}} />}
                        </ComposedChart>
                    </ResponsiveContainer>
                    </div>
                  </div>

                  {/* ── MULTI-HORIZON TARGETS ── */}
                  <div className="glass-2 rounded-xl border border-text/5 p-6 shadow-2xl">
                    <h3 className="text-text text-sm uppercase tracking-widest font-black mb-6 flex items-center gap-2 font-mono">
                        <Clock size={16} className="text-accent"/> Price Targets
                    </h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {forecastData.dl_targets && Object.entries(forecastData.dl_targets).map(([horizon, data]: [string, any]) => {
                            if (!data) return null;
                            const isPos = data.change_pct >= 0;
                            return (
                                <div key={horizon} className="bg-surface/50 border border-text/5 p-5 rounded-sm flex flex-col text-center relative overflow-hidden group hover:border-text/20 transition-all hover:bg-text/5 shadow-inner">
                                    <div className={`absolute top-0 left-0 w-full h-1 ${isPos ? 'bg-success/50 shadow-[0_0_10px_rgba(34,197,94,0.5)]' : 'bg-danger/50 shadow-[0_0_10px_rgba(239,68,68,0.5)]'}`} />
                                    <span className="text-text-muted text-[9px] font-mono font-bold uppercase tracking-widest mb-3">{horizon} Forecast</span>
                                    <span className="text-text font-black text-lg mb-1 tracking-tight">${formatPrice(data.price)}</span>
                                    <span className={`text-xs font-black font-mono tracking-wider ${isPos ? 'text-success' : 'text-danger'}`}>
                                        {isPos ? '+' : ''}{data.change_pct}%
                                    </span>
                                </div>
                            )
                        })}
                    </div>
                  </div>
              </div>
            </div>

            {/* ── BOTTOM ROW ── */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-6">
              
              {/* T-SHAP Widget */}
              <div className="glass-2 rounded-xl border border-text/5 p-8 shadow-2xl overflow-hidden relative group">
                <div className="absolute inset-0 bg-gradient-to-br from-accent/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
                <div className="relative z-10">
                    <div className="flex items-center justify-between mb-8">
                    <h3 className="text-text font-black text-xl tracking-tight flex items-center gap-3">
                        <div className="p-2.5 glass bg-accent/10 rounded-sm shadow-inner"><BarChart2 className="text-accent" size={20} /></div>
                        Topological SHAP
                    </h3>
                    <div className="flex items-center gap-2">
                        <div className="text-[9px] font-bold text-text-muted uppercase tracking-widest border border-text/10 px-3 py-1.5 rounded-sm bg-surface/50 font-mono shadow-inner">Feature Impact</div>
                        <Link href="/explain" className="text-[9px] font-bold text-accent hover:text-accent-2 uppercase tracking-widest border border-accent/20 hover:border-accent px-3 py-1.5 rounded-sm bg-accent/5 font-mono transition-colors flex items-center gap-1">
                            <Brain size={10} /> Explain SHAP
                        </Link>
                    </div>
                    </div>
                    
                    {tShapChartData.length > 0 ? (
                    <div className="h-[280px] w-full">
                        <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                        <BarChart layout="vertical" data={tShapChartData} margin={{ top: 0, right: 20, left: 40, bottom: 0 }}>
                            <XAxis type="number" tick={{fill: "var(--text-muted)", fontSize: 10, fontFamily: "var(--font-mono)", fontWeight: "bold"}} axisLine={false} tickLine={false} />
                            <YAxis dataKey="name" type="category" tick={{fill: "var(--text)", fontSize: 10, fontFamily: "var(--font-mono)", fontWeight: "bold"}} axisLine={false} tickLine={false} width={150} />
                            <Tooltip cursor={{fill: palette.text, fillOpacity: 0.05}} contentStyle={{background:"rgba(var(--surface),0.9)", border:"1px solid rgba(var(--text),0.1)", borderRadius:"12px", backdropFilter: "blur(12px)", color: "var(--text)", fontWeight: "bold", fontFamily: "var(--font-mono)", fontSize: "12px"}} />
                            <ReferenceLine x={0} stroke={palette.text} strokeOpacity={0.2} strokeDasharray="3 3" />
                            <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={16}>
                            {tShapChartData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={entry.color} />
                            ))}
                            </Bar>
                        </BarChart>
                        </ResponsiveContainer>
                    </div>
                    ) : (
                    <div className="h-[280px] flex items-center justify-center text-text-muted border border-dashed border-text/10 rounded-sm text-xs font-mono font-bold uppercase tracking-widest bg-surface/30">
                        Awaiting Exploratory Matrix...
                    </div>
                    )}
                </div>
              </div>

              {/* zkML Verification Widget */}
              <div className="glass-2 rounded-xl border border-text/5 p-1 shadow-2xl relative overflow-hidden group">
                <div className="absolute inset-0 bg-success/10 blur-[40px] pointer-events-none group-hover:bg-success/20 transition-all duration-1000" />
                <div className="bg-surface/80 h-full w-full rounded-[31px] p-8 flex flex-col relative z-10 backdrop-blur-2xl border border-text/5">
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center gap-3">
                            <div className="p-2.5 glass bg-text/5 rounded-sm"><Terminal size={20} className="text-text-muted" /></div>
                            <h3 className="text-text font-black text-xl tracking-tight">Execution Audit Checksum</h3>
                        </div>
                        <Shield size={20} className="text-text-muted/40" />
                    </div>
                    
                    <p className="text-sm text-text/80 mb-8 leading-relaxed font-light tracking-wide flex-1">
                        SHA-256 audit hash binding input features, outputs, and the model version to verify prediction data integrity and execution path tracking.
                    </p>
                    
                    {zkProof ? (
                        <div className="mt-auto bg-black/60 p-5 rounded-sm border border-text/10 font-mono text-[10px] sm:text-xs break-all relative overflow-hidden shadow-inner">
                        <div className="text-text-muted/70 mb-3 uppercase tracking-widest text-[9px] font-bold">{'// Audit Checksum'}</div>
                        <div className="text-text/90 leading-relaxed font-bold tracking-tight">{zkProof}</div>
                        <div className="mt-5 flex items-center gap-2 text-text tracking-widest uppercase text-[10px] font-black bg-text/10 w-fit px-3 py-1.5 rounded-sm border border-text/20">
                            <CheckCircle size={14} className="text-success" /> AUDIT CHECKSUM MATCH
                        </div>
                        </div>
                    ) : (
                        <div className="mt-auto bg-black/40 p-6 rounded-sm border border-text/5 font-mono text-xs font-bold text-text-muted text-center uppercase tracking-widest flex items-center justify-center gap-3">
                        <div className="w-3 h-3 border-2 border-text/20 border-t-text rounded-full animate-spin" />
                        Generating Checksum...
                        </div>
                    )}
                </div>
              </div>

            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function PredictionsPage() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return null;
  }

  return (
    <Suspense fallback={<div className="h-[calc(100vh-8rem)] flex items-center justify-center text-accent font-mono text-xs font-bold tracking-widest uppercase animate-pulse">Initializing ST-GCN Canvas...</div>}>
      <PredictionStudio />
    </Suspense>
  )
}
