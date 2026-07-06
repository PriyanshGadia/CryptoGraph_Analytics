"""
CryptoGraph API Routes
Exported FastAPI routers.
"""

from .assets import router as assets_router
from .predictions import router as predictions_router
from .graph import router as graph_router
from .risk import router as risk_router
from .explain import router as explain_router
from .forecast import router as forecast_router
from .status import router as status_router
from .coins import router as coins_router
from .performance import router as performance_router
from .correlations import router as correlations_router
from .sentiment_data import router as sentiment_router
from .screener import router as screener_router
from .settings import router as settings_router
from .portfolio import router as portfolio_router
from .stream import router as stream_router

__all__ = [
    "assets_router",
    "predictions_router",
    "graph_router",
    "risk_router",
    "explain_router",
    "forecast_router",
    "status_router",
    "coins_router",
    "performance_router",
    "correlations_router",
    "sentiment_router",
    "screener_router",
    "settings_router",
    "portfolio_router",
    "stream_router"
]
