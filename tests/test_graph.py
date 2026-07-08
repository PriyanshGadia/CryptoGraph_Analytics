import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from ml.graph.graph_builder import DynamicGraphBuilder

def test_graph_builder():
    symbols = ["BTC", "ETH", "SOL"]
    builder = DynamicGraphBuilder(supabase_client=None, asset_symbols=symbols, feature_dim=24)
    
    # Prepare dummy feature dataframes for the last 40 days
    now = datetime.now(timezone.utc)
    dates = [now - timedelta(days=i) for i in range(40)]
    dates.reverse()
    
    dummy_features = {}
    cols = [
        "open", "high", "low", "close", "volume", 
        "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
        "returns_1d", "returns_7d", "volatility_7d", 
        "sentiment_score", "fear_greed_norm", "community_score", "public_interest", 
        "sentiment_rolling_3d", "sentiment_momentum", "market_cap_usd",
        "fed_rate", "cpi", "inflation", "vix"
    ]
    
    for idx, sym in enumerate(symbols):
        data = []
        for d in dates:
            row = {
                "timestamp": d,
                "open": 1000.0 * (idx + 1),
                "high": 1050.0 * (idx + 1),
                "low": 980.0 * (idx + 1),
                "close": 1020.0 * (idx + 1) + np.random.randn() * 10,
                "volume": 50000.0,
                "market_cap_usd": 1000000000.0 * (idx + 1)
            }
            # fill indicators with default values
            for c in cols:
                if c not in row:
                    row[c] = 0.5
            data.append(row)
            
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        # Compute returns_1d and volatility_7d
        df["returns_1d"] = df["close"].pct_change().fillna(0.0)
        df["volatility_7d"] = df["returns_1d"].rolling(7).std().fillna(0.02)
        dummy_features[sym] = df
        
    # Build graph for today
    graph = builder.build_graph(now, dummy_features)
    
    assert graph.x.shape == (3, 24), f"Expected x shape (3, 24), got {graph.x.shape}"
    assert graph.edge_index.shape[0] == 2, "edge_index should be of shape (2, E)"
    assert graph.edge_attr.shape[1] == 1, "edge_attr should be of shape (E, 1)"
    print("Graph builder unit test passed successfully!")
