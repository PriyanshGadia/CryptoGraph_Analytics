"""Graph routes — local SQLAlchemy backend."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc, text
from app.api.deps import get_db
from app.db.models import GraphResponse, GraphNode, GraphEdge
from app.db.models_sqla import Asset, Prediction, OHLCV
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd

router = APIRouter(prefix="/graph", tags=["graph"])


def _compute_correlation_graph(db: Session, top_n_edges: int = 100):
    """
    Builds a correlation-based graph from the local OHLCV + technical_features tables.
    Nodes = assets, Edges = top Pearson correlations between daily returns.
    """
    since = datetime.now(timezone.utc) - timedelta(days=30)

    # Batched query: get all daily returns from technical_features
    tech_query = text("""
        SELECT asset_id, timestamp, returns_1d
        FROM technical_features
        WHERE timestamp >= :since
        ORDER BY timestamp ASC
    """)
    rows = db.execute(tech_query, {"since": since.isoformat()}).fetchall()

    if not rows:
        return [], []

    # Build a pivot table: date x asset_id -> returns_1d
    df = pd.DataFrame(rows, columns=["asset_id", "timestamp", "returns_1d"])
    df["date"] = df["timestamp"].apply(lambda x: str(x).split("T")[0] if isinstance(x, str) else str(x)[:10])
    pivot = df.pivot_table(index="date", columns="asset_id", values="returns_1d")
    pivot = pivot.dropna(axis=1, thresh=max(1, len(pivot) // 2))

    if pivot.shape[1] < 2:
        return [], []

    corr_matrix = pivot.corr(method="pearson").fillna(0.0)

    # Load asset metadata
    assets = db.query(Asset).all()
    asset_map = {a.id: a for a in assets}

    # Get latest predictions
    preds = db.query(Prediction).order_by(desc(Prediction.predicted_at)).limit(200).all()
    pred_map = {}
    for p in preds:
        if p.asset_id not in pred_map:
            pred_map[p.asset_id] = p

    # Build nodes
    nodes_dict = {}
    for aid, asset in asset_map.items():
        pred = pred_map.get(aid)
        nodes_dict[asset.symbol] = GraphNode(
            id=str(aid),
            symbol=asset.symbol,
            sector=asset.sector or "other",
            market_cap_usd=asset.market_cap_usd,
            predicted_direction=pred.direction if pred else "neutral",
            confidence=pred.confidence if pred else 0.0,
        )

    # Build edges from upper triangle of correlation matrix
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
    pairs = []
    for i, aid_a in enumerate(corr_matrix.columns):
        for j, aid_b in enumerate(corr_matrix.columns):
            if mask[i][j]:
                val = corr_matrix.iloc[i, j]
                if not np.isnan(val) and abs(val) > 0.1:
                    pairs.append((aid_a, aid_b, float(val)))

    # Sort by absolute correlation descending, take top_n_edges
    pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    pairs = pairs[:top_n_edges]

    # Load latest technical features for Motif Mining (Structural Similarity)
    latest_tech_query = text("""
        SELECT asset_id, returns_1d, volatility_7d, rsi_14, macd, macd_signal
        FROM technical_features
        WHERE (asset_id, timestamp) IN (
            SELECT asset_id, MAX(timestamp)
            FROM technical_features
            GROUP BY asset_id
        )
    """)
    latest_tech_rows = db.execute(latest_tech_query).fetchall()
    
    tech_vectors = {}
    for r in latest_tech_rows:
        aid = r[0]
        ret = (r[1] or 0.0) * 10
        vol = (r[2] or 0.0) * 10
        rsi = ((r[3] or 50.0) - 50) / 50
        macd = r[4] or 0.0
        sig = r[5] or 0.0
        vec = np.array([ret, vol, rsi, macd, sig])
        norm = np.linalg.norm(vec)
        tech_vectors[aid] = vec / norm if norm > 0 else np.zeros(5)

    edges = []
    for aid_a, aid_b, weight in pairs:
        a = asset_map.get(aid_a)
        b = asset_map.get(aid_b)
        if a and b:
            edge_type = "positive_correlation" if weight > 0 else "negative_correlation"
            
            # Motif Similarity
            vec_a = tech_vectors.get(aid_a, np.zeros(5))
            vec_b = tech_vectors.get(aid_b, np.zeros(5))
            motif_sim = float(np.dot(vec_a, vec_b))
            
            edges.append(GraphEdge(
                source=a.symbol,
                target=b.symbol,
                weight=round(abs(weight), 4),
                edge_type=edge_type,
                motif_similarity=round(max(-1.0, min(1.0, motif_sim)), 4)
            ))

    return list(nodes_dict.values()), edges


@router.get("/latest", response_model=GraphResponse)
async def get_latest_graph(db: Session = Depends(get_db)):
    """
    Returns current graph for visualization.
    Computes correlation-based graph from local OHLCV/technical_features.
    """
    nodes, edges = _compute_correlation_graph(db)
    return GraphResponse(nodes=nodes, edges=edges)


@router.get("/history")
async def get_graph_history(days: int = 7, db: Session = Depends(get_db)):
    """
    Returns graph evolution metrics over N days.
    Computes edge density from rolling correlation windows.
    """
    # Build one snapshot for now (multi-day requires heavy compute)
    nodes, edges = _compute_correlation_graph(db)

    history = []
    total_assets = len(nodes)
    max_possible = total_assets * (total_assets - 1) / 2 if total_assets > 1 else 1

    # Group significant edges by strength
    strong_edges = [e for e in edges if e.weight > 0.5]
    central_nodes = {}
    for e in edges:
        central_nodes[e.source] = central_nodes.get(e.source, 0) + 1
        central_nodes[e.target] = central_nodes.get(e.target, 0) + 1

    top_central = sorted(central_nodes.items(), key=lambda x: x[1], reverse=True)[:5]

    history.append({
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "edge_count": len(edges),
        "density": min(len(edges) / max_possible, 1.0) if max_possible > 0 else 0,
        "strong_edge_count": len(strong_edges),
        "top_central_nodes": [n[0] for n in top_central],
    })

    return history
