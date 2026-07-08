"""Graph routes — local SQLAlchemy backend."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc, text, func
from app.api.deps import get_db
from app.db.schemas import GraphResponse, GraphNode, GraphEdge
from app.db.models import Asset, Prediction, OHLCV, Forecast as SQLAForecast
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd

router = APIRouter(prefix="/graph", tags=["graph"])


from app.core.cache import cached

@cached(ttl_seconds=3600)
def _compute_correlation_graph(db: Session, top_n_edges: int = 100, mode: str = "live"):
    """
    Builds a correlation-based graph from local OHLCV, technical_features, or forecasts tables.
    Nodes = assets, Edges = top Pearson correlations between daily returns.
    Supports mode="live" (last 30 days), mode="historical" (last 90 days),
    mode="historical_30" (last 30 days historical), mode="projected" (30 day forecast),
    mode="projected_15" (15 day forecast).
    
    WARNING: The double-for-loop correlation extraction is O(N^2).
    This function is strictly limited to 200 assets (approx 20,000 iterations). 
    Do NOT increase the SQL LIMIT 200 without refactoring the numpy masking logic.
    """
    # 1. Fetch live 30-day returns to construct the canonical graph topology (so all modes share the exact same edges)
    since_live = datetime.now(timezone.utc) - timedelta(days=30)
    # Limit to top 200 assets by market cap to prevent O(N^2) memory exhaustion
    top_assets_query = text("SELECT id FROM assets ORDER BY market_cap_usd DESC LIMIT 200")
    top_asset_ids = [str(r[0]) for r in db.execute(top_assets_query).fetchall()]
    if not top_asset_ids:
        return [], []

    params = {"since": since_live.isoformat()}
    for i, aid in enumerate(top_asset_ids):
        params[f"aid_{i}"] = aid

    tech_query = text(f"""
        SELECT asset_id, timestamp, returns_1d
        FROM technical_features
        WHERE timestamp >= :since AND asset_id IN ({','.join([f':aid_{i}' for i in range(len(top_asset_ids))])})
        ORDER BY timestamp ASC
    """)
    rows_live = db.execute(tech_query, params).fetchall()

    if not rows_live:
        return [], []

    df_live = pd.DataFrame(rows_live, columns=["asset_id", "timestamp", "returns_1d"])
    df_live["date"] = df_live["timestamp"].apply(lambda x: str(x).split("T")[0] if isinstance(x, str) else str(x)[:10])
    pivot_live = df_live.pivot_table(index="date", columns="asset_id", values="returns_1d")
    pivot_live = pivot_live.dropna(axis=1, thresh=max(1, len(pivot_live) // 2))

    if pivot_live.shape[1] < 2:
        return [], []

    live_corr = pivot_live.corr(method="pearson").fillna(0.0)

    # Build upper triangle of live correlations efficiently (vectorized)
    mask = np.triu(np.ones_like(live_corr, dtype=bool), k=1)
    corr_vals = live_corr.values
    indices = np.where(mask)
    cols = list(live_corr.columns)
    
    all_pairs = []
    for i, j in zip(indices[0], indices[1]):
        val = float(corr_vals[i, j])
        if not np.isnan(val):
            all_pairs.append((cols[i], cols[j], val))

    # Ensure all nodes are connected (degree >= 1)
    connected_pairs = []
    seen_keys = set()
    asset_strongest = {}
    for aid_a, aid_b, val in all_pairs:
        if aid_a not in asset_strongest or abs(val) > abs(asset_strongest[aid_a][2]):
            asset_strongest[aid_a] = (aid_a, aid_b, val)
        if aid_b not in asset_strongest or abs(val) > abs(asset_strongest[aid_b][2]):
            asset_strongest[aid_b] = (aid_a, aid_b, val)

    for aid, edge in asset_strongest.items():
        key = tuple(sorted([edge[0], edge[1]]))
        if key not in seen_keys:
            seen_keys.add(key)
            connected_pairs.append((edge[0], edge[1]))

    # Fill remaining edge slots up to top_n_edges with top positive and negative correlations
    remaining_pairs = [p for p in all_pairs if tuple(sorted([p[0], p[1]])) not in seen_keys]
    pos_rem = [p for p in remaining_pairs if p[2] >= 0]
    neg_rem = [p for p in remaining_pairs if p[2] < 0]
    pos_rem.sort(key=lambda x: x[2], reverse=True)
    neg_rem.sort(key=lambda x: x[2])  # Most negative first

    slots_left = max(0, top_n_edges - len(connected_pairs))
    n_pos = int(slots_left * 0.75)
    n_neg = slots_left - n_pos

    canonical_edge_pairs = list(connected_pairs)
    for p in pos_rem[:n_pos]:
        canonical_edge_pairs.append((p[0], p[1]))
    for p in neg_rem[:n_neg]:
        canonical_edge_pairs.append((p[0], p[1]))
    if len(canonical_edge_pairs) < top_n_edges:
        for p in pos_rem[n_pos : n_pos + (top_n_edges - len(canonical_edge_pairs))]:
            canonical_edge_pairs.append((p[0], p[1]))

    # 2. Compute mode-specific correlation matrix
    target_corr = live_corr.copy()

    if mode in ["historical", "historical_30"]:
        days_lookback = 90 if mode == "historical" else 30
        since = datetime.now(timezone.utc) - timedelta(days=days_lookback)
        hist_params = params.copy()
        hist_params["since"] = since.isoformat()
        rows_hist = db.execute(tech_query, hist_params).fetchall()
        if rows_hist:
            df_h = pd.DataFrame(rows_hist, columns=["asset_id", "timestamp", "returns_1d"])
            df_h["date"] = df_h["timestamp"].apply(lambda x: str(x).split("T")[0] if isinstance(x, str) else str(x)[:10])
            p_h = df_h.pivot_table(index="date", columns="asset_id", values="returns_1d")
            p_h = p_h.dropna(axis=1, thresh=max(1, len(p_h) // 2))
            if p_h.shape[1] >= 2:
                target_corr = p_h.corr(method="pearson").fillna(0.0)

    elif mode.startswith("projected"):
        import json
        forecast_rows = db.query(SQLAForecast).all()
        if forecast_rows:
            proj_data = {}
            for f in forecast_rows:
                prices = f.forecast_prices
                if isinstance(prices, str):
                    try:
                        prices = json.loads(prices)
                    except Exception:
                        continue
                if isinstance(prices, list) and len(prices) > 1:
                    limit = 15 if mode == "projected_15" else 30
                    proj_data[f.asset_id] = prices[:limit]

            if len(proj_data) >= 2:
                df_proj = pd.DataFrame(proj_data)
                df_returns = df_proj.pct_change().dropna()
                if len(df_returns) >= 2:
                    p_proj_corr = df_returns.corr(method="pearson")
                    for col in target_corr.columns:
                        for row_idx in target_corr.index:
                            if col in p_proj_corr.columns and row_idx in p_proj_corr.index:
                                val = p_proj_corr.loc[row_idx, col]
                                if not np.isnan(val) and val != 0.0:
                                    target_corr.loc[row_idx, col] = float(val)

    # Load asset metadata
    assets = db.query(Asset).all()
    asset_map = {a.id: a for a in assets}

    # Get latest predictions
    subq = db.query(
        Prediction.asset_id,
        func.max(Prediction.predicted_at).label("max_at")
    ).group_by(Prediction.asset_id).subquery()

    latest_preds = db.query(Prediction).join(
        subq,
        (Prediction.asset_id == subq.c.asset_id) & (Prediction.predicted_at == subq.c.max_at)
    ).all()
    pred_map = {}
    for p in latest_preds:
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
            confidence_interval=[pred.confidence_interval_lower, pred.confidence_interval_upper] if (pred and pred.confidence_interval_lower is not None and pred.confidence_interval_upper is not None) else None,
        )

    # Load latest technical features for Motif Mining
    latest_tech_query = text("""
        SELECT t1.asset_id, t1.returns_1d, t1.volatility_7d, t1.rsi_14, t1.macd, t1.macd_signal
        FROM technical_features t1
        JOIN (
            SELECT asset_id, MAX(timestamp) as max_ts
            FROM technical_features
            GROUP BY asset_id
        ) t2 ON t1.asset_id = t2.asset_id AND t1.timestamp = t2.max_ts
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

    # Build edges using canonical topology
    edges = []
    for aid_a, aid_b in canonical_edge_pairs:
        a = asset_map.get(aid_a)
        b = asset_map.get(aid_b)
        if a and b:
            if aid_a in target_corr.index and aid_b in target_corr.columns:
                weight = float(target_corr.loc[aid_a, aid_b])
            elif aid_b in target_corr.index and aid_a in target_corr.columns:
                weight = float(target_corr.loc[aid_b, aid_a])
            else:
                weight = float(live_corr.loc[aid_a, aid_b]) if (aid_a in live_corr.index and aid_b in live_corr.columns) else 0.0

            if np.isnan(weight):
                weight = 0.0

            edge_type = "positive_correlation" if weight >= 0 else "negative_correlation"

            vec_a = tech_vectors.get(aid_a, np.zeros(5))
            vec_b = tech_vectors.get(aid_b, np.zeros(5))
            motif_sim = float(np.dot(vec_a, vec_b))

            edges.append(GraphEdge(
                source=a.symbol,
                target=b.symbol,
                weight=round(weight, 4),
                edge_type=edge_type,
                motif_similarity=round(max(-1.0, min(1.0, motif_sim)), 4)
            ))

    return list(nodes_dict.values()), edges


