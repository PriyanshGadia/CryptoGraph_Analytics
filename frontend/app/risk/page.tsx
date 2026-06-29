"use client";

import useSWR from "swr";
import { fetcher, RiskData, RiskAlert } from "@/lib/api";
import { Skeleton } from "@/components/ui/Skeleton";
import { GlassCard } from "@/components/ui/GlassCard";
import {
  RefreshCcw, AlertTriangle, TrendingUp, TrendingDown, Minus,
  Shield, Activity, BarChart3, PieChart as PieIcon, CheckCircle,
  ShieldAlert, Info, Zap
} from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, ScatterChart, Scatter, ZAxis, Area, AreaChart, BarChart, CartesianGrid, Bar, PieChart, Pie, Cell, Legend, ComposedChart } from "recharts";
import { ScrollToTop } from "@/components/ScrollToTop";
import { CHART_HEX } from "@/lib/design-tokens";

interface PredictionRow {
  asset_symbol: string;
  direction: string;
  confidence: number;
  volatility_regime: string;
  predicted_at: string;
  model_version: string;
}

const DIRECTION_COLORS: Record<string, string> = {
  strong_up: "rgb(34, 197, 94)", up: "rgba(34, 197, 94, 0.6)", neutral: "rgb(148, 163, 184)", down: "rgba(239, 68, 68, 0.6)", strong_down: "rgb(239, 68, 68)",
};
const DIRECTION_LABELS: Record<string, string> = {
  strong_up: "Strong Buy", up: "Buy", neutral: "Neutral", down: "Sell", strong_down: "Strong Sell",
};

const SEVERITY_CONFIG: Record<string, { bg: string; border: string; icon: any; text: string; shadow: string }> = {
  high: { bg: "bg-danger/10", border: "border-danger/30", icon: ShieldAlert, text: "text-danger", shadow: "shadow-[0_0_15px_rgba(239,68,68,0.15)]" },
  medium: { bg: "bg-warning/10", border: "border-warning/30", icon: AlertTriangle, text: "text-warning", shadow: "shadow-[0_0_15px_rgba(234,179,8,0.15)]" },
  info: { bg: "bg-accent/10", border: "border-accent/30", icon: Info, text: "text-accent", shadow: "shadow-[0_0_15px_rgba(99,102,241,0.15)]" },
  low: { bg: "bg-success/10", border: "border-success/30", icon: CheckCircle, text: "text-success", shadow: "shadow-[0_0_15px_rgba(34,197,94,0.15)]" },
};

