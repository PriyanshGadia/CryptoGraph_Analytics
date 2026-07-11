"use client";
import React, { useState, useEffect } from "react";

import useSWR from "swr";
import { fetcher, apiService, PortfolioResponse, PortfolioTradesResponse, TradeRecord } from "@/lib/api";
import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { useChartPalette } from "@/lib/useChartPalette";
import { ComposedChart, Area, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { 
  TrendingUp, 
  TrendingDown, 
  Wallet, 
  PieChart, 
  Activity, 
  Target,
  ArrowRightLeft,
  DollarSign,
  Play,
  ChevronDown,
  ChevronUp,
  Star,
  Save,
  MessageSquare,
  Zap,
  ShieldCheck,
  RotateCcw
} from "lucide-react";

export default function PortfolioPage() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const { data: portfolio, error: pErr, mutate: mutatePortfolio } = useSWR<PortfolioResponse>("/api/v1/portfolio", fetcher, {
    refreshInterval: 60000,
  });
  
  const { data: tradesData, error: tErr, mutate: mutateTrades } = useSWR<PortfolioTradesResponse>("/api/v1/portfolio/trades?limit=50", fetcher, {
    refreshInterval: 60000,
  });

  const [executing, setExecuting] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [stressTest, setStressTest] = useState(false);
  const palette = useChartPalette();
  const [expandedTradeId, setExpandedTradeId] = useState<number | null>(null);
  
  // Grading form state
  const [grade, setGrade] = useState<number>(0);
  const [notes, setNotes] = useState<string>("");
  const [submittingGrade, setSubmittingGrade] = useState(false);
  const [signingTradeId, setSigningTradeId] = useState<number | null>(null);

  if (!mounted) return <div className="h-screen w-full flex items-center justify-center text-text-muted font-mono bg-background">Loading chart components...</div>;

  const handleManualExecute = async () => {
    if (executing || resetting) return;
    setExecuting(true);
    try {
      await apiService.triggerExecution();
      await mutatePortfolio();
      await mutateTrades();
    } catch (e) {
      console.error("Failed to execute agent", e);
    } finally {
      setExecuting(false);
    }
  };

  const handleResetPortfolio = async () => {
    if (resetting || executing) return;
    if (!confirm("Are you sure you want to reset paper trading portfolio to $100,000 initial capital?")) return;
    setResetting(true);
    try {
      await apiService.resetPortfolio();
      await mutatePortfolio();
      await mutateTrades();
    } catch (e) {
      console.error("Failed to reset portfolio", e);
    } finally {
      setResetting(false);
    }
  };

  const handleExpand = (trade: TradeRecord) => {
    if (expandedTradeId === trade.id) {
      setExpandedTradeId(null);
    } else {
      setExpandedTradeId(trade.id);
      setGrade(trade.overseer_grade || 0);
      setNotes(trade.overseer_notes || "");
    }
  };

  const submitGrade = async (tradeId: number) => {
    if (grade === 0) return;
    setSubmittingGrade(true);
    try {
      await apiService.gradeTrade(tradeId, grade, notes);
      await mutateTrades();
      setExpandedTradeId(null);
    } catch (e) {
      console.error("Failed to submit grade", e);
    } finally {
      setSubmittingGrade(false);
    }
  };

  const handleWeb3Sign = async (trade: TradeRecord) => {
    setSigningTradeId(trade.id);
    try {
      console.log("Logging Simulated Paper Trade for:", {
        asset: trade.symbol,
        side: trade.side,
        amount: trade.total_usd
      });
      
      // Delay for visual feedback of logging
      await new Promise(resolve => setTimeout(resolve, 800));
      const simulatedTxId = "paper_trade_" + Date.now();
      
      await apiService.confirmWeb3Trade(trade.id, simulatedTxId);
      await mutateTrades();
      await mutatePortfolio();
    } catch (e) {
      console.error("Failed to log paper trade", e);
    } finally {
      setSigningTradeId(null);
    }
  };

  if (pErr || tErr) {
    return (
      <div className="p-8 text-danger flex items-center justify-center font-mono">
        <Activity className="mr-2" /> Failed to load portfolio data.
      </div>
    );
  }

  if (!portfolio) {
    return (
      <div className="space-y-8 pt-8">
        <h1 className="text-4xl font-black text-text font-sans">Autonomous Portfolio</h1>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Skeleton className="h-32 w-full rounded-sm" />
          <Skeleton className="h-32 w-full rounded-sm" />
          <Skeleton className="h-32 w-full rounded-sm" />
          <Skeleton className="h-32 w-full rounded-sm" />
        </div>
      </div>
    );
  }

  const trades = tradesData?.trades || [];

  return (
    <div className="space-y-8 pt-8 p-6 glass-2 rounded-2xl overflow-hidden max-w-7xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 relative">
        <div className="absolute top-[-50px] left-[-50px] w-64 h-64 bg-accent/5 rounded-full blur-[80px] pointer-events-none" />
        <div className="relative z-10">
          <h1 className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted tracking-tight font-sans">Autonomous Portfolio</h1>
          <p className="text-text-muted font-light tracking-wide mt-2">Paper-trading performance driven by ST-GCN agent signals.</p>
        </div>
        <div className="relative z-10 flex items-center gap-3">
          <button
            onClick={handleResetPortfolio}
            disabled={resetting || executing}
            className="flex items-center justify-center gap-2 glass bg-danger/10 hover:bg-danger/20 text-danger px-5 py-4 rounded-sm font-bold transition-all disabled:opacity-50 border border-danger/30 tracking-widest uppercase text-xs"
            title="Reset paper trading capital to $100,000"
          >
            {resetting ? (
              <div className="w-4 h-4 border-2 border-danger/30 border-t-danger rounded-full animate-spin" />
            ) : (
              <RotateCcw size={16} />
            )}
            {resetting ? "Resetting..." : "Reset"}
          </button>

          <button
            onClick={handleManualExecute}
            disabled={executing || resetting}
            className="flex items-center justify-center gap-3 glass bg-accent/20 hover:bg-accent/30 text-accent px-8 py-4 rounded-sm font-bold transition-all disabled:opacity-50 border border-accent/30 shadow-[0_0_20px_rgba(var(--accent),0.1)] hover:shadow-[0_0_30px_rgba(var(--accent),0.2)] tracking-widest uppercase text-xs"
          >
            {executing ? (
              <div className="w-5 h-5 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
            ) : (
              <Play size={18} fill="currentColor" />
            )}
            {executing ? "Executing Strategy..." : "Force Execution"}
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <GlassCard tier={2} shape="none" className="rounded-xl p-6 relative overflow-hidden group interactive-lift">
          <div className="absolute inset-0 bg-gradient-to-br from-accent/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <div className="text-[10px] font-bold font-mono tracking-widest text-text-muted uppercase mb-4 flex items-center gap-2">
            <Wallet size={16} className="text-accent" /> Total Value
          </div>
          <div className="text-4xl font-black text-text font-mono tracking-tight">
            ${portfolio.total_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-xs mt-3 text-text-muted font-mono bg-text/5 inline-block px-2 py-1 rounded border border-text/5">
            Cash: ${portfolio.cash_balance.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
        </GlassCard>

        <GlassCard tier={2} shape="none" className="rounded-xl p-6 relative overflow-hidden group interactive-lift">
          <div className="absolute inset-0 bg-gradient-to-br from-success/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <div className="text-[10px] font-bold font-mono tracking-widest text-text-muted uppercase mb-4 flex items-center gap-2">
            <Activity size={16} className="text-success" /> Return on Investment
          </div>
          <div className={`text-4xl font-black font-mono tracking-tight flex items-center gap-2 ${portfolio.roi_pct >= 0 ? 'text-success' : 'text-danger'}`}>
            {portfolio.roi_pct >= 0 ? <TrendingUp size={28} /> : <TrendingDown size={28} />}
            {portfolio.roi_pct > 0 ? "+" : ""}{portfolio.roi_pct.toFixed(2)}%
          </div>
          <div className="text-xs mt-3 text-text-muted font-mono flex items-center justify-between border-t border-text/5 pt-2">
            <span>vs BTC Benchmark:</span>
            <span className={portfolio.roi_pct >= portfolio.btc_roi_pct ? 'text-success font-bold' : 'text-danger font-bold'}>
              {portfolio.btc_roi_pct > 0 ? "+" : ""}{portfolio.btc_roi_pct.toFixed(2)}%
            </span>
          </div>
        </GlassCard>

        <GlassCard tier={2} shape="none" className="rounded-xl p-6 relative overflow-hidden group interactive-lift">
          <div className="absolute inset-0 bg-gradient-to-br from-warning/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <div className="text-[10px] font-bold font-mono tracking-widest text-text-muted uppercase mb-4 flex items-center gap-2">
            <Target size={16} className="text-warning" /> Win Rate
          </div>
          <div className="text-4xl font-black text-text font-mono tracking-tight">
            {portfolio.win_rate.toFixed(1)}%
          </div>
          <div className="text-xs mt-3 text-text-muted font-mono">
            {portfolio.total_trades} total trades executed
          </div>
        </GlassCard>

        <GlassCard tier={2} shape="none" className="rounded-xl p-6 relative overflow-hidden group interactive-lift">
          <div className="absolute inset-0 bg-gradient-to-br from-danger/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <div className="text-[10px] font-bold font-mono tracking-widest text-text-muted uppercase mb-4 flex items-center gap-2">
            <TrendingDown size={16} className="text-danger" /> Max Drawdown
          </div>
          <div className="text-4xl font-black text-danger font-mono tracking-tight">
            -{portfolio.max_drawdown_pct.toFixed(2)}%
          </div>
          <div className="text-xs mt-3 text-text-muted font-mono">
            Since inception
          </div>
        </GlassCard>
      </div>

      {/* Main Performance Chart */}
      <GlassCard tier={2} shape="none" className="rounded-xl p-8 relative overflow-hidden">
        <div className="flex justify-between items-center mb-6">
           <div>
             <h2 className="text-xl font-black text-text flex items-center gap-2 tracking-tight"><TrendingUp size={20} className="text-accent"/> Equity Curve</h2>
             <p className="text-xs text-text-muted mt-1 font-mono uppercase tracking-widest">Portfolio vs BTC Benchmark</p>
           </div>
           <div className="flex items-center gap-3 bg-surface/50 p-2 rounded-sm border border-text/10">
              <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">Stress Test</span>
              <button 
                onClick={() => setStressTest(!stressTest)}
                className={`w-10 h-5 rounded-full relative transition-colors ${stressTest ? 'bg-danger/80' : 'bg-text/10'}`}
              >
                <div className={`absolute top-1 left-1 w-3 h-3 rounded-full bg-text transition-transform ${stressTest ? 'translate-x-5' : ''}`} />
              </button>
           </div>
        </div>
        <div className="h-[400px] w-full mt-4">
           <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0} initialDimension={{ width: 100, height: 100 }}>
             <ComposedChart data={portfolio.equity_curve.map(pt => ({
                ...pt, 
                date: new Date(pt.timestamp).toLocaleDateString(),
                projected_drawdown: stressTest ? pt.portfolio * (1 - (portfolio.max_drawdown_pct / 100)) : undefined
             }))} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
               <defs>
                 <linearGradient id="colorPortfolio" x1="0" y1="0" x2="0" y2="1">
                   <stop offset="5%" stopColor={palette.accent} stopOpacity={0.3}/>
                   <stop offset="95%" stopColor={palette.accent} stopOpacity={0}/>
                 </linearGradient>
                 <linearGradient id="colorBTC" x1="0" y1="0" x2="0" y2="1">
                   <stop offset="5%" stopColor={palette.muted} stopOpacity={0.2}/>
                   <stop offset="95%" stopColor={palette.muted} stopOpacity={0}/>
                 </linearGradient>
               </defs>
               <CartesianGrid strokeDasharray="3 3" stroke={palette.muted} strokeOpacity={0.1} vertical={false} />
               <XAxis dataKey="date" stroke={palette.muted} fontSize={10} fontFamily="monospace" tickLine={false} axisLine={false} minTickGap={30} />
               <YAxis yAxisId="left" stroke={palette.text} fontSize={10} fontFamily="monospace" tickLine={false} axisLine={false} tickFormatter={(v) => '$' + v.toLocaleString()} domain={['auto', 'auto']} />
               <Tooltip 
                 contentStyle={{ backgroundColor: "rgba(var(--background), 0.9)", borderColor: "rgba(var(--text), 0.1)", borderRadius: "12px", color: palette.text, backdropFilter: "blur(10px)" }} 
                 itemStyle={{ fontFamily: 'monospace', fontWeight: 'bold' }} 
                 formatter={(value) => '$' + Number(value).toLocaleString(undefined, {maximumFractionDigits:2})}
               />
               <Area yAxisId="left" type="monotone" dataKey="portfolio" stroke={palette.accent} strokeWidth={3} fillOpacity={1} fill="url(#colorPortfolio)" name="Portfolio" />
               <Area yAxisId="left" type="monotone" dataKey="btc_benchmark" stroke={palette.muted} strokeWidth={2} fillOpacity={1} fill="url(#colorBTC)" name="BTC Benchmark" />
               {stressTest && (
                 <Line yAxisId="left" type="stepAfter" dataKey="projected_drawdown" stroke={palette.danger} strokeWidth={2} strokeDasharray="5 5" name="- Max Drawdown" dot={false} activeDot={false} />
               )}
             </ComposedChart>
           </ResponsiveContainer>
        </div>
      </GlassCard>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Holdings */}
        <GlassCard tier={2} shape="none" className="rounded-xl p-0 overflow-hidden lg:col-span-1 flex flex-col h-[600px]">
          <div className="p-6 border-b border-text/5 bg-surface/30">
            <h2 className="flex items-center gap-3 text-lg font-black text-text tracking-tight">
              <PieChart size={20} className="text-accent" />
              Current Holdings
            </h2>
            <p className="text-xs text-text-muted mt-2 font-mono tracking-widest uppercase">Active positions across assets</p>
          </div>
          <div className="p-6 flex-1 overflow-auto custom-scrollbar">
            {Object.keys(portfolio.holdings).length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-text-muted text-center space-y-4">
                <Wallet className="opacity-20 text-accent" size={48} />
                <div className="text-sm font-mono tracking-widest uppercase">No active holdings.<br/>100% in cash.</div>
              </div>
            ) : (
              <div className="space-y-3">
                {Object.entries(portfolio.holdings).map(([symbol, data]: [string, any]) => {
                  const avgPrice = data.total_invested / data.qty;
                  return (
                    <div key={symbol} className="flex items-center justify-between p-4 bg-surface/40 hover:bg-text/5 rounded-sm border border-text/5 transition-colors group">
                      <div>
                        <div className="font-black text-lg text-text tracking-tight group-hover:text-accent transition-colors">{symbol}</div>
                        <div className="text-[10px] text-text-muted font-mono mt-1">{data.qty.toFixed(4)} tokens</div>
                      </div>
                      <div className="text-right">
                        <div className="font-bold text-text font-mono">${data.total_invested.toLocaleString(undefined, {maximumFractionDigits: 2})}</div>
                        <div className="text-[10px] text-text-muted font-mono mt-1">Avg: ${avgPrice.toLocaleString(undefined, {maximumFractionDigits: 2})}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </GlassCard>

        {/* Recent Trades */}
        <GlassCard tier={2} shape="none" className="rounded-xl p-0 overflow-hidden lg:col-span-2 flex flex-col h-[600px]">
          <div className="p-6 border-b border-text/5 bg-surface/30">
            <h2 className="flex items-center gap-3 text-lg font-black text-text tracking-tight">
              <ArrowRightLeft size={20} className="text-accent" />
              Recent Trade Execution
            </h2>
            <p className="text-xs text-text-muted mt-2 font-mono tracking-widest uppercase">Latest automated paper trades</p>
          </div>
          <div className="flex-1 overflow-auto custom-scrollbar">
            {trades.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-text-muted space-y-4">
                <ArrowRightLeft className="opacity-20 text-accent" size={48} />
                <div className="text-sm font-mono tracking-widest uppercase">No trades executed yet.</div>
              </div>
            ) : (
              <div className="min-w-full">
                <table className="w-full text-sm text-left">
                  <thead className="text-[10px] text-text-muted uppercase tracking-widest font-mono border-b border-text/10 bg-surface/50 sticky top-0 z-10 backdrop-blur-md">
                    <tr>
                      <th className="px-6 py-4 font-bold">Date</th>
                      <th className="px-6 py-4 font-bold">Asset</th>
                      <th className="px-6 py-4 font-bold">Type</th>
                      <th className="px-6 py-4 font-bold">Amount</th>
                      <th className="px-6 py-4 font-bold">Price</th>
                      <th className="px-6 py-4 font-bold text-right">Total / PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((trade: TradeRecord) => (
                      <React.Fragment key={trade.id}>
                        <tr 
                          onClick={() => handleExpand(trade)}
                          className={`border-b border-text/5 last:border-0 hover:bg-text/[0.02] transition-colors cursor-pointer group ${expandedTradeId === trade.id ? 'bg-text/[0.02]' : ''}`}
                        >
                          <td className="px-6 py-4 whitespace-nowrap text-text-muted font-mono text-[10px] flex items-center gap-3">
                            <div className={`p-1 rounded bg-text/5 ${expandedTradeId === trade.id ? 'text-accent' : ''}`}>
                                {expandedTradeId === trade.id ? <ChevronUp size={12} /> : <ChevronDown size={12} className="opacity-50 group-hover:opacity-100" />}
                            </div>
                            {new Date(trade.timestamp).toLocaleDateString()} <span className="opacity-50">{new Date(trade.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                          </td>
                          <td className="px-6 py-4 font-black text-text tracking-tight">{trade.symbol}</td>
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-2">
                              <span className={`inline-block px-2 py-1 rounded text-[9px] font-bold uppercase tracking-widest border ${trade.side === 'buy' ? 'bg-success/10 text-success border-success/20' : 'bg-danger/10 text-danger border-danger/20'}`}>
                                {trade.side}
                              </span>
                              {trade.confidence ? (
                                <span className="text-[10px] font-mono font-bold text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded" title="Signal Confidence at execution">
                                  {trade.confidence.toFixed(1)}%
                                </span>
                              ) : null}
                            </div>
                          </td>
                          <td className="px-6 py-4 text-text font-mono text-xs">{trade.quantity.toLocaleString(undefined, {maximumFractionDigits: 4})}</td>
                          <td className="px-6 py-4 text-text font-mono text-xs">${trade.price.toLocaleString(undefined, {maximumFractionDigits: 2})}</td>
                          <td className="px-6 py-4 text-right">
                            <div className="font-bold text-text font-mono flex items-center justify-end gap-3">
                              {trade.status === "PENDING_WEB3_SIGNATURE" || trade.status === "PENDING" ? (
                                <span className="inline-block px-2 py-0.5 rounded text-[8px] bg-warning/10 text-warning border border-warning/20 uppercase tracking-widest font-bold animate-pulse">
                                  Action Req
                                </span>
                              ) : trade.overseer_grade ? (
                                <div className="flex text-warning gap-0.5" title={`Graded ${trade.overseer_grade} Stars`}>
                                  {[...Array(trade.overseer_grade)].map((_, i) => <Star key={i} size={10} fill="currentColor" />)}
                                </div>
                              ) : null}
                              ${trade.total_usd.toLocaleString(undefined, {maximumFractionDigits: 2})}
                            </div>
                            {trade.side === 'sell' && trade.pnl !== undefined && trade.status === "EXECUTED" && (
                              <div className={`text-[10px] font-mono mt-1 ${trade.pnl > 0 ? 'text-success' : 'text-danger'}`}>
                                {trade.pnl > 0 ? '+' : ''}${trade.pnl.toLocaleString(undefined, {maximumFractionDigits: 2})} PnL
                              </div>
                            )}
                          </td>
                        </tr>
                        
                        {expandedTradeId === trade.id && (
                          <tr className="bg-surface/20 border-b border-text/10">
                            <td colSpan={6} className="p-0">
                                <div className="p-6 animate-in fade-in slide-in-from-top-2">
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 glass-panel bg-black/20 p-6 rounded-sm border border-text/5 shadow-inner">
                                        
                                        {/* Debate Transcript */}
                                        <div className="space-y-4">
                                        <h4 className="text-xs font-bold text-accent mb-4 flex items-center gap-2 tracking-widest uppercase font-mono">
                                            <MessageSquare size={14} />
                                            Multi-Agent Debate Transcript
                                        </h4>
                                        {trade.debate ? (
                                            <div className="space-y-4 text-sm font-light tracking-wide">
                                            <div className="bg-surface/50 p-4 rounded-sm border border-text/5">
                                                <span className="font-mono text-[10px] text-text-muted block mb-2 uppercase tracking-widest border-b border-text/5 pb-2">Macro Economist</span>
                                                <p className="text-text/90 leading-relaxed text-xs">{trade.debate.macro_analysis}</p>
                                            </div>
                                            <div className="bg-surface/50 p-4 rounded-sm border border-text/5">
                                                <span className="font-mono text-[10px] text-text-muted block mb-2 uppercase tracking-widest border-b border-text/5 pb-2">On-Chain Detective</span>
                                                <p className="text-text/90 leading-relaxed text-xs">{trade.debate.onchain_analysis}</p>
                                            </div>
                                            <div className="bg-surface/50 p-4 rounded-sm border border-text/5">
                                                <span className="font-mono text-[10px] text-text-muted block mb-2 uppercase tracking-widest border-b border-text/5 pb-2">Sentiment Analyst</span>
                                                <p className="text-text/90 leading-relaxed text-xs">{trade.debate.sentiment_analysis}</p>
                                            </div>
                                            <div className="bg-accent/10 p-4 rounded-sm border border-accent/20">
                                                <span className="font-mono text-[10px] text-accent font-bold block mb-2 uppercase tracking-widest border-b border-accent/20 pb-2 flex items-center gap-2"><Star size={10} fill="currentColor"/> CIO Verdict</span>
                                                <p className="text-text leading-relaxed whitespace-pre-wrap text-sm">{trade.debate.cio_reasoning}</p>
                                            </div>
                                            </div>
                                        ) : (
                                            <div className="text-text-muted text-xs italic py-4 font-mono">No debate transcript available.</div>
                                        )}
                                        </div>

                                        {/* Overseer Grading */}
                                        <div className="md:border-l md:border-text/10 md:pl-8 flex flex-col justify-between">
                                            <div>
                                                <h4 className="text-xs font-bold text-warning mb-2 flex items-center gap-2 tracking-widest uppercase font-mono">
                                                    <Target size={14} />
                                                    Overseer Grading (RLHF)
                                                </h4>
                                                <p className="text-[10px] text-text-muted mb-6 font-mono leading-relaxed">
                                                    Grade the CIO&apos;s logic. 1-star and 5-star trades will be injected into future prompts as Few-Shot learning examples.
                                                </p>
                                                
                                                <div className="space-y-6">
                                                    <div>
                                                    <label className="block text-[10px] font-bold font-mono text-text-muted mb-3 uppercase tracking-widest">Assign Grade</label>
                                                    <div className="flex items-center gap-3 bg-surface/50 p-3 rounded-sm border border-text/5 w-fit">
                                                        {[1, 2, 3, 4, 5].map((star) => (
                                                        <button
                                                            key={star}
                                                            onClick={() => setGrade(star)}
                                                            className={`transition-all hover:scale-110 ${grade >= star ? "text-warning drop-shadow-[0_0_8px_rgba(var(--warning),0.5)]" : "text-text-muted/40 hover:text-warning/50"}`}
                                                        >
                                                            <Star size={28} fill={grade >= star ? "currentColor" : "none"} strokeWidth={1.5} />
                                                        </button>
                                                        ))}
                                                        <span className="ml-4 text-xs font-bold font-mono text-text bg-black/40 px-3 py-1.5 rounded">
                                                        {grade === 0 ? "Unrated" : grade === 1 ? "1 - Terrible" : grade === 5 ? "5 - Excellent" : `${grade} Stars`}
                                                        </span>
                                                    </div>
                                                    </div>

                                                    <div>
                                                    <label className="block text-[10px] font-bold font-mono text-text-muted mb-3 uppercase tracking-widest">Overseer Notes</label>
                                                    <textarea
                                                        value={notes}
                                                        onChange={(e) => setNotes(e.target.value)}
                                                        placeholder="Provide explicit feedback to guide future decisions..."
                                                        className="w-full h-28 bg-surface/50 border border-text/10 rounded-sm p-4 text-sm text-text focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/50 resize-none font-sans font-light tracking-wide transition-all"
                                                    />
                                                    </div>
                                                </div>
                                            </div>

                                            <button
                                                onClick={() => submitGrade(trade.id)}
                                                disabled={grade === 0 || submittingGrade}
                                                className="w-full mt-6 flex items-center justify-center gap-2 glass bg-warning/10 hover:bg-warning/20 text-warning border border-warning/30 px-6 py-3.5 rounded-sm font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed uppercase tracking-widest text-xs shadow-[0_0_15px_rgba(var(--warning),0.05)]"
                                            >
                                                {submittingGrade ? (
                                                <div className="w-4 h-4 border-2 border-warning/30 border-t-warning rounded-full animate-spin" />
                                                ) : (
                                                <Save size={16} />
                                                )}
                                                Save RLHF Feedback
                                            </button>
                                        </div>

                                        {/* Paper Trade Simulation Panel (if pending) */}
                                        {(trade.status === "PENDING_WEB3_SIGNATURE" || trade.status === "PENDING") && (
                                        <div className="md:col-span-2 mt-2 p-6 glass-panel bg-warning/5 border border-warning/20 rounded-sm flex flex-col md:flex-row items-center justify-between gap-6 shadow-[0_0_30px_rgba(var(--warning),0.05)] relative overflow-hidden">
                                            <div className="absolute top-0 right-0 w-32 h-32 bg-warning/10 blur-[40px]" />
                                            <div className="relative z-10">
                                                <h4 className="text-sm font-bold text-warning flex items-center gap-2 tracking-widest uppercase font-mono mb-2">
                                                    <Zap size={16} />
                                                    Paper Trade Logging Required
                                                </h4>
                                                <p className="text-xs text-text-muted font-light tracking-wide">
                                                    The CIO Agent has routed this trade. Action is required to log the simulated paper execution.
                                                </p>
                                                <div className="flex items-center gap-2 mt-4 text-[9px] text-success font-mono uppercase tracking-widest bg-success/10 border border-success/20 px-3 py-1.5 rounded w-fit">
                                                    <ShieldCheck size={12} />
                                                    Simulated Execution • Paper Trade
                                                </div>
                                            </div>
                                            <button
                                                onClick={() => handleWeb3Sign(trade)}
                                                disabled={signingTradeId === trade.id}
                                                className="relative z-10 flex-shrink-0 flex items-center justify-center gap-3 bg-warning hover:bg-warning/90 text-black font-black py-3 px-8 rounded-sm transition-all disabled:opacity-50 min-w-[240px] uppercase tracking-widest text-xs shadow-[0_0_20px_rgba(var(--warning),0.3)]"
                                            >
                                                {signingTradeId === trade.id ? (
                                                <div className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                                                ) : (
                                                <Wallet size={16} />
                                                )}
                                                {signingTradeId === trade.id ? "Logging Trade..." : "Log Paper Trade"}
                                            </button>
                                        </div>
                                        )}
                                        
                                    </div>
                                </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

