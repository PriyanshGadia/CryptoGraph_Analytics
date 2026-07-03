from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class Asset(BaseModel):
    id: str
    symbol: str
    name: str
    sector: str
    market_cap_usd: Optional[float] = None
    current_price: Optional[float] = None
    price_change_24h_pct: Optional[float] = None
    predicted_direction: Optional[str] = None
    confidence: Optional[float] = None
    confidence_interval: Optional[List[float]] = None

class Prediction(BaseModel):
    asset_symbol: str
    direction: str
    confidence: float
    confidence_interval: Optional[List[float]] = None
    volatility_regime: str
    predicted_at: str
    model_version: str
    shap_values: Optional[dict] = None
    is_fallback: bool = False

class PredictionHistory(BaseModel):
    symbol: str
    predictions: List[Prediction]

class GraphNode(BaseModel):
    id: str
    symbol: str
    sector: str
    market_cap_usd: Optional[float] = None
    predicted_direction: Optional[str] = None
    confidence: Optional[float] = None
    confidence_interval: Optional[List[float]] = None

class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float
    edge_type: str
    motif_similarity: Optional[float] = None

class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    betti_0: Optional[int] = None
    average_clustering: Optional[float] = None
    euler_characteristic: Optional[int] = None

class RiskData(BaseModel):
    market_regime: str
    average_volatility: float
    correlation_clusters: Dict[str, List[str]]
    top_movers: List[Dict[str, Any]]
    risk_alerts: List[str]

class ExplainResponse(BaseModel):
    symbol: str
    explanation: str
    direction: str
    confidence: float
    top_features: Dict[str, float]
    news_sources: List[str] = []
    bull_case: Optional[str] = None
    bear_case: Optional[str] = None
    risk_case: Optional[str] = None
    is_fallback: bool = False

class TradeRecord(BaseModel):
    id: int
    timestamp: str
    symbol: str
    side: str
    quantity: float
    price: float
    total_usd: float
    reason: Optional[str] = None
    confidence: Optional[float] = None
    pnl: float = 0.0

class PortfolioResponse(BaseModel):
    cash_balance: float
    holdings_value: float
    total_value: float
    initial_capital: float = 100000.0
    roi_pct: float
    btc_benchmark_value: float
    btc_roi_pct: float
    win_rate: float
    total_trades: int
    max_drawdown_pct: float
    holdings: Dict[str, Any]
    equity_curve: List[Dict[str, Any]]

class PortfolioTradesResponse(BaseModel):
    trades: List[TradeRecord]
    total: int