export default function RiskPage() {
  const { data, error, isLoading, mutate } = useSWR<RiskData>("/api/risk", fetcher, {
    revalidateOnFocus: false, dedupingInterval: 30000, refreshInterval: 120000,
  });
  const { data: preds } = useSWR<PredictionRow[]>("/api/predictions?limit=50", fetcher, {
    revalidateOnFocus: false, dedupingInterval: 30000, refreshInterval: 120000,
  });
  const { data: macro } = useSWR("/api/risk/macro", fetcher, {
    revalidateOnFocus: false, dedupingInterval: 30000, refreshInterval: 300000,
  });

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[50vh] space-y-6">
        <div className="text-danger bg-danger/10 p-6 rounded-sm border border-danger/20 font-mono text-center flex flex-col items-center gap-4 shadow-[0_0_30px_rgba(239,68,68,0.1)]">
            <ShieldAlert size={48} className="text-danger drop-shadow-[0_0_10px_rgba(239,68,68,0.5)]" />
            <p>Risk telemetry offline. Unable to establish connection to market sentinels.</p>
        </div>
        <button onClick={() => mutate()} className="flex items-center gap-2 px-6 py-3 glass bg-white/5 hover:bg-white/10 transition-all rounded-sm text-text border border-white/10 shadow-inner hover:shadow-[0_0_15px_rgba(255,255,255,0.1)] font-bold uppercase tracking-widest text-xs">
          <RefreshCcw size={16} /> Re-establish Link
        </button>
      </div>
    );
  }

  const predDist = preds ? Object.entries(
    preds.reduce((acc, p) => { acc[p.direction] = (acc[p.direction] || 0) + 1; return acc; }, {} as Record<string, number>)
  ).map(([dir, count]) => ({
    name: DIRECTION_LABELS[dir] || dir,
    value: count,
    color: DIRECTION_COLORS[dir] || "#64748b",
  })) : [];

  const topMoversData = data?.top_volatile?.map(m => ({
    name: m.symbol,
    volatility: m.volatility_7d,
  })) || [];

  return (
    <div className="space-y-8 pt-8 p-6 glass-2 shape-seal overflow-hidden max-w-[1600px] mx-auto relative">
      <div className="absolute top-[-100px] right-[-100px] w-96 h-96 bg-danger/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[20%] left-[-100px] w-80 h-80 bg-accent/5 rounded-full blur-[100px] pointer-events-none" />

      {/* HEADER */}
      <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-end gap-6 mb-4">
        <div>
          <h1 className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted flex items-center gap-4 tracking-tight">
            <div className="p-3 glass bg-danger/10 rounded-sm shadow-inner shadow-danger/20">
                <ShieldAlert className="text-danger" size={32} />
            </div>
            Risk Matrix
          </h1>
          <p className="text-text-muted mt-3 font-light tracking-wide max-w-xl">
            Real-time market regime, volatility clustering, and neural correlation analysis.
          </p>
        </div>
      </div>

      {isLoading || !data ? (
        <div className="space-y-8 relative z-10">
          <Skeleton className="h-32 w-full rounded-sm" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">{Array.from({length: 4}).map((_, i) => <Skeleton key={i} className="h-36 rounded-sm" />)}</div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8"><Skeleton className="h-[400px] rounded-sm" /><Skeleton className="h-[400px] rounded-sm" /></div>
        </div>
      ) : (
        <div className="relative z-10 space-y-8">
          {/* Regime Banner */}
          <GlassCard tier={2} shape="shape-squircle" className={`p-0 overflow-hidden relative group border ${
            data.market_regime === "bull"
              ? "border-success/30 hover:border-success/50 hover:shadow-[0_0_30px_rgba(34,197,94,0.1)]"
              : data.market_regime === "bear"
                ? "border-danger/30 hover:border-danger/50 hover:shadow-[0_0_30px_rgba(239,68,68,0.1)]"
                : "border-warning/30 hover:border-warning/50 hover:shadow-[0_0_30px_rgba(234,179,8,0.1)]"
          }`}>
            <div className={`absolute inset-0 opacity-10 transition-opacity duration-1000 group-hover:opacity-20 ${
              data.market_regime === "bull" ? "bg-gradient-to-r from-success to-transparent" : data.market_regime === "bear" ? "bg-gradient-to-r from-danger to-transparent" : "bg-gradient-to-r from-warning to-transparent"
            }`} />
            
            <div className="relative p-8 flex items-center gap-8">
                <div className={`p-5 rounded-sm glass ${
                data.market_regime === "bull" ? "bg-success/20 shadow-inner shadow-success/40" : data.market_regime === "bear" ? "bg-danger/20 shadow-inner shadow-danger/40" : "bg-warning/20 shadow-inner shadow-warning/40"
                }`}>
                {data.market_regime === "bull" ? <TrendingUp size={40} className="text-success drop-shadow-[0_0_10px_rgba(34,197,94,0.5)]" /> :
                data.market_regime === "bear" ? <TrendingDown size={40} className="text-danger drop-shadow-[0_0_10px_rgba(239,68,68,0.5)]" /> :
                <Minus size={40} className="text-warning drop-shadow-[0_0_10px_rgba(234,179,8,0.5)]" />}
                </div>
                <div>
                <div className="text-[10px] uppercase tracking-widest font-black text-text-muted mb-2 flex items-center gap-2">
                    <Zap size={12} className={data.market_regime === "bull" ? "text-success" : data.market_regime === "bear" ? "text-danger" : "text-warning"} />
                    Dominant Market Regime
                </div>
                <h2 className={`text-4xl font-black tracking-tight ${
                    data.market_regime === "bull" ? "text-success drop-shadow-[0_0_10px_rgba(34,197,94,0.3)]" : data.market_regime === "bear" ? "text-danger drop-shadow-[0_0_10px_rgba(239,68,68,0.3)]" : "text-warning drop-shadow-[0_0_10px_rgba(234,179,8,0.3)]"
                }`}>
                    {data.market_regime === "bull" ? "BULLISH TREND" : data.market_regime === "bear" ? "BEARISH TREND" : "SIDEWAYS CHOP"}
                </h2>
                <p className="text-sm text-text-muted mt-2 font-mono">
                    {data.market_regime === "bull" ? `${data.up_pct ?? 0}% of global network assets trending upward` :
                    data.market_regime === "bear" ? `${data.down_pct ?? 0}% of global network assets trending downward` :
                    `Mixed signals \u2014 ${data.average_volatility?.toFixed(2) ?? "0"}% network mean volatility`}
                </p>
                </div>
            </div>
          </GlassCard>

          {/* Stats Row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {[
              { label: "Mean Volatility", value: `${data.average_volatility?.toFixed(2) ?? "0"}%`, icon: Activity, color: "text-accent" },
              { label: "Active Threats", value: String(data.risk_alerts?.length ?? 0), icon: AlertTriangle, color: data.risk_alerts?.length ? "text-warning" : "text-success" },
              { label: "Monitored Nodes", value: String(data.total_assets_monitored ?? 50), icon: Shield, color: "text-text" },
              { label: "Isomorphic Clusters", value: String(Object.keys(data.correlation_clusters || {}).length), icon: BarChart3, color: "text-accent" },
            ].map((s, i) => (
              <GlassCard key={i} tier={2} shape="shape-squircle" className="p-6 flex items-center gap-4 group hover:bg-white/[0.02] transition-colors border border-white/10 hover:border-white/20 h-32">
                <div className="p-3 rounded-sm glass bg-white/5 group-hover:bg-white/10 transition-colors shadow-inner shadow-white/5 border border-white/10">
                    <s.icon size={24} className={s.color} />
                </div>
                <div>
                  <div className="text-3xl font-black font-sans text-text tracking-tight group-hover:scale-105 transition-transform origin-left">{s.value}</div>
                  <div className="text-[10px] uppercase tracking-widest font-bold text-text-muted mt-1">{s.label}</div>
                </div>
              </GlassCard>
            ))}
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Top Volatile Assets Bar Chart */}
            <GlassCard tier={2} shape="shape-squircle" className="p-8">
                <div className="mb-8">
                  <h3 className="text-xl font-black text-text tracking-tight flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full glass bg-accent/10 border border-accent/20 flex items-center justify-center">
                          <BarChart3 className="text-accent" size={16} />
                      </div>
                      High-Frequency Volatility Nodes
                  </h3>
                  <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-2">7-Day Trailing Price Variance</p>
                </div>
                <div className="h-[300px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={topMoversData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                      <XAxis dataKey="name" stroke="rgba(255,255,255,0.3)" fontSize={10} fontFamily="monospace" tickLine={false} axisLine={false} tickMargin={10} />
                      <YAxis stroke="rgba(255,255,255,0.3)" fontSize={10} fontFamily="monospace" tickLine={false} axisLine={false} tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: "rgba(10, 10, 15, 0.9)", borderColor: "rgba(255, 255, 255, 0.1)", color: "#f1f5f9", borderRadius: "12px", backdropFilter: "blur(10px)" }} 
                        itemStyle={{ fontFamily: 'monospace', fontWeight: 'bold' }}
                        formatter={(v: any) => [`${Number(v).toFixed(2)}%`, "Volatility"]} 
                      />
                      <Bar dataKey="volatility" fill={CHART_HEX.dark.warning} radius={[4, 4, 0, 0]} className="drop-shadow-[0_0_5px_rgba(212,165,71,0.5)]" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
            </GlassCard>

            {/* Prediction Distribution Pie */}
            <GlassCard tier={2} shape="shape-squircle" className="p-8">
                <div className="mb-8">
                  <h3 className="text-xl font-black text-text tracking-tight flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full glass bg-accent/10 border border-accent/20 flex items-center justify-center">
                          <PieIcon className="text-accent" size={16} />
                      </div>
                      Network Prediction State
                  </h3>
                  <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-2">Aggregate Model Bias across all analyzed assets</p>
                </div>
                <div className="h-[300px] w-full relative">
                  {predDist.length > 0 ? (
                    <>
                        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                            <div className="w-32 h-32 rounded-full border border-white/5 flex items-center justify-center bg-surface/50 backdrop-blur-sm z-10 shadow-inner">
                                <div className="text-center">
                                    <div className="text-2xl font-black text-text">{preds?.length}</div>
                                    <div className="text-[8px] uppercase tracking-widest font-bold text-text-muted">Total Nodes</div>
                                </div>
                            </div>
                        </div>
                        <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie 
                                data={predDist} 
                                cx="50%" 
                                cy="50%" 
                                innerRadius={70}
                                outerRadius={110} 
                                dataKey="value" 
                                nameKey="name" 
                                stroke="rgba(10, 10, 15, 0.8)"
                                strokeWidth={2}
                            >
                            {predDist.map((d, i) => <Cell key={i} fill={d.color} />)}
                            </Pie>
                            <Tooltip 
                                contentStyle={{ backgroundColor: "rgba(10, 10, 15, 0.9)", borderColor: "rgba(255, 255, 255, 0.1)", borderRadius: "12px", backdropFilter: "blur(10px)", color: "#fff", fontWeight: "bold" }} 
                                itemStyle={{ fontFamily: 'monospace' }}
                            />
                            <Legend wrapperStyle={{ fontSize: 10, fontFamily: 'monospace', fontWeight: 'bold', color: "#94a3b8", paddingTop: "20px" }} iconType="circle" />
                        </PieChart>
                        </ResponsiveContainer>
                    </>
                  ) : (
                    <div className="flex items-center justify-center h-full text-text-muted font-mono border border-white/5 rounded-sm bg-surface/30">Awaiting tensor computation...</div>
                  )}
                </div>
            </GlassCard>
          </div>

          {/* Correlation Clusters */}
          {data.correlation_clusters && Object.keys(data.correlation_clusters).length > 0 && (
            <GlassCard tier={2} shape="shape-squircle" className="p-0 overflow-hidden">
              <div className="p-8 border-b border-white/5 bg-surface/30">
                <h3 className="text-xl font-black text-text tracking-tight">Topological Correlation Clusters</h3>
                <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-1">Assets exhibiting strong price action isomorphism</p>
              </div>
              <div className="p-8">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                  {Object.entries(data.correlation_clusters).slice(0, 8).map(([cluster, assets]) => (
                    <div key={cluster} className="p-5 glass bg-surface/50 rounded-sm border border-white/10 hover:border-accent/30 transition-colors group hover:shadow-[0_0_20px_rgba(var(--accent),0.1)]">
                      <div className="flex items-center justify-between mb-4">
                        <span className="font-mono text-sm font-black text-text group-hover:text-accent transition-colors">#{cluster.replace("_", "-").toUpperCase()}</span>
                        <span className="px-3 py-1 bg-accent/10 text-accent rounded-full text-[10px] font-black tracking-widest border border-accent/20 shadow-inner">
                            {assets.length} NODES
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {assets.map((sym: string) => (
                          <span key={sym} className="px-3 py-1.5 rounded-sm text-xs font-mono font-bold bg-white/5 text-text-muted border border-white/10 group-hover:bg-accent/5 group-hover:text-text group-hover:border-accent/20 transition-colors">
                            {sym}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                {Object.keys(data.correlation_clusters).length > 8 && (
                    <div className="mt-6 text-center">
                        <span className="inline-block px-6 py-2 rounded-full glass bg-white/5 border border-white/10 text-text-muted text-[10px] uppercase tracking-widest font-bold">
                            + {Object.keys(data.correlation_clusters).length - 8} Additional Subgraphs Hidden
                        </span>
                    </div>
                )}
              </div>
            </GlassCard>
          )}

          {/* Risk Alerts — Structured Cards */}
          <GlassCard tier={2} shape="shape-squircle" className="p-0 overflow-hidden border border-white/10 relative">
             <div className="absolute top-0 right-0 w-full h-1 bg-gradient-to-r from-transparent via-white/20 to-transparent opacity-50" />
             <div className="p-8 border-b border-white/5 bg-surface/30 flex items-center justify-between">
              <div>
                  <h3 className="text-xl font-black text-text tracking-tight flex items-center gap-3">
                    {data.risk_alerts?.some(a => a.severity === "high") ? <AlertTriangle className="text-danger drop-shadow-[0_0_10px_rgba(239,68,68,0.5)]" /> : <Shield className="text-success" />}
                    Threat Intelligence
                  </h3>
                  <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-1">Automated structural vulnerability detection</p>
              </div>
              <div className="hidden md:flex items-center gap-2 px-4 py-2 glass bg-white/5 border border-white/10 rounded-full text-[10px] font-bold text-text-muted uppercase tracking-widest">
                  Status: {data.risk_alerts?.length > 0 ? <span className="text-warning animate-pulse">ELEVATED</span> : <span className="text-success">NOMINAL</span>}
              </div>
            </div>
            
            <div className="p-8 bg-black/20">
              {!data.risk_alerts || data.risk_alerts.length === 0 ? (
                <div className="flex items-center justify-center py-12 glass bg-success/5 border border-success/20 rounded-sm shadow-inner shadow-success/10">
                    <div className="text-center">
                        <CheckCircle className="text-success mx-auto mb-4 drop-shadow-[0_0_10px_rgba(34,197,94,0.5)]" size={48} />
                        <span className="text-success font-black tracking-widest text-sm uppercase">All network parameters within nominal thresholds</span>
                    </div>
                </div>
              ) : (
                <ul className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {data.risk_alerts.map((alert: RiskAlert, idx: number) => {
                    const config = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.low;
                    const AlertIcon = config.icon;
                    return (
                      <li key={idx} className={`p-6 rounded-sm glass border ${config.bg} ${config.border} ${config.shadow} relative overflow-hidden group`}>
                        <div className={`absolute left-0 top-0 bottom-0 w-1 ${config.bg.replace('/10', '')} opacity-50 group-hover:opacity-100 transition-opacity`} />
                        <div className="flex gap-4 items-start relative z-10">
                          <div className={`p-3 rounded-full glass bg-background/50 border border-white/5 shadow-inner`}>
                            <AlertIcon className={`${config.text} flex-shrink-0 drop-shadow-[0_0_5px_currentColor]`} size={24} />
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center justify-between mb-2">
                                <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-sm border glass ${config.text} border-current/30`}>{alert.severity}</span>
                                <span className="text-[10px] text-text-muted font-mono uppercase tracking-widest bg-black/40 px-2 py-0.5 rounded-sm">{alert.type.replace('_', ' ')}</span>
                            </div>
                            <p className="text-text text-sm font-bold mt-3 leading-relaxed">{alert.message}</p>
                            {alert.recommendation && (
                              <div className="mt-4 p-3 bg-black/40 rounded-sm border border-white/5">
                                  <p className="text-text-muted text-xs italic flex items-center gap-2 font-serif">
                                      <span className="text-white/50 not-italic font-sans text-[10px] uppercase font-bold tracking-widest">Protocol:</span> 
                                      {alert.recommendation}
                                  </p>
                              </div>
                            )}
                            {alert.affected_assets && alert.affected_assets.length > 0 && (
                              <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-white/5">
                                {alert.affected_assets.map((sym) => (
                                  <span key={sym} className="px-2 py-1 rounded-sm text-[10px] font-mono font-bold bg-white/5 text-text-muted border border-white/10 hover:bg-white/10 transition-colors cursor-default">
                                    {sym}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </GlassCard>

          {/* Macro Environment Section */}
          {macro && (
            <div className="pt-8">
              <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 border-b border-white/10 pb-6 mb-8 relative">
                <div className="absolute bottom-0 left-0 w-32 h-px bg-gradient-to-r from-accent to-transparent" />
                <div>
                    <h2 className="text-3xl font-black text-text tracking-tight flex items-center gap-4">
                        Macro Parameters
                        {(macro.crypto_vix_correlation ?? 0) < -0.5 && <span className="text-[10px] bg-danger/20 text-danger px-3 py-1.5 rounded-sm uppercase border border-danger/30 shadow-[0_0_10px_rgba(239,68,68,0.2)] tracking-widest font-black">Risk-Off Vector Active</span>}
                    </h2>
                    <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-2">Traditional finance correlation indices</p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <GlassCard tier={2} shape="shape-squircle" className="p-6 flex items-center gap-6 group hover:border-white/20 transition-all hover:-translate-y-1">
                    <div className="p-4 rounded-sm glass bg-accent/10 text-accent border border-accent/20 group-hover:scale-110 transition-transform"><Activity size={28} /></div>
                    <div>
                      <div className="text-3xl font-black font-sans text-text tracking-tight">{(macro.current_fed_rate ?? 0).toFixed(2)}<span className="text-lg text-text-muted">%</span></div>
                      <div className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-1 mb-2">10Y Treasury Yield</div>
                      {macro.fed_rate_trend && (
                        <div className={`text-[9px] px-2 py-0.5 rounded-sm border inline-block font-black uppercase tracking-widest ${macro.fed_rate_trend === 'rising' ? 'bg-danger/10 text-danger border-danger/30' : macro.fed_rate_trend === 'falling' ? 'bg-success/10 text-success border-success/30' : 'bg-white/5 text-text-muted border-white/10'}`}>
                          VECTOR: {macro.fed_rate_trend}
                        </div>
                      )}
                    </div>
                </GlassCard>
                <GlassCard tier={2} shape="shape-squircle" className="p-6 flex items-center gap-6 group hover:border-white/20 transition-all hover:-translate-y-1">
                    <div className="p-4 rounded-sm glass bg-warning/10 text-warning border border-warning/20 group-hover:scale-110 transition-transform"><TrendingUp size={28} /></div>
                    <div>
                      <div className="text-3xl font-black font-sans text-text tracking-tight">{(macro.current_vix ?? 0).toFixed(1)}</div>
                      <div className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-1 mb-2">VIX Fear Gauge</div>
                      {macro.vix_regime && (
                        <div className={`text-[9px] px-2 py-0.5 rounded-sm border inline-block font-black uppercase tracking-widest ${macro.vix_regime === 'extreme_fear' ? 'bg-danger/10 text-danger border-danger/30 shadow-[0_0_10px_rgba(239,68,68,0.2)]' : macro.vix_regime === 'elevated' ? 'bg-warning/10 text-warning border-warning/30' : 'bg-success/10 text-success border-success/30'}`}>
                          STATE: {macro.vix_regime.replace('_', ' ')}
                        </div>
                      )}
                    </div>
                </GlassCard>
                <GlassCard tier={2} shape="shape-squircle" className="p-6 flex items-center gap-6 group hover:border-white/20 transition-all hover:-translate-y-1">
                    <div className="p-4 rounded-sm glass bg-danger/10 text-danger border border-danger/20 group-hover:scale-110 transition-transform"><AlertTriangle size={28} /></div>
                    <div>
                      <div className="text-3xl font-black font-sans text-text tracking-tight">{(macro.crypto_vix_correlation ?? 0).toFixed(3)}</div>
                      <div className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-1 mb-2">Network / VIX Correlation</div>
                    </div>
                </GlassCard>
              </div>

              {macro.history && macro.history.length > 0 && (
                <GlassCard tier={2} shape="shape-squircle" className="p-8">
                  <div className="mb-8">
                    <h3 className="text-xl font-black text-text tracking-tight flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full glass bg-warning/10 border border-warning/20 flex items-center justify-center">
                            <TrendingUp className="text-warning" size={16} />
                        </div>
                        Volatility Trajectory
                    </h3>
                    <p className="text-[10px] text-text-muted uppercase tracking-widest font-bold mt-2">60-Day Historic VIX Window</p>
                  </div>
                  <div className="h-[320px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={macro.history} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                        <XAxis dataKey="date" stroke="rgba(255,255,255,0.3)" fontSize={10} fontFamily="monospace" tickLine={false} axisLine={false} minTickGap={30} />
                        <YAxis stroke="rgba(255,255,255,0.3)" fontSize={10} fontFamily="monospace" tickLine={false} axisLine={false} />
                        <Tooltip 
                            contentStyle={{ backgroundColor: "rgba(10, 10, 15, 0.9)", borderColor: "rgba(255, 255, 255, 0.1)", borderRadius: "12px", color: "#fff", backdropFilter: "blur(10px)" }} 
                            itemStyle={{ fontFamily: 'monospace', fontWeight: 'bold' }}
                            labelStyle={{ color: 'rgba(255,255,255,0.5)', marginBottom: '8px' }}
                        />
                        <defs>
                            <linearGradient id="vixGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="rgba(234, 179, 8, 0.3)" stopOpacity={1}/>
                                <stop offset="95%" stopColor="rgba(234, 179, 8, 0)" stopOpacity={0}/>
                            </linearGradient>
                        </defs>
                        <Area type="monotone" dataKey="vix" fill="url(#vixGrad)" stroke="none" />
                        <Line type="monotone" dataKey="vix" name="VIX Level" stroke={CHART_HEX.dark.warning} dot={false} strokeWidth={3} className="drop-shadow-[0_0_5px_rgba(234,179,8,0.5)]" />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </GlassCard>
              )}
            </div>
          )}

        </div>
      )}
      <ScrollToTop />
    </div>
  );
}

