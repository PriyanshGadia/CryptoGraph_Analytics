"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher, apiService, PortfolioResponse, PortfolioTradesResponse, TradeRecord } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
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
  ShieldCheck
} from "lucide-react";

export default function PortfolioPage() {
  const { data: portfolio, error: pErr, mutate: mutatePortfolio } = useSWR<PortfolioResponse>("/api/portfolio", fetcher, {
    refreshInterval: 60000,
  });
  
  const { data: tradesData, error: tErr, mutate: mutateTrades } = useSWR<PortfolioTradesResponse>("/api/portfolio/trades?limit=50", fetcher, {
    refreshInterval: 60000,
  });

  const [executing, setExecuting] = useState(false);
  const [expandedTradeId, setExpandedTradeId] = useState<number | null>(null);
  
  // Grading form state
  const [grade, setGrade] = useState<number>(0);
  const [notes, setNotes] = useState<string>("");
  const [submittingGrade, setSubmittingGrade] = useState(false);
  const [signingTradeId, setSigningTradeId] = useState<number | null>(null);

  const handleManualExecute = async () => {
    if (executing) return;
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
      // Phase 7: EIP-712 Typed Data Simulation
      console.log("Requesting EIP-712 Signature for:", {
        domain: { name: 'ST-GCN Autonomous Swarm', version: '1', chainId: 1 },
        types: {
          Trade: [
            { name: 'asset', type: 'string' },
            { name: 'side', type: 'string' },
            { name: 'amount', type: 'uint256' },
            { name: 'action', type: 'string' },
          ]
        },
        message: {
          asset: trade.symbol,
          side: trade.side,
          amount: trade.total_usd,
          action: "MEV-Shielded Execution via Flashbots RPC"
        }
      });
      
      // Mock Web3 Execution Delay (e.g. MetaMask popup & confirmation)
      await new Promise(resolve => setTimeout(resolve, 2500));
      // Mock TX hash
      const mockTxHash = "0x" + Array.from({length: 40}, () => Math.floor(Math.random() * 16).toString(16)).join('');
      
      await apiService.confirmWeb3Trade(trade.id, mockTxHash);
      await mutateTrades();
      await mutatePortfolio();
    } catch (e) {
      console.error("Failed to sign Web3 transaction", e);
    } finally {
      setSigningTradeId(null);
    }
  };

  if (pErr || tErr) {
    return (
      <div className="p-8 text-danger flex items-center justify-center">
        <Activity className="mr-2" /> Failed to load portfolio data.
      </div>
    );
  }

  if (!portfolio) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold text-text">Autonomous Portfolio</h1>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      </div>
    );
  }

  const trades = tradesData?.trades || [];

  return (
    <div className="space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-text">Autonomous Portfolio</h1>
          <p className="text-textMuted mt-1">Paper-trading performance driven by ST-GCN agent signals.</p>
        </div>
        <button
          onClick={handleManualExecute}
          disabled={executing}
          className="flex items-center justify-center gap-2 bg-accent hover:bg-accent/90 text-white px-6 py-2 rounded-lg font-semibold transition-colors disabled:opacity-50"
        >
          {executing ? (
            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <Play size={18} fill="currentColor" />
          )}
          {executing ? "Executing..." : "Force Execution"}
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card className="border-accent/30 shadow-[0_0_15px_rgba(99,102,241,0.1)]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-textMuted flex items-center gap-2">
              <Wallet size={16} /> Total Value
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-text">
              ${portfolio.total_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <div className="text-sm mt-1 text-textMuted">
              Cash: ${portfolio.cash_balance.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-textMuted flex items-center gap-2">
              <Activity size={16} /> Return on Investment (ROI)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-3xl font-bold flex items-center gap-2 ${portfolio.roi_pct >= 0 ? 'text-success' : 'text-danger'}`}>
              {portfolio.roi_pct >= 0 ? <TrendingUp size={24} /> : <TrendingDown size={24} />}
              {portfolio.roi_pct > 0 ? "+" : ""}{portfolio.roi_pct.toFixed(2)}%
            </div>
            <div className="text-sm mt-1 text-textMuted flex items-center justify-between">
              <span>vs BTC Benchmark:</span>
              <span className={portfolio.roi_pct >= portfolio.btc_roi_pct ? 'text-success' : 'text-danger'}>
                {portfolio.btc_roi_pct > 0 ? "+" : ""}{portfolio.btc_roi_pct.toFixed(2)}%
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-textMuted flex items-center gap-2">
              <Target size={16} /> Win Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-text">
              {portfolio.win_rate.toFixed(1)}%
            </div>
            <div className="text-sm mt-1 text-textMuted">
              {portfolio.total_trades} total trades executed
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-textMuted flex items-center gap-2">
              <TrendingDown size={16} /> Max Drawdown
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-danger">
              -{portfolio.max_drawdown_pct.toFixed(2)}%
            </div>
            <div className="text-sm mt-1 text-textMuted">
              Since inception
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Holdings */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PieChart size={20} className="text-accent" />
              Current Holdings
            </CardTitle>
            <p className="text-sm text-textMuted mt-1.5">Active positions across all assets</p>
          </CardHeader>
          <CardContent>
            {Object.keys(portfolio.holdings).length === 0 ? (
              <div className="text-center py-8 text-textMuted bg-surface/50 rounded-lg border border-border/50">
                <Wallet className="mx-auto mb-2 opacity-50" size={32} />
                No active holdings. 100% in cash.
              </div>
            ) : (
              <div className="space-y-4">
                {Object.entries(portfolio.holdings).map(([symbol, data]: [string, any]) => {
                  // Rough avg price calculation
                  const avgPrice = data.total_invested / data.qty;
                  return (
                    <div key={symbol} className="flex items-center justify-between p-3 bg-surface rounded-lg border border-border">
                      <div>
                        <div className="font-bold text-text">{symbol}</div>
                        <div className="text-xs text-textMuted">{data.qty.toFixed(4)} tokens</div>
                      </div>
                      <div className="text-right">
                        <div className="font-medium text-text">${data.total_invested.toLocaleString(undefined, {maximumFractionDigits: 2})}</div>
                        <div className="text-xs text-textMuted">Avg: ${avgPrice.toLocaleString(undefined, {maximumFractionDigits: 2})}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Trades */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ArrowRightLeft size={20} className="text-accent" />
              Recent Trade Execution
            </CardTitle>
            <p className="text-sm text-textMuted mt-1.5">Latest automated paper trades</p>
          </CardHeader>
          <CardContent>
            {trades.length === 0 ? (
              <div className="text-center py-12 text-textMuted bg-surface/50 rounded-lg border border-border/50">
                No trades have been executed yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="text-xs text-textMuted uppercase bg-surface/80 border-b border-border">
                    <tr>
                      <th className="px-4 py-3 font-medium">Date</th>
                      <th className="px-4 py-3 font-medium">Asset</th>
                      <th className="px-4 py-3 font-medium">Type</th>
                      <th className="px-4 py-3 font-medium">Amount</th>
                      <th className="px-4 py-3 font-medium">Price</th>
                      <th className="px-4 py-3 font-medium text-right">Total / PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((trade: TradeRecord) => (
                      <React.Fragment key={trade.id}>
                        <tr 
                          onClick={() => handleExpand(trade)}
                          className="border-b border-border last:border-0 hover:bg-surface/50 transition-colors cursor-pointer group"
                        >
                          <td className="px-4 py-3 whitespace-nowrap text-textMuted flex items-center gap-2">
                            {expandedTradeId === trade.id ? <ChevronUp size={14} /> : <ChevronDown size={14} className="opacity-50 group-hover:opacity-100" />}
                            {new Date(trade.timestamp).toLocaleDateString()} {new Date(trade.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                          </td>
                          <td className="px-4 py-3 font-bold text-text">{trade.symbol}</td>
                          <td className="px-4 py-3">
                            <Badge variant={trade.side === 'buy' ? 'success' : 'destructive'} className="uppercase text-[10px] tracking-wider font-bold">
                              {trade.side}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-text">{trade.quantity.toLocaleString(undefined, {maximumFractionDigits: 4})}</td>
                          <td className="px-4 py-3 text-text">${trade.price.toLocaleString(undefined, {maximumFractionDigits: 2})}</td>
                          <td className="px-4 py-3 text-right">
                            <div className="font-medium text-text flex items-center justify-end gap-2">
                              {trade.status === "PENDING_WEB3_SIGNATURE" ? (
                                <Badge variant="warning" className="uppercase text-[9px] tracking-wider font-bold animate-pulse">
                                  Action Required
                                </Badge>
                              ) : trade.overseer_grade ? (
                                <div className="flex text-yellow-400" title={`Graded ${trade.overseer_grade} Stars`}>
                                  {[...Array(trade.overseer_grade)].map((_, i) => <Star key={i} size={12} fill="currentColor" />)}
                                </div>
                              ) : null}
                              ${trade.total_usd.toLocaleString(undefined, {maximumFractionDigits: 2})}
                            </div>
                            {trade.side === 'sell' && trade.pnl !== undefined && trade.status === "EXECUTED" && (
                              <div className={`text-xs ${trade.pnl > 0 ? 'text-success' : 'text-danger'}`}>
                                {trade.pnl > 0 ? '+' : ''}${trade.pnl.toLocaleString(undefined, {maximumFractionDigits: 2})} PnL
                              </div>
                            )}
                          </td>
                        </tr>
                        
                        {expandedTradeId === trade.id && (
                          <tr className="bg-surface/30 border-b border-border">
                            <td colSpan={6} className="p-4">
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-surface p-4 rounded-lg border border-border">
                                
                                {/* Debate Transcript */}
                                <div>
                                  <h4 className="text-sm font-bold text-text mb-3 flex items-center gap-2">
                                    <MessageSquare size={16} className="text-accent" />
                                    Multi-Agent Debate Transcript
                                  </h4>
                                  {trade.debate ? (
                                    <div className="space-y-4 text-sm">
                                      <div>
                                        <span className="font-semibold text-textMuted block mb-1">Macro Economist:</span>
                                        <p className="text-text bg-background p-2 rounded border border-border/50">{trade.debate.macro_analysis}</p>
                                      </div>
                                      <div>
                                        <span className="font-semibold text-textMuted block mb-1">On-Chain Detective:</span>
                                        <p className="text-text bg-background p-2 rounded border border-border/50">{trade.debate.onchain_analysis}</p>
                                      </div>
                                      <div>
                                        <span className="font-semibold text-textMuted block mb-1">Sentiment Analyst:</span>
                                        <p className="text-text bg-background p-2 rounded border border-border/50">{trade.debate.sentiment_analysis}</p>
                                      </div>
                                      <div>
                                        <span className="font-semibold text-accent block mb-1">CIO Verdict:</span>
                                        <p className="text-text bg-accent/10 p-3 rounded border border-accent/20 whitespace-pre-wrap">{trade.debate.cio_reasoning}</p>
                                      </div>
                                    </div>
                                  ) : (
                                    <div className="text-textMuted text-sm italic py-4">No debate transcript available for this legacy trade.</div>
                                  )}
                                </div>

                                {/* Overseer Grading */}
                                <div className="border-l border-border pl-6">
                                  <h4 className="text-sm font-bold text-text mb-3 flex items-center gap-2">
                                    <Target size={16} className="text-yellow-400" />
                                    Overseer Grading (RLHF)
                                  </h4>
                                  <p className="text-xs text-textMuted mb-4">
                                    Grade the CIO's logic. 1-star and 5-star trades will be injected into future prompts as Few-Shot learning examples.
                                  </p>
                                  
                                  <div className="space-y-4">
                                    <div>
                                      <label className="block text-xs font-semibold text-textMuted mb-2">Assign Grade</label>
                                      <div className="flex items-center gap-2">
                                        {[1, 2, 3, 4, 5].map((star) => (
                                          <button
                                            key={star}
                                            onClick={() => setGrade(star)}
                                            className={`transition-colors ${grade >= star ? "text-yellow-400" : "text-border hover:text-yellow-400/50"}`}
                                          >
                                            <Star size={24} fill={grade >= star ? "currentColor" : "none"} strokeWidth={1.5} />
                                          </button>
                                        ))}
                                        <span className="ml-2 text-xs font-bold text-text">
                                          {grade === 0 ? "Unrated" : grade === 1 ? "1 - Terrible" : grade === 5 ? "5 - Excellent" : `${grade} Stars`}
                                        </span>
                                      </div>
                                    </div>

                                    <div>
                                      <label className="block text-xs font-semibold text-textMuted mb-2">Overseer Notes</label>
                                      <textarea
                                        value={notes}
                                        onChange={(e) => setNotes(e.target.value)}
                                        placeholder="What did the CIO do well or poorly? Provide explicit feedback to guide future decisions..."
                                        className="w-full h-24 bg-background border border-border rounded p-3 text-sm text-text focus:outline-none focus:border-accent resize-none"
                                      />
                                    </div>

                                    <button
                                      onClick={() => submitGrade(trade.id)}
                                      disabled={grade === 0 || submittingGrade}
                                      className="w-full flex items-center justify-center gap-2 bg-accent/20 hover:bg-accent text-accent hover:text-white border border-accent/50 px-4 py-2 rounded font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                      {submittingGrade ? (
                                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                      ) : (
                                        <Save size={16} />
                                      )}
                                      Save RLHF Feedback
                                    </button>
                                  </div>
                                </div>

                                {/* Web3 Signer Panel (if pending) */}
                                {trade.status === "PENDING_WEB3_SIGNATURE" && (
                                  <div className="md:col-span-2 mt-4 p-4 bg-accent/10 border border-accent/30 rounded-lg flex flex-col md:flex-row items-center justify-between gap-4">
                                    <div>
                                      <h4 className="text-sm font-bold text-text flex items-center gap-2">
                                        <Zap size={16} className="text-accent" />
                                        Web3 DEX Execution Required
                                      </h4>
                                      <p className="text-xs text-textMuted mt-1">
                                        The CIO Agent has routed this trade to a decentralized exchange to prevent slippage.
                                      </p>
                                      <div className="flex items-center gap-1 mt-2 text-[10px] text-success bg-success/10 border border-success/20 px-2 py-1 rounded w-fit">
                                        <ShieldCheck size={12} />
                                        <span>EIP-712 Structured Signing (Phishing Protection Active) • Flashbots RPC Shielded</span>
                                      </div>
                                    </div>
                                    <button
                                      onClick={() => handleWeb3Sign(trade)}
                                      disabled={signingTradeId === trade.id}
                                      className="flex-shrink-0 flex items-center justify-center gap-2 bg-accent hover:bg-accent/90 text-white font-bold py-2 px-6 rounded-lg transition-colors disabled:opacity-50 min-w-[200px]"
                                    >
                                      {signingTradeId === trade.id ? (
                                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                      ) : (
                                        <Wallet size={16} />
                                      )}
                                      {signingTradeId === trade.id ? "Awaiting Signature..." : "Sign via Web3 Wallet"}
                                    </button>
                                  </div>
                                )}
                                
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
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
