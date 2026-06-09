"use client"
import { useState, useRef } from "react"
import useSWR from "swr"
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine, Bar
} from "recharts"
import { TrendingUp, TrendingDown, Minus, Brain, 
         BarChart2, AlertTriangle, CheckCircle } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
const fetcher = (url: string) => fetch(url).then(r => {
  if (!r.ok) throw new Error(r.statusText)
  return r.json()
})

// ── Direction badge component ──────────────────────────────────────────
function DirectionBadge({ direction }: { direction: string }) {
  const config: Record<string, {bg: string, text: string, label: string, 
                                 icon: React.ReactNode}> = {
    strong_up:   {bg:"bg-green-900",  text:"text-green-300",
                  label:"↑↑ Strong Buy",  icon:<TrendingUp size={12}/>},
    up:          {bg:"bg-green-800",  text:"text-green-400",
                  label:"↑ Buy",          icon:<TrendingUp size={12}/>},
    neutral:     {bg:"bg-gray-800",   text:"text-gray-400",
                  label:"→ Neutral",       icon:<Minus size={12}/>},
    down:        {bg:"bg-red-800",    text:"text-red-400",
                  label:"↓ Sell",         icon:<TrendingDown size={12}/>},
    strong_down: {bg:"bg-red-900",    text:"text-red-300",
                  label:"↓↓ Strong Sell", icon:<TrendingDown size={12}/>},
  }
  const c = config[direction] || config["neutral"]
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs 
                      font-bold ${c.bg} ${c.text}`}>
      {c.icon}{c.label}
    </span>
  )
}

// ── Volatility chip ────────────────────────────────────────────────────
function VolatilityChip({ regime }: { regime: string }) {
  const colors: Record<string,string> = {
    low:"bg-blue-900 text-blue-300", medium:"bg-yellow-900 text-yellow-300",
    high:"bg-orange-900 text-orange-300", extreme:"bg-red-900 text-red-300"
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-mono uppercase 
                      ${colors[regime] || colors.medium}`}>
      {regime}
    </span>
  )
}

