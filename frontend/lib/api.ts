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
}

export interface Prediction {
  asset_symbol: string;
  direction: string;
  confidence: number;
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
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  edge_type: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface RiskData {
  market_regime: string;
  average_volatility: number;
  correlation_clusters: Record<string, string[]>;
  top_movers: any[];
  risk_alerts: string[];
  up_pct: number;
  down_pct: number;
}

export interface ExplainResponse {
  symbol: string;
  explanation: string;
  direction: string;
}

// SWR Fetcher
export const fetcher = (url: string) => api.get(url).then(res => res.data);

// API Service for specific calls outside of SWR (if needed)
export const apiService = {
  getAssets: () => api.get<Asset[]>('/api/assets').then(res => res.data),
  getGraphLatest: () => api.get<GraphResponse>('/api/graph/latest').then(res => res.data),
  getRisk: () => api.get<RiskData>('/api/risk').then(res => res.data),
  getExplain: (symbol: string) => api.get<ExplainResponse>(`/api/explain/${symbol}`).then(res => res.data),
};