@router.get("/latest", response_model=GraphResponse)
async def get_latest_graph(mode: str = "live", db: Session = Depends(get_db)):
    """
    Returns current graph for visualization.
    Computes correlation-based graph from local OHLCV/technical_features or forecasts depending on mode ("live", "historical", "projected").
    Includes dynamic topological complex descriptors (Betti-0, Euler Characteristic, and Clustering).
    """
    nodes, edges = _compute_correlation_graph(db, mode=mode)
    
    num_nodes = len(nodes)
    num_edges = len(edges)
    
    # Adjacency list
    adj = {node.symbol: set() for node in nodes}
    for edge in edges:
        adj[edge.source].add(edge.target)
        adj[edge.target].add(edge.source)
        
    # BFS for Connected Components (Betti-0)
    visited = set()
    betti_0 = 0
    for node in nodes:
        if node.symbol not in visited:
            betti_0 += 1
            queue = [node.symbol]
            visited.add(node.symbol)
            while queue:
                curr = queue.pop(0)
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
                        
    # Euler characteristic: V - E
    euler_characteristic = num_nodes - num_edges
    
    # Average Clustering Coefficient
    clustering_sum = 0.0
    for node in nodes:
        neighbors = adj[node.symbol]
        k = len(neighbors)
        if k < 2:
            continue
        links = 0
        neigh_list = list(neighbors)
        for i in range(len(neigh_list)):
            for j in range(i + 1, len(neigh_list)):
                if neigh_list[j] in adj[neigh_list[i]]:
                    links += 1
        clustering_sum += (2.0 * links) / (k * (k - 1))
    average_clustering = clustering_sum / num_nodes if num_nodes > 0 else 0.0
    
    return GraphResponse(
        nodes=nodes,
        edges=edges,
        betti_0=betti_0,
        average_clustering=round(average_clustering, 4),
        euler_characteristic=euler_characteristic
    )


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