// ── Skeleton row ───────────────────────────────────────────────────────
function SkeletonRow() {
  return (
    <tr className="border-b border-[#2a2a2a]">
      {[...Array(6)].map((_,i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 bg-[#2a2a2a] rounded animate-pulse"/>
        </td>
      ))}
    </tr>
  )
}

// ── Forecast chart component ───────────────────────────────────────────
function ForecastChart({ data, symbol }: { data: any, symbol: string }) {
  if (!data) return null

  // Handle error/insufficient data response
  if (data.error || !data.historical || data.historical.length === 0) {
    return (
      <div className="bg-amber-950 rounded-xl p-6 border border-amber-800">
        <div className="text-amber-300 font-mono text-sm">
          ⚠️ {data.error || "No historical data available for this asset."}
        </div>
        <div className="text-amber-500 text-xs mt-2">
          This asset may not have enough trading history in the database.
          Run the Binance collector to fetch more data.
        </div>
      </div>
    )
  }

  // Build unified chart data: historical + forecast
  const chartData: any[] = []

  // Historical points (last 30 for clarity)
  const hist = data.historical.slice(-30)
  hist.forEach((h: any) => {
    chartData.push({
      date:       h.date,
      actual:     h.close,
      type:       "historical"
    })
  })

  // Forecast points
  data.forecast_dates.forEach((date: string, i: number) => {
    const point: any = {
      date,
      ensemble:   data.forecast_prices[i],
      lower:      data.lower_bound[i],
      upper:      data.upper_bound[i],
      type:       "forecast"
    }
    if (data.lstm_forecast)    point.lstm    = data.lstm_forecast[i]
    if (data.prophet_forecast) point.prophet = data.prophet_forecast[i]
    chartData.push(point)
  })

  const lastActual = data.historical?.length > 0
    ? data.historical[data.historical.length - 1]?.close
    : undefined
  const forecastEnd = data.forecast_prices?.length > 0
    ? data.forecast_prices[data.forecast_prices.length - 1]
    : undefined

  // Guard: don't render if we don't have the key values
  if (lastActual === undefined || forecastEnd === undefined) {
    return (
      <div className="bg-[#1a1a1a] rounded-xl p-6 border border-[#2a2a2a]
                      text-[#94a3b8] font-mono text-sm">
        Unable to render forecast — price data unavailable.
      </div>
    )
  }
  const changeColor = forecastEnd > lastActual ? "#22c55e" : "#ef4444"

  return (
    <div className="space-y-6">

      {/* ── Main forecast chart ── */}
      <div className="bg-[#1a1a1a] rounded-xl p-6 border border-[#2a2a2a]">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white font-mono">
            {symbol} — 60-Day History + 7-Day Forecast
          </h3>
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#94a3b8] bg-[#0f0f0f] px-3 py-1 rounded-full">
              Model: {data.model_used}
            </span>
            {!data.ensemble && (
              <span className="text-xs text-amber-500 bg-amber-950 px-2 py-1 rounded-full">
                LSTM only — install neuralprophet for ensemble
              </span>
            )}
          </div>
        </div>

        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={chartData}
            margin={{top:10, right:30, left:10, bottom:10}}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a"/>
            <XAxis dataKey="date" tick={{fill:"#94a3b8", fontSize:11}}
              tickLine={false}
              interval={Math.floor(chartData.length / 8)}/>
            <YAxis tick={{fill:"#94a3b8", fontSize:11}}
              tickLine={false} axisLine={false}
              tickFormatter={(v) =>
                v >= 1000 ? `$${(v/1000).toFixed(1)}k` : `$${v.toFixed(4)}`
              }
              domain={["auto","auto"]}/>
            <Tooltip
              contentStyle={{background:"#1a1a1a", border:"1px solid #2a2a2a",
                             borderRadius:"8px", color:"#f1f5f9"}}
              formatter={(value: any, name: string) => [
                `$${Number(value).toFixed(6)}`, name
              ]}/>
            <Legend/>

            {/* Confidence interval shading */}
            <Area dataKey="upper" fill="#6366f1" fillOpacity={0.1}
              stroke="none" name="Upper Bound"/>
            <Area dataKey="lower" fill="#0f0f0f" fillOpacity={1}
              stroke="none" name="Lower Bound"/>

            {/* Historical actual prices */}
            <Line dataKey="actual" stroke="#f1f5f9" strokeWidth={2}
              dot={false} name="Actual Price" connectNulls/>

            {/* Ensemble forecast */}
            <Line dataKey="ensemble" stroke="#6366f1" strokeWidth={2.5}
              strokeDasharray="6 3" dot={false}
              name="Ensemble Forecast" connectNulls/>

            {/* Individual model lines (if ensemble) */}
            {data.ensemble && (
              <>
                <Line dataKey="lstm" stroke="#22c55e" strokeWidth={1}
                  strokeDasharray="3 3" dot={false}
                  name="LSTM" connectNulls/>
                <Line dataKey="prophet" stroke="#f59e0b" strokeWidth={1}
                  strokeDasharray="3 3" dot={false}
                  name="Prophet" connectNulls/>
              </>
            )}

            {/* Reference line at last actual price */}
            <ReferenceLine y={lastActual} stroke="#94a3b8"
              strokeDasharray="4 4" label={{
                value:"Current", fill:"#94a3b8", fontSize:11
              }}/>

            {/* Reference line where forecast begins */}
            <ReferenceLine x={data.last_date} stroke="#6366f1"
              strokeDasharray="4 4" label={{
                value:"Today", fill:"#6366f1", fontSize:11
              }}/>
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* ── Forecast summary numbers ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {data.forecast_dates.map((date: string, i: number) => {
          const price   = data.forecast_prices[i]
          const change  = ((price - lastActual) / lastActual * 100)
          const isUp    = price > lastActual
          return (
            <div key={date}
              className="bg-[#1a1a1a] rounded-lg p-3 border border-[#2a2a2a]">
              <div className="text-xs text-[#94a3b8] mb-1">
                Day {i+1} · {date}
              </div>
              <div className="text-white font-mono font-bold text-sm">
                ${price >= 1000
                  ? price.toLocaleString("en-US", {maximumFractionDigits:2})
                  : price.toFixed(6)
                }
              </div>
              <div className={`text-xs font-mono mt-0.5 
                              ${isUp ? "text-green-400" : "text-red-400"}`}>
                {isUp ? "+" : ""}{change.toFixed(2)}%
              </div>
              <div className="text-xs text-[#64748b] mt-1">
                [{price >= 1000
                  ? `$${data.lower_bound[i].toLocaleString("en-US",{maximumFractionDigits:0})}`
                  : `$${data.lower_bound[i].toFixed(4)}`} –{" "}
                 {price >= 1000
                  ? `$${data.upper_bound[i].toLocaleString("en-US",{maximumFractionDigits:0})}`
                  : `$${data.upper_bound[i].toFixed(4)}`}]
              </div>
            </div>
          )
        })}
      </div>

      {/* ── Model comparison ── */}
      <div className="bg-[#1a1a1a] rounded-xl p-6 border border-[#2a2a2a]">
        <h3 className="text-lg font-bold text-white font-mono mb-4">
          Model Comparison
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">

          {/* ST-GCN prediction */}
          <div className="bg-[#0f0f0f] rounded-lg p-4 border border-[#2a2a2a]">
            <div className="text-xs text-[#94a3b8] mb-2 uppercase tracking-wider">
              ST-GCN Model
            </div>
            <div className="text-sm text-[#94a3b8] mb-1">
              Graph Neural Network
            </div>
            <DirectionBadge direction={data.stgcn_direction}/>
            <div className="mt-2">
              <div className="flex justify-between text-xs text-[#94a3b8] mb-1">
                <span>Confidence</span>
                <span>{data.stgcn_confidence}%</span>
              </div>
              <div className="h-1.5 bg-[#2a2a2a] rounded-full">
                <div className="h-full bg-indigo-500 rounded-full"
                  style={{width:`${data.stgcn_confidence}%`}}/>
              </div>
            </div>
            <div className="mt-2">
              <VolatilityChip regime={data.stgcn_volatility}/>
            </div>
          </div>

          {/* Deep Learning prediction */}
          <div className="bg-[#0f0f0f] rounded-lg p-4 border border-[#2a2a2a]">
            <div className="text-xs text-[#94a3b8] mb-2 uppercase tracking-wider">
              Deep Learning Forecast
            </div>
            <div className="text-sm text-[#94a3b8] mb-1">
              {data.model_used}
            </div>
            <DirectionBadge direction={
              data.dl_direction === "up" ? "up" :
              data.dl_direction === "down" ? "down" : "neutral"
            }/>
            <div className="mt-2 text-sm font-mono">
              <span className={data.dl_change_pct >= 0
                ? "text-green-400" : "text-red-400"}>
                {data.dl_change_pct >= 0 ? "+" : ""}
                {data.dl_change_pct}% in 7 days
              </span>
            </div>
            <div className="mt-2 text-xs text-[#64748b]">
              Current: ${Number(lastActual) >= 1000
                ? Number(lastActual).toLocaleString("en-US",{maximumFractionDigits:2})
                : Number(lastActual).toFixed(6)}
              {" → "}
              ${Number(forecastEnd) >= 1000
                ? Number(forecastEnd).toLocaleString("en-US",{maximumFractionDigits:2})
                : Number(forecastEnd).toFixed(6)}
            </div>
          </div>

          {/* Agreement panel */}
          <div className={`rounded-lg p-4 border ${
            data.models_agree
              ? "bg-green-950 border-green-800"
              : "bg-amber-950 border-amber-800"
          }`}>
            <div className="text-xs uppercase tracking-wider mb-2 
                          text-[#94a3b8]">
              Signal Agreement
            </div>
            {data.models_agree
              ? <CheckCircle className="text-green-400 mb-2" size={24}/>
              : <AlertTriangle className="text-amber-400 mb-2" size={24}/>
            }
            <div className={`text-sm font-bold font-mono ${
              data.models_agree ? "text-green-300" : "text-amber-300"
            }`}>
              {data.agreement_signal}
            </div>
            <div className="text-xs text-[#94a3b8] mt-2">
              {data.models_agree
                ? "Both models point the same direction — higher conviction signal."
                : "Models disagree — exercise caution and reduce position size."}
            </div>
          </div>
        </div>

        {/* Visual comparison bar if ensemble */}
        {data.ensemble && data.lstm_forecast && data.prophet_forecast && (
          <div>
            <div className="text-sm text-[#94a3b8] mb-3">
              7-Day Forecast Comparison (individual models vs ensemble)
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <ComposedChart data={data.forecast_dates.map(
                (date: string, i: number) => ({
                  date,
                  LSTM:     data.lstm_forecast[i],
                  Prophet:  data.prophet_forecast[i],
                  Ensemble: data.forecast_prices[i],
                })
              )} margin={{top:5, right:20, left:10, bottom:5}}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a"/>
                <XAxis dataKey="date" tick={{fill:"#94a3b8", fontSize:10}}/>
                <YAxis tick={{fill:"#94a3b8", fontSize:10}}
                  tickFormatter={(v) =>
                    v >= 1000 ? `$${(v/1000).toFixed(0)}k` : `$${v.toFixed(2)}`
                  }
                  domain={["auto","auto"]}/>
                <Tooltip contentStyle={{background:"#1a1a1a",
                  border:"1px solid #2a2a2a", borderRadius:"8px"}}/>
                <Legend/>
                <Line dataKey="LSTM"     stroke="#22c55e" strokeWidth={1.5}
                  dot={false}/>
                <Line dataKey="Prophet"  stroke="#f59e0b" strokeWidth={1.5}
                  dot={false}/>
                <Line dataKey="Ensemble" stroke="#6366f1" strokeWidth={2.5}
                  dot={false}/>
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main predictions page ──────────────────────────────────────────────
export default function PredictionsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const [forecastData, setForecastData]     = useState<any>(null)
  const [forecastLoading, setForecastLoading] = useState(false)
  const [forecastError, setForecastError]   = useState<string | null>(null)
  const [filterDir, setFilterDir]           = useState("all")
  const [minConf, setMinConf]               = useState(0)
  const [search, setSearch]                 = useState("")

  const { data: predictions, isLoading, error } = useSWR(
    `${BASE}/api/predictions?limit=50`,
    fetcher,
    { revalidateOnFocus: false, refreshInterval: 60000 }
  )

  const runForecast = async (symbol: string) => {
    setSelectedSymbol(symbol)
    setForecastLoading(true)
    setForecastError(null)
    setForecastData(null)
    try {
      const res = await fetch(`${BASE}/api/forecast/${symbol}`)
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setForecastData(data)
      // Scroll to forecast section smoothly
      setTimeout(() => {
        document.getElementById("forecast-section")?.scrollIntoView({
          behavior: "smooth", block: "start"
        })
      }, 100)
    } catch (e: any) {
      setForecastError(e.message || "Forecast failed")
    } finally {
      setForecastLoading(false)
    }
  }

  // Filter predictions
  const filtered = (predictions || []).filter((p: any) => {
    const matchDir  = filterDir === "all" || p.direction?.includes(filterDir)
    const matchConf = (p.confidence || 0) * 100 >= minConf
    const matchSrch = !search ||
      p.asset_symbol?.toLowerCase().includes(search.toLowerCase())
    return matchDir && matchConf && matchSrch
  })

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white font-mono">
          Predictions
        </h1>
        <p className="text-[#94a3b8] text-sm mt-1">
          ST-GCN model predictions + on-demand deep learning forecast
        </p>
      </div>

      {/* ── Filter bar ── */}
      <div className="flex flex-wrap gap-3 items-center">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search symbol..."
          className="bg-[#1a1a1a] border border-[#2a2a2a] text-white rounded-lg
                     px-3 py-2 text-sm w-36 focus:outline-none
                     focus:border-indigo-500"
        />
        <select
          value={filterDir}
          onChange={e => setFilterDir(e.target.value)}
          className="bg-[#1a1a1a] border border-[#2a2a2a] text-white rounded-lg
                     px-3 py-2 text-sm focus:outline-none focus:border-indigo-500">
          <option value="all">All Directions</option>
          <option value="up">Buy Signals</option>
          <option value="down">Sell Signals</option>
          <option value="neutral">Neutral</option>
        </select>
        <div className="flex items-center gap-2 text-sm text-[#94a3b8]">
          <span>Min confidence:</span>
          <input type="range" min={0} max={100} value={minConf}
            onChange={e => setMinConf(Number(e.target.value))}
            className="w-24 accent-indigo-500"/>
          <span className="text-white w-8">{minConf}%</span>
        </div>
        <button
          onClick={() => {
            const csv = [
              ["Symbol","Direction","Confidence","Volatility","Predicted At"].join(","),
              ...filtered.map((p: any) => [
                p.asset_symbol, p.direction,
                ((p.confidence||0)*100).toFixed(1)+"%",
                p.volatility_regime, p.predicted_at
              ].join(","))
            ].join("\n")
            const blob = new Blob([csv], {type:"text/csv"})
            const a    = document.createElement("a")
            a.href     = URL.createObjectURL(blob)
            a.download = "predictions.csv"
            a.click()
          }}
          className="ml-auto bg-[#1a1a1a] border border-[#2a2a2a] text-[#94a3b8]
                     hover:text-white px-3 py-2 rounded-lg text-sm transition">
          Export CSV
        </button>
      </div>

      {/* ── Predictions table ── */}
      <div className="bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#2a2a2a]">
              {["Asset","Direction","Confidence","Volatility",
                "Predicted At","Forecast"].map(h => (
                <th key={h}
                  className="px-4 py-3 text-left text-xs font-bold
                             text-[#94a3b8] uppercase tracking-wider">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? [...Array(10)].map((_,i) => <SkeletonRow key={i}/>)
              : error
              ? <tr><td colSpan={6} className="px-4 py-8 text-center
                    text-[#ef4444]">Failed to load predictions</td></tr>
              : filtered.map((p: any) => (
                <tr key={p.asset_symbol}
                  className={`border-b border-[#2a2a2a] hover:bg-[#0f0f0f]
                    transition ${selectedSymbol === p.asset_symbol
                      ? "bg-indigo-950/30" : ""}`}>
                  <td className="px-4 py-3">
                    <span className="font-mono font-bold text-white">
                      {p.asset_symbol}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <DirectionBadge direction={p.direction || "neutral"}/>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-20 bg-[#2a2a2a] rounded-full">
                        <div className="h-full bg-indigo-500 rounded-full"
                          style={{width:`${(p.confidence||0)*100}%`}}/>
                      </div>
                      <span className="text-xs text-[#94a3b8] font-mono">
                        {((p.confidence||0)*100).toFixed(0)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <VolatilityChip regime={p.volatility_regime || "medium"}/>
                  </td>
                  <td className="px-4 py-3 text-xs text-[#94a3b8] font-mono">
                    {p.predicted_at
                      ? new Date(p.predicted_at).toLocaleString()
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => runForecast(p.asset_symbol)}
                      disabled={forecastLoading && 
                                selectedSymbol === p.asset_symbol}
                      className="flex items-center gap-1.5 px-3 py-1.5
                                 bg-indigo-600 hover:bg-indigo-500
                                 disabled:opacity-50 text-white text-xs
                                 rounded-lg transition font-mono">
                      <Brain size={12}/>
                      {forecastLoading && selectedSymbol === p.asset_symbol
                        ? "Running..." : "Forecast"}
                    </button>
                  </td>
                </tr>
              ))
            }
          </tbody>
        </table>
      </div>

      {/* ── Forecast section ── */}
      {(forecastLoading || forecastData || forecastError) && (
        <div id="forecast-section">
          <h2 className="text-xl font-bold text-white font-mono mb-4">
            Deep Learning Forecast — {selectedSymbol}
          </h2>

          {forecastLoading && (
            <div className="bg-[#1a1a1a] rounded-xl p-12 border
                            border-[#2a2a2a] text-center">
              <div className="inline-flex items-center gap-3
                              text-[#94a3b8]">
                <div className="w-5 h-5 border-2 border-indigo-500
                                border-t-transparent rounded-full
                                animate-spin"/>
                <span className="font-mono">
                  Running LSTM + Prophet ensemble on {selectedSymbol}...
                  <br/>
                  <span className="text-xs text-[#64748b]">
                    This takes 15–30 seconds
                  </span>
                </span>
              </div>
            </div>
          )}

          {forecastError && (
            <div className="bg-red-950 rounded-xl p-6 border
                            border-red-800 text-red-300 font-mono text-sm">
              ❌ Forecast failed: {forecastError}
            </div>
          )}

          {forecastData && !forecastLoading && (
            <ForecastChart data={forecastData} symbol={selectedSymbol!}/>
          )}

          {forecastData && !forecastLoading && (
            <div className="flex justify-center mt-4">
              <button
                onClick={() => runForecast(selectedSymbol!)}
                className="flex items-center gap-2 px-4 py-2 bg-[#1a1a1a]
                           border border-[#2a2a2a] text-[#94a3b8]
                           hover:text-white hover:border-indigo-500
                           rounded-lg text-sm font-mono transition">
                🔄 Re-run forecast
              </button>
              <span className="ml-3 text-xs text-[#64748b] self-center">
                Each run trains a fresh model on latest data
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
