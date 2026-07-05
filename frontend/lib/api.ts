import axios from 'axios';

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface Asset {
  id: string;
  symbol: string;
  name: string;
  sector: string;
  market_cap_usd: number;
  current_price: number;
  price_change_24h_pct: number;
  predicted_direction: string;
  confidence: number;
  confidence_interval?: [number, number];
  rsi_14?: number;
  macd?: number;
  volatility_regime?: string;
  volume_24h?: number;
}

export interface Prediction {
  asset_symbol: string;
  direction: string;
  confidence: number;
  confidence_interval?: [number, number];
  volatility_regime: string;
  predicted_at: string;
  model_version: string;
}

export interface GraphNode {
  id: string;
  symbol: string;
  sector: string;
  market_cap_usd: number;
  predicted_direction: string;
  confidence: number;
  confidence_interval?: [number, number];
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  edge_type: string;
  motif_similarity?: number;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface RiskAlert {
  severity: string;
  type: string;
  message: string;
  affected_assets: string[];
  recommendation: string;
}

export interface RiskData {
  market_regime: string;
  average_volatility: number;
  correlation_clusters: Record<string, string[]>;
  top_volatile: Array<{
    symbol: string;
    name: string;
    volatility_7d: number;
    returns_1d: number;
    current_price: number;
  }>;
  risk_alerts: RiskAlert[];
  up_pct: number;
  down_pct: number;
  neutral_pct: number;
  total_assets_monitored: number;
}

export interface ExplainResponse {
  symbol: string;
  explanation: string;
  direction: string;
  confidence: number;
  top_features: Record<string, number>;
  news_sources?: string[];
  bull_case?: string;
  bear_case?: string;
  risk_case?: string;
}

export interface TradeRecord {
  id: number;
  timestamp: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  total_usd: number;
  reason?: string;
  confidence?: number;
  status: string;
  pnl: number;
  overseer_grade?: number;
  overseer_notes?: string;
  debate?: {
    macro_analysis: string | null;
    onchain_analysis: string | null;
    sentiment_analysis: string | null;
    bull_case?: string | null;
    bear_case?: string | null;
    risk_case?: string | null;
    cio_reasoning: string | null;
  } | null;
}

export interface PortfolioResponse {
  cash_balance: number;
  holdings_value: number;
  total_value: number;
  initial_capital: number;
  roi_pct: number;
  btc_benchmark_value: number;
  btc_roi_pct: number;
  win_rate: number;
  total_trades: number;
  max_drawdown_pct: number;
  holdings: Record<string, any>;
  equity_curve: Array<{ timestamp: string; portfolio: number; btc_benchmark: number }>;
}

export interface PortfolioTradesResponse {
  trades: TradeRecord[];
  total: number;
}

// SWR Fetcher
export const fetcher = (url: string) => api.get(url).then(res => res.data);

// API Service for specific calls outside of SWR (if needed)
export const apiService = {
  getAssets: () => api.get<Asset[]>('/api/assets').then(res => res.data),
  getGraphLatest: () => api.get<GraphResponse>('/api/graph/latest').then(res => res.data),
  getRisk: () => api.get<RiskData>('/api/risk').then(res => res.data),
  getExplain: (symbol: string) => api.get<ExplainResponse>(`/api/explain/${symbol}`).then(res => res.data),
  getSettings: () => api.get<{values: Record<string, string>, configured: Record<string, boolean>}>('/api/settings').then(res => res.data),
  updateSettings: (settings: Record<string, string>) => api.post<{status: string, message: string}>('/api/settings', { settings }).then(res => res.data),
  getPortfolio: () => api.get<PortfolioResponse>('/api/portfolio').then(res => res.data),
  getPortfolioTrades: (limit = 100, offset = 0) => api.get<PortfolioTradesResponse>(`/api/portfolio/trades?limit=${limit}&offset=${offset}`).then(res => res.data),
  triggerExecution: () => api.post('/api/portfolio/execute').then(res => res.data),
  resetPortfolio: () => api.post('/api/portfolio/reset').then(res => res.data),
  gradeTrade: (tradeId: number, grade: number, notes: string) => api.post(`/api/portfolio/trades/${tradeId}/grade`, { grade, notes }).then(res => res.data),
  confirmWeb3Trade: (tradeId: number, txHash: string) => api.post(`/api/portfolio/trades/${tradeId}/confirm`, { tx_hash: txHash }).then(res => res.data),
  triggerRefreshAll: () => api.post('/api/status/refresh-all').then(res => res.data),
  triggerSchedulerRun: () => api.post('/api/scheduler/run').then(res => res.data),
  getLatestSynthesis: () => api.get('/api/sentiment-data/latest-synthesis').then(res => res.data),
};
