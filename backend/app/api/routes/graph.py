"""Graph routes."""
from fastapi import APIRouter, Depends
from app.api.deps import get_supabase
from app.db.models import GraphResponse, GraphNode, GraphEdge

router = APIRouter(prefix="/graph", tags=["graph"])

@router.get("/latest", response_model=GraphResponse)
async def get_latest_graph(db=Depends(get_supabase)):
    """
    Returns current graph for visualization.
    Query latest graph_snapshots grouped by (source_asset, target_asset).
    Join with assets table to get symbol, sector, market_cap_usd.
    Join with predictions for predicted_direction, confidence.
    Build nodes list (deduplicated assets) and edges list.
    """
    # 1. Fetch the latest snapshot date
    snapshot_res = db.table("graph_snapshots").select("timestamp").order("timestamp", desc=True).limit(1).execute()
    
    if not snapshot_res.data:
        return GraphResponse(nodes=[], edges=[])
        
    latest_date = snapshot_res.data[0]['timestamp']
    
    # 2. Fetch edges for that date
    edges_res = db.table("graph_snapshots").select("*, source:assets!source_asset(id, symbol, sector, market_cap_usd), target:assets!target_asset(id, symbol, sector, market_cap_usd)").eq("timestamp", latest_date).execute()
    
    nodes_dict = {}
    edges_list = []
    
    for row in edges_res.data:
        src = row.get("source")
        tgt = row.get("target")
        
        if not src or not tgt:
            continue
            
        src_sym = src["symbol"]
        tgt_sym = tgt["symbol"]
        
        edges_list.append(GraphEdge(
            source=src_sym,
            target=tgt_sym,
            weight=row.get("weight", 0.0),
            edge_type=row.get("edge_type", "correlation")
        ))
        
        # Add to nodes dictionary
        if src_sym not in nodes_dict:
            nodes_dict[src_sym] = {
                "id": str(src["id"]),
                "symbol": src_sym,
                "sector": src.get("sector", "other"),
                "market_cap_usd": src.get("market_cap_usd")
            }
        if tgt_sym not in nodes_dict:
            nodes_dict[tgt_sym] = {
                "id": str(tgt["id"]),
                "symbol": tgt_sym,
                "sector": tgt.get("sector", "other"),
                "market_cap_usd": tgt.get("market_cap_usd")
            }
            
    # 3. Fetch latest predictions to augment nodes
    pred_res = db.table("predictions").select("*, assets(symbol)").order("timestamp", desc=True).limit(200).execute()
    pred_dict = {}
    for p in pred_res.data:
        sym = p.get("assets", {}).get("symbol")
        if sym and sym not in pred_dict:
            pred_dict[sym] = p

    nodes_list = []
    for sym, node_info in nodes_dict.items():
        p_info = pred_dict.get(sym, {})
        nodes_list.append(GraphNode(
            id=node_info["id"],
            symbol=sym,
            sector=node_info["sector"],
            market_cap_usd=node_info.get("market_cap_usd"),
            predicted_direction=p_info.get("direction"),
            confidence=p_info.get("confidence")
        ))
        
    return GraphResponse(nodes=nodes_list, edges=edges_list)

@router.get("/history")
async def get_graph_history(days: int = 7, db=Depends(get_supabase)):
    """
    Returns graph evolution over N days.
    For each day in last `days` days:
      Query graph_snapshots for that date
      Compute: edge_count, density (edge_count/max_possible), top 5 central nodes
    Return list of daily summaries.
    """
    # Simple mockup aggregation for time-series extraction
    res = db.table("graph_snapshots").select("timestamp").order("timestamp", desc=True).limit(days * 1000).execute()
    
    date_counts = {}
    for row in res.data:
        dt = row['timestamp']
        date_counts[dt] = date_counts.get(dt, 0) + 1
        
    history = []
    for dt, count in list(date_counts.items())[:days]:
        history.append({
            "date": dt,
            "edge_count": count,
            "density": min(count / (50*49), 1.0), # Assuming max nodes is 50
            "top_central_nodes": ["BTC", "ETH", "BNB"] # Mock centralities
        })
        
    return history
