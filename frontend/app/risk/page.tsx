"use client";

import useSWR from "swr";
import { fetcher, RiskData } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  RefreshCcw, AlertTriangle, TrendingUp, TrendingDown, Minus,
  Shield, Activity, BarChart3, PieChart as PieIcon, CheckCircle
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, AreaChart, Area, ComposedChart, Line
} from "recharts";
import { ScrollToTop } from "@/components/ScrollToTop";

interface PredictionRow {
  asset_symbol: string;
  direction: string;
  confidence: number;
  volatility_regime: string;
  predicted_at: string;
  model_version: string;
}

const DIRECTION_COLORS: Record<string, string> = {
  strong_up: "#16a34a", up: "#22c55e", neutral: "#64748b", down: "#ef4444", strong_down: "#991b1b",
};
const DIRECTION_LABELS: Record<string, string> = {
  strong_up: "Strong Buy", up: "Buy", neutral: "Neutral", down: "Sell", strong_down: "Strong Sell",
};

export default function RiskPage() {
  const { data, error, isLoading, mutate } = useSWR<RiskData>("/api/risk", fetcher, {
    revalidateOnFocus: false, dedupingInterval: 30000,
  });
  const { data: preds } = useSWR<PredictionRow[]>("/api/predictions?limit=50", fetcher, {
    revalidateOnFocus: false, dedupingInterval: 30000,
  });
  const { data: macro } = useSWR("/api/risk/macro", fetcher, {
    revalidateOnFocus: false, dedupingInterval: 30000,
  });

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full space-y-4">
        <div className="text-danger bg-danger/10 p-4 rounded-md border border-danger/20">Failed to load risk data</div>
        <button onClick={() => mutate()} className="flex items-center gap-2 px-4 py-2 bg-surface hover:bg-border transition-colors rounded-md text-text border border-border">
          <RefreshCcw size={16} /> Retry
        </button>
      </div>
    );
  }

  // Compute prediction distribution for pie chart
  const predDist = preds ? Object.entries(
    preds.reduce((acc, p) => { acc[p.direction] = (acc[p.direction] || 0) + 1; return acc; }, {} as Record<string, number>)
  ).map(([dir, count]) => ({
    name: DIRECTION_LABELS[dir] || dir,
    value: count,
    color: DIRECTION_COLORS[dir] || "#64748b",
  })) : [];

  const topMoversData = data?.top_movers.map(m => ({
    name: m.symbol,
    volatility: m.volatility_7d,
  })) || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-text">Risk Dashboard</h1>
        <p className="text-textMuted mt-1">Market regime, volatility, and correlation analysis</p>
      </div>

      {isLoading || !data ? (
        <div className="space-y-6">
          <Skeleton className="h-28 w-full" />
          <div className="grid grid-cols-4 gap-4">{Array.from({length: 4}).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
          <div className="grid grid-cols-2 gap-6"><Skeleton className="h-[340px]" /><Skeleton className="h-[340px]" /></div>
        </div>
      ) : (
        <>
          {/* Regime Banner */}
          <div className={`p-6 rounded-xl border flex items-center gap-6 ${
            data.market_regime === "bull"
              ? "bg-green-900/60 border-green-500/50"
              : data.market_regime === "bear"
                ? "bg-red-900/60 border-red-500/50"
                : "bg-amber-900/60 border-amber-500/50"
          }`}>
            <div className={`p-3 rounded-full ${
              data.market_regime === "bull" ? "bg-green-800" : data.market_regime === "bear" ? "bg-red-800" : "bg-amber-800"
            }`}>
              {data.market_regime === "bull" ? <TrendingUp size={32} className="text-green-400" /> :
               data.market_regime === "bear" ? <TrendingDown size={32} className="text-red-400" /> :
               <Minus size={32} className="text-amber-400" />}
            </div>
            <div>
              <h2 className={`text-2xl font-bold ${
                data.market_regime === "bull" ? "text-green-400" : data.market_regime === "bear" ? "text-red-400" : "text-amber-400"
              }`}>
                {data.market_regime === "bull" ? "\uD83D\uDFE2 Bull Market" : data.market_regime === "bear" ? "\uD83D\uDD34 Bear Market" : "\u26AA Sideways Market"}
              </h2>
              <p className="text-sm text-textMuted mt-1">
                {data.market_regime === "bull" ? `${data.up_pct ?? 0}% of assets trending upward` :
                 data.market_regime === "bear" ? `${data.down_pct ?? 0}% of assets trending downward` :
                 `Mixed signals \u2014 ${data.average_volatility?.toFixed(2) ?? "0"}% average volatility`}
              </p>
            </div>
          </div>

          {/* Stats Row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "Avg Volatility", value: `${data.average_volatility?.toFixed(2) ?? "0"}%`, icon: Activity },
              { label: "Active Alerts", value: String(data.risk_alerts?.length ?? 0), icon: AlertTriangle },
              { label: "Tracked Assets", value: "50", icon: Shield },
              { label: "Clusters", value: String(Object.keys(data.correlation_clusters || {}).length), icon: BarChart3 },
            ].map((s, i) => (
              <Card key={i}>
                <CardContent className="p-4 flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-accent/10"><s.icon size={20} className="text-accent" /></div>
                  <div>
                    <div className="text-2xl font-bold font-mono text-text">{s.value}</div>
                    <div className="text-xs text-textMuted">{s.label}</div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Top Movers Bar Chart */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><BarChart3 className="text-accent" size={18} /> Top Volatile Assets</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-[280px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={topMoversData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" vertical={false} />
                      <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                      <YAxis stroke="#94a3b8" fontSize={11} tickLine={false} axisLine={false} tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} />
                      <Tooltip contentStyle={{ backgroundColor: "#1a1a1a", borderColor: "#2a2a2a", color: "#f1f5f9", borderRadius: 8 }} formatter={(v: number) => [`${(v * 100).toFixed(2)}%`, "Volatility"]} />
                      <Bar dataKey="volatility" fill="#6366f1" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Prediction Distribution Pie */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><PieIcon className="text-accent" size={18} /> Prediction Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-[280px] w-full">
                  {predDist.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={predDist} cx="50%" cy="45%" outerRadius={90} dataKey="value" nameKey="name" label={({ name, percent }: any) => `${name} ${(percent * 100).toFixed(0)}%`} labelLine={false} fontSize={11}>
                          {predDist.map((d, i) => <Cell key={i} fill={d.color} />)}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: "#1a1a1a", borderColor: "#2a2a2a", borderRadius: 8 }} />
                        <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center h-full text-textMuted">No prediction data</div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Correlation Clusters */}
          {data.correlation_clusters && Object.keys(data.correlation_clusters).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Correlation Clusters</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {Object.entries(data.correlation_clusters).slice(0, 8).map(([cluster, assets]) => (
                    <div key={cluster} className="p-4 bg-background rounded-lg border border-border">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="font-mono text-sm font-bold text-text">{cluster.replace("_", " ").toUpperCase()}</span>
                        <span className="px-2 py-0.5 bg-accent/10 text-accent rounded-full text-xs font-mono">{assets.length} assets</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {assets.map((sym: string) => (
                          <span key={sym} className="px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-accent/10 text-accent border border-accent/20">
                            {sym}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                  {Object.keys(data.correlation_clusters).length > 8 && (
                    <div className="p-4 flex items-center justify-center text-textMuted text-sm">
                      and {Object.keys(data.correlation_clusters).length - 8} more clusters...
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Risk Alerts */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {data.risk_alerts?.length > 0 ? <AlertTriangle className="text-warning" /> : <CheckCircle className="text-success" />}
                {data.risk_alerts?.length > 0 ? "Active Risk Alerts" : "Risk Status"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!data.risk_alerts || data.risk_alerts.length === 0 ? (
                <div className="flex items-center gap-3 p-4 bg-green-900/20 border border-green-800/30 rounded-lg">
                  <CheckCircle className="text-success" size={20} />
                  <span className="text-success">All systems normal — no active risk alerts</span>
                </div>
              ) : (
                <ul className="space-y-3">
                  {data.risk_alerts.map((alert: string, idx: number) => (
                    <li key={idx} className="flex gap-3 p-3 bg-amber-900/20 border border-amber-800/30 rounded-lg">
                      <AlertTriangle className="text-warning mt-0.5 flex-shrink-0" size={16} />
                      <span className="text-text text-sm">{alert}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {/* Macro Environment Section */}
          {macro && (
            <div className="mt-8 space-y-6">
              <h2 className="text-2xl font-bold text-text font-mono flex items-center gap-2 border-b border-border pb-2">
                Macro Environment
                {macro.vix_btc_correlation < -0.5 && <span className="text-[10px] bg-red-900/50 text-red-400 px-2 py-1 rounded-full uppercase ml-2 border border-red-800">Risk-Off Detected</span>}
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                  <CardContent className="p-4 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-blue-900/20 text-blue-400"><Activity size={20} /></div>
                    <div>
                      <div className="text-2xl font-bold font-mono text-text">{(macro.indicators?.[macro.indicators.length-1]?.fed_rate || 0).toFixed(2)}%</div>
                      <div className="text-xs text-textMuted">Fed Funds Rate</div>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-orange-900/20 text-orange-400"><TrendingUp size={20} /></div>
                    <div>
                      <div className="text-2xl font-bold font-mono text-text">{(macro.indicators?.[macro.indicators.length-1]?.cpi || 0).toFixed(1)}</div>
                      <div className="text-xs text-textMuted">CPI</div>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-red-900/20 text-red-400"><AlertTriangle size={20} /></div>
                    <div>
                      <div className="text-2xl font-bold font-mono text-text">{(macro.vix_btc_correlation || 0).toFixed(2)}</div>
                      <div className="text-xs text-textMuted">VIX/BTC Correlation</div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader>
                  <CardTitle>Macro Indicators Trend</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="h-[300px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={macro.indicators} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" vertical={false} />
                        <XAxis dataKey="date" stroke="#94a3b8" fontSize={10} tickLine={false} axisLine={false} minTickGap={30} />
                        <YAxis yAxisId="left" stroke="#3b82f6" fontSize={10} tickLine={false} axisLine={false} orientation="left" />
                        <YAxis yAxisId="right" stroke="#f97316" fontSize={10} tickLine={false} axisLine={false} orientation="right" />
                        <Tooltip contentStyle={{ backgroundColor: "#1a1a1a", borderColor: "#2a2a2a", borderRadius: 8, color: "#fff" }} />
                        <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
                        <Line yAxisId="left" type="monotone" dataKey="fed_rate" name="Fed Rate" stroke="#3b82f6" dot={false} strokeWidth={2} />
                        <Line yAxisId="right" type="monotone" dataKey="vix" name="VIX" stroke="#f97316" dot={false} strokeWidth={2} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

        </>
      )}
      <ScrollToTop />
    </div>
  );
}
