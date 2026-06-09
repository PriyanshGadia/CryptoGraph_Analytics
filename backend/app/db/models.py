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

class Prediction(BaseModel):
    asset_symbol: str
    direction: str
    confidence: float
    volatility_regime: str
    predicted_at: str
    model_version: str

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

class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float
    edge_type: str

class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]

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
