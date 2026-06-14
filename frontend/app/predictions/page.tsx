"use client"
import { useState, useEffect, Suspense } from "react"
import useSWR from "swr"
import { useSearchParams, useRouter } from "next/navigation"
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, BarChart, Bar, Cell
} from "recharts"
import { TrendingUp, TrendingDown, Minus, Brain, 
         BarChart2, AlertTriangle, CheckCircle, Terminal, Lock, Clock, Target, Layers, Info, X } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
const WS_BASE = BASE.replace(/^http/, "ws")

const fetcher = (url: string) => fetch(url).then(r => {
  if (!r.ok) throw new Error(r.statusText)
  return r.json()
})

// ── Shared UI Components ──────────────────────────────────────────
function DirectionBadge({ direction }: { direction: string }) {
  const config: Record<string, {bg: string, text: string, label: string, icon: React.ReactNode, border: string}> = {
    strong_up:   {bg:"bg-[#10b981]/10",  text:"text-[#10b981]", label:"STRONG BUY",  icon:<TrendingUp size={14}/>, border:"border-[#10b981]/20"},
    up:          {bg:"bg-[#34d399]/10",  text:"text-[#34d399]", label:"BUY",          icon:<TrendingUp size={14}/>, border:"border-[#34d399]/20"},
    neutral:     {bg:"bg-[#94a3b8]/10",   text:"text-[#94a3b8]",  label:"NEUTRAL",       icon:<Minus size={14}/>, border:"border-[#94a3b8]/20"},
    down:        {bg:"bg-[#fb923c]/10",    text:"text-[#fb923c]",   label:"SELL",         icon:<TrendingDown size={14}/>, border:"border-[#fb923c]/20"},
    strong_down: {bg:"bg-[#f43f5e]/10",    text:"text-[#f43f5e]",   label:"STRONG SELL", icon:<TrendingDown size={14}/>, border:"border-[#f43f5e]/20"},
  }
  const c = config[direction] || config["neutral"]
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-sm text-[10px] sm:text-xs font-bold uppercase tracking-widest border ${c.bg} ${c.text} ${c.border}`}>
      {c.icon}{c.label}
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
                    <div key={i} className="my-6 p-4 bg-indigo-950/30 border border-indigo-500/20 rounded-xl flex items-center justify-center overflow-x-auto text-indigo-200">
                        <BlockMath math={equation} />
                    </div>
                )
            }
            if (line.startsWith('**') && !line.match(/^[0-9]\./)) {
                return <h3 key={i} className="text-xl font-bold text-white mb-4 mt-2">{line.replace(/\*\*/g, '')}</h3>
            }
            if (line.match(/^[0-9]\./)) {
                // Parse inline math $...$ and block math $$...$$
                const parts = line.split(/(\$\$[^$]+\$\$|\$[^$]+\$)/g);
                return (
                    <div key={i} className="flex gap-4 mb-3 text-slate-300 leading-relaxed text-sm">
                        <span className="text-indigo-400 font-mono mt-0.5 whitespace-nowrap">{parts[0].substring(0, 2)}</span>
                        <span>
                            {parts.map((part, index) => {
                                if (index === 0) {
                                   part = part.substring(3);
                                }
                                if (part.startsWith('$$') && part.endsWith('$$')) {
                                    return <span key={index} className="text-indigo-200 block my-2"><BlockMath math={part.replace(/\$\$/g, '')} /></span>;
                                }
                                if (part.startsWith('$') && part.endsWith('$')) {
                                    return <span key={index} className="text-indigo-300"><InlineMath math={part.replace(/\$/g, '')} /></span>;
                                }
                                // Handle bold tags inside normal text
                                const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
                                return boldParts.map((b, bIdx) => {
                                    if (b.startsWith('**') && b.endsWith('**')) {
                                        return <strong key={`${index}-${bIdx}`} className="text-white">{b.replace(/\*\*/g, '')}</strong>;
                                    }
                                    return b;
                                });
                            })}
                        </span>
                    </div>
                )
            }
            return <p key={i} className="mb-2 text-slate-300 text-sm">{line}</p>
        });
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
            <div className="bg-[#0f172a] border border-slate-700 w-full max-w-2xl rounded-2xl shadow-2xl relative z-10 flex flex-col max-h-[85vh] overflow-hidden">
                <div className="flex items-center justify-between p-6 border-b border-slate-800">
                    <h2 className="text-lg font-bold text-white tracking-wide">{title}</h2>
                    <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors bg-slate-800/50 p-2 rounded-lg">
                        <X size={20} />
                    </button>
                </div>
                <div className="p-8 overflow-y-auto custom-scrollbar">
                    {renderFormula(formulaSteps)}
                </div>
            </div>
        </div>
    );
}


// ── Main Page ──────────────────────────────────────────
function PredictionStudio() {
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
    const ws = new WebSocket(`${WS_BASE}/api/stream/ticker/${selectedSymbol}`);
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
      if (sv.zk_proof) zkProof = sv.zk_proof;
    } catch (e) {}
  }

  const shapSource = tShapData?.attributions_pct || tShapData;

  const tShapChartData = shapSource && Object.keys(shapSource).length > 0 ? Object.entries(shapSource).map(([name, val]) => ({
    name, value: Number(val), color: Number(val) > 0 ? "#10b981" : "#f43f5e"
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
    <div className="h-full bg-[#030712] text-slate-200 overflow-y-auto custom-scrollbar font-sans relative">
      
      <MathModal 
        isOpen={modalOpen} 
        onClose={() => setModalOpen(false)} 
        title={modalContent.title} 
        formulaSteps={modalContent.steps} 
      />

      {/* Subtle Glow Backgrounds */}
      <div className="absolute top-0 right-0 w-[800px] h-[800px] bg-indigo-900/10 rounded-full blur-[150px] pointer-events-none" />
      <div className="absolute bottom-0 left-0 w-[800px] h-[800px] bg-emerald-900/10 rounded-full blur-[150px] pointer-events-none" />

      <div className="w-full max-w-[1600px] mx-auto p-4 md:p-8 relative z-10">
        {!selectedSymbol ? (
          <div className="h-[70vh] flex flex-col items-center justify-center text-slate-500 space-y-6">
            <Brain size={64} className="opacity-20 text-indigo-500" />
            <h3 className="text-2xl font-light tracking-wide text-center max-w-md text-slate-400">Select an Asset for Forecast Analysis.</h3>
            <button onClick={() => router.push('/screener')} className="mt-8 bg-white/5 hover:bg-white/10 border border-white/10 text-white px-8 py-3 rounded-full font-medium text-sm tracking-wide transition-all shadow-[0_0_15px_rgba(255,255,255,0.05)]">Open Screener</button>
          </div>
        ) : forecastLoading ? (
          <div className="h-[70vh] flex flex-col items-center justify-center text-slate-400 space-y-8">
            <div className="relative w-16 h-16">
                <div className="absolute inset-0 border-2 border-indigo-500/20 rounded-full" />
                <div className="absolute inset-0 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            </div>
            <div className="text-center space-y-2">
              <div className="text-indigo-400 text-lg uppercase tracking-[0.1em] animate-pulse">Computing Multi-Factor Inference</div>
              <div className="text-xs uppercase tracking-widest opacity-60 font-mono">Running PyTorch Deep Learning Sequences</div>
            </div>
          </div>
        ) : forecastError || (forecastData && forecastData.error) ? (
          <div className="p-8 bg-red-950/30 border border-red-900/50 rounded-2xl text-red-400 font-mono backdrop-blur-md shadow-2xl flex items-center gap-4">
            <AlertTriangle className="text-red-500" />
            {forecastError || forecastData.error}
          </div>
        ) : forecastData && (
          <div className="space-y-6 pb-10">
            
            {/* ── HEADER ROW ── */}
            <div className="flex flex-col md:flex-row justify-between items-end gap-6 bg-white/[0.02] border border-white/[0.05] p-6 lg:p-8 rounded-3xl shadow-2xl backdrop-blur-xl relative overflow-hidden">
              <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/5 rounded-full blur-[80px] pointer-events-none" />
              
              <div className="relative z-10 space-y-2">
                <div className="flex items-center gap-3 mb-2">
                    <span className="text-xs text-indigo-400 font-mono tracking-widest uppercase border border-indigo-500/20 bg-indigo-500/10 px-3 py-1 rounded-full">Multi-Factor Analysis Pipeline</span>
                </div>
                <h1 className="text-5xl md:text-6xl font-black text-white tracking-tight">
                    {selectedSymbol}<span className="text-slate-600 font-light">/USD</span>
                </h1>
                <div className="text-slate-300 text-2xl pt-2 flex items-center gap-3 font-mono">
                    <span className={`transition-colors duration-300 ${livePrice ? 'text-indigo-300' : 'text-white'}`}>${formatPrice(currentDisplayPrice)}</span>
                    <span className="text-sm font-sans flex items-center gap-2">
                        {livePrice ? <span className="relative flex h-2 w-2"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span><span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span></span> : null}
                        <span className="text-slate-500">Live Market Price</span>
                    </span>
                </div>
              </div>

              <div className="relative z-10 flex flex-col items-end gap-4 min-w-[280px]">
                <div className="w-full bg-black/40 border border-white/10 p-5 rounded-2xl backdrop-blur-md">
                    <div className="flex justify-between items-center mb-4">
                        <span className="text-slate-400 text-xs uppercase tracking-widest font-mono">Ultimate Consensus</span>
                        <DirectionBadge direction={forecastData.final_consensus} />
                    </div>
                    <div className={`text-sm font-bold tracking-wide flex items-center gap-2 ${forecastData.final_consensus === 'neutral' ? 'text-slate-400' : forecastData.final_consensus.includes('up') ? 'text-emerald-400' : 'text-red-400'}`}>
                        {forecastData.final_consensus !== 'neutral' ? <Target size={16}/> : <Minus size={16}/>}
                        {forecastData.agreement_signal}
                    </div>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
              
              {/* ── CONSENSUS MATRIX (9 METRICS) ── */}
              <div className="xl:col-span-1 space-y-6">
                  <div className="bg-white/[0.02] border border-white/[0.05] rounded-3xl p-6 shadow-2xl backdrop-blur-xl h-full flex flex-col">
                    <div className="flex items-center justify-between mb-6">
                        <h3 className="text-slate-300 text-sm uppercase tracking-widest font-bold flex items-center gap-2">
                            <Layers size={16} className="text-indigo-400"/> Multi-Factor Matrix
                        </h3>
                        <span className="text-[10px] text-slate-500 font-mono bg-black/20 px-2 py-1 rounded border border-slate-700">Click row for math</span>
                    </div>
                    
                    <div className="space-y-2 flex-1">
                      {forecastData.metrics_breakdown && forecastData.metrics_breakdown.map((m: any, idx: number) => (
                          <div 
                            key={idx} 
                            onClick={() => {
                                if (m.formula_steps) {
                                    setModalContent({ title: m.name, steps: m.formula_steps });
                                    setModalOpen(true);
                                }
                            }}
                            className="group flex flex-col p-3 border border-transparent hover:border-white/[0.05] hover:bg-white/[0.02] transition-all rounded-xl cursor-pointer relative"
                          >
                            <div className="flex justify-between items-center w-full">
                                <div className="flex items-center gap-2">
                                    <div className="text-slate-300 font-medium text-sm">{m.name}</div>
                                </div>
                                <DirectionBadge direction={m.direction} />
                            </div>
                            
                            {/* Hidden by default, reveals snippet and prompt on hover */}
                            <div className="mt-2 flex items-center justify-between h-0 overflow-hidden opacity-0 group-hover:h-auto group-hover:opacity-100 transition-all duration-300">
                                <div className="text-xs font-mono text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
                                    {m.calculation_snippet || "N/A"}
                                </div>
                                <div className="text-[10px] text-slate-500 flex items-center gap-1 uppercase tracking-widest">
                                    <Info size={12} /> View Equation
                                </div>
                            </div>
                          </div>
                      ))}
                    </div>
                  </div>
              </div>

              {/* ── FAN CHART MAIN VISUAL ── */}
              <div className="xl:col-span-2 space-y-6">
                  <div className="bg-white/[0.02] border border-white/[0.05] rounded-3xl p-6 shadow-2xl backdrop-blur-xl flex flex-col h-[400px] lg:h-[500px]">
                    <div className="flex justify-between items-center mb-6">
                    <div>
                        <h3 className="text-xl font-light tracking-wide text-white">Probability Cone</h3>
                        <p className="text-xs text-slate-500 mt-1 font-mono">60D Historical + 30D Ensembled Forecasting</p>
                    </div>
                    <VolatilityChip regime={forecastData.stgcn_volatility} />
                    </div>
                    
                    <div className="flex-1 w-full relative">
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                        <defs>
                            <linearGradient id="colorArea" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/>
                            <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#ffffff" strokeOpacity={0.03} vertical={false} />
                        <XAxis dataKey="date" tick={{fill:"#64748b", fontSize:10, fontFamily: "monospace"}} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={40} />
                        <YAxis tick={{fill:"#64748b", fontSize:10, fontFamily: "monospace"}} tickLine={false} axisLine={false} domain={["auto", "auto"]} 
                                tickFormatter={(v) => `$${formatPrice(v)}`} width={80} />
                        <Tooltip 
                            contentStyle={{background:"rgba(10, 10, 10, 0.9)", border:"1px solid rgba(255,255,255,0.1)", borderRadius:"12px", color:"#f1f5f9", backdropFilter: "blur(10px)", boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.5)"}}
                            itemStyle={{fontFamily: "monospace", fontSize: "12px"}}
                            labelStyle={{color: "#94a3b8", marginBottom: "8px", fontSize: "10px", textTransform: "uppercase"}}
                        />
                        
                        <Area type="monotone" dataKey="upper" stroke="none" fill="url(#colorArea)" name="Upper Bound" />
                        <Area type="monotone" dataKey="lower" stroke="none" fill="#030712" fillOpacity={1} name="Lower Bound" />
                        
                        <Line type="monotone" dataKey="actual" stroke="#ffffff" strokeWidth={2} dot={false} name="Actual Price" connectNulls />
                        <Line type="monotone" dataKey="ensemble" stroke="#818cf8" strokeWidth={2} strokeDasharray="4 4" dot={false} name="30D Prediction" connectNulls />
                        
                        {currentDisplayPrice && <ReferenceLine y={currentDisplayPrice} stroke="#475569" strokeDasharray="3 3" opacity={0.6} />}
                        {forecastData.last_date && <ReferenceLine x={forecastData.last_date} stroke="#818cf8" strokeOpacity={0.6} label={{value: "NOW", fill: "#818cf8", fontSize: 10, position: 'insideTopLeft', fontFamily: 'monospace'}} />}
                        </ComposedChart>
                    </ResponsiveContainer>
                    </div>
                  </div>

                  {/* ── MULTI-HORIZON TARGETS ── */}
                  <div className="bg-white/[0.02] border border-white/[0.05] rounded-3xl p-6 shadow-2xl backdrop-blur-xl">
                    <h3 className="text-slate-300 text-sm uppercase tracking-widest font-bold mb-4 flex items-center gap-2">
                        <Clock size={16} className="text-emerald-400"/> Price Targets
                    </h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {forecastData.dl_targets && Object.entries(forecastData.dl_targets).map(([horizon, data]: [string, any]) => {
                            if (!data) return null;
                            const isPos = data.change_pct >= 0;
                            return (
                                <div key={horizon} className="bg-black/30 border border-white/5 p-4 rounded-2xl flex flex-col text-center relative overflow-hidden group hover:border-white/10 transition-colors">
                                    <div className={`absolute top-0 left-0 w-full h-1 ${isPos ? 'bg-emerald-500/20' : 'bg-red-500/20'}`} />
                                    <span className="text-slate-400 text-[10px] font-mono uppercase tracking-widest mb-2">{horizon} Forecast</span>
                                    <span className="text-white font-mono text-sm mb-1">${formatPrice(data.price)}</span>
                                    <span className={`text-xs font-bold ${isPos ? 'text-emerald-400' : 'text-red-400'}`}>
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
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              
              {/* T-SHAP Widget */}
              <div className="bg-white/[0.02] border border-white/[0.05] rounded-3xl p-6 shadow-2xl backdrop-blur-xl">
                <div className="flex items-center justify-between mb-8">
                  <h3 className="text-white font-light tracking-wide flex items-center gap-3">
                    <div className="p-2 bg-indigo-500/10 rounded-lg"><BarChart2 className="text-indigo-400" size={18} /></div>
                    Topological SHAP
                  </h3>
                  <div className="text-[10px] text-slate-400 uppercase tracking-widest border border-slate-700 px-2 py-1 rounded bg-black/20">Feature Impact</div>
                </div>
                
                {tShapChartData.length > 0 ? (
                  <div className="h-[250px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart layout="vertical" data={tShapChartData} margin={{ top: 0, right: 20, left: 40, bottom: 0 }}>
                        <XAxis type="number" tick={{fill: "#64748b", fontSize: 10, fontFamily: "monospace"}} axisLine={false} tickLine={false} />
                        <YAxis dataKey="name" type="category" tick={{fill: "#cbd5e1", fontSize: 11, fontFamily: "monospace"}} axisLine={false} tickLine={false} width={150} />
                        <Tooltip cursor={{fill: 'rgba(255,255,255,0.02)'}} contentStyle={{background:"rgba(10,10,10,0.9)", border:"1px solid rgba(255,255,255,0.1)", borderRadius:"8px", backdropFilter: "blur(10px)", color: "white"}} />
                        <ReferenceLine x={0} stroke="rgba(255,255,255,0.1)" />
                        <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={12}>
                          {tShapChartData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="h-[250px] flex items-center justify-center text-slate-500 border border-dashed border-white/10 rounded-xl text-sm font-mono bg-black/20">
                    Awaiting Exploratory Matrix...
                  </div>
                )}
              </div>

              {/* zkML Verification Widget */}
              <div className="bg-gradient-to-br from-[#0a0a0a] to-[#030712] border border-white/[0.05] rounded-3xl p-1 shadow-2xl relative overflow-hidden group">
                <div className="absolute inset-0 bg-green-500/5 blur-2xl pointer-events-none group-hover:bg-green-500/10 transition-colors duration-700" />
                <div className="bg-black/60 h-full w-full rounded-[23px] p-6 flex flex-col relative z-10 backdrop-blur-xl">
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center gap-3">
                            <div className="p-2 bg-green-500/10 rounded-lg"><Terminal size={18} className="text-green-400" /></div>
                            <h3 className="text-white font-light tracking-wide">zkML Verification</h3>
                        </div>
                        <Lock size={16} className="text-green-500/30" />
                    </div>
                    
                    <p className="text-sm text-slate-400 mb-6 leading-relaxed flex-1">
                        Cryptographic zero-knowledge proof ensuring inference execution matches the audited ST-GCN weights securely without revealing model architecture.
                    </p>
                    
                    {zkProof ? (
                        <div className="mt-auto bg-black/80 p-4 rounded-xl border border-green-500/20 font-mono text-[10px] sm:text-xs break-all relative overflow-hidden">
                        <div className="absolute inset-0 bg-green-500/5 opacity-50" />
                        <div className="text-green-500/70 mb-2 uppercase tracking-widest text-[10px]">{'// SNARK Hash'}</div>
                        <div className="text-slate-300 leading-relaxed opacity-90">{zkProof}</div>
                        <div className="mt-4 flex items-center gap-2 text-[#34d399] tracking-widest uppercase text-[10px] font-bold">
                            <CheckCircle size={12} /> ON-CHAIN VERIFIED
                        </div>
                        </div>
                    ) : (
                        <div className="mt-auto bg-black/80 p-4 rounded-xl border border-white/5 font-mono text-xs text-slate-600 text-center uppercase tracking-widest">
                        Generating Proof...
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
  return (
    <Suspense fallback={<div className="h-screen flex items-center justify-center text-slate-500 font-mono text-sm tracking-widest uppercase bg-[#030712]">Initializing Canvas...</div>}>
      <PredictionStudio />
    </Suspense>
  )
}
