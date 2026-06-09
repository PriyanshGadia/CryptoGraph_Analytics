from fastapi import APIRouter, Depends
from app.api.deps import get_supabase
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
from app.core.cache import cached

router = APIRouter(prefix="/correlations", tags=["correlations"])

@router.get("/matrix")
@cached(ttl_seconds=300)
def get_correlation_matrix(
    days: int = 30,
    db=Depends(get_supabase)
):
    """
    Computes Pearson correlation matrix for all assets.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    
    # 1. Query technical_features
    all_data = []
    start = 0
    limit = 1000
    while True:
        res = db.table("technical_features")\
            .select("asset_id, timestamp, returns_1d")\
            .gte("timestamp", since.isoformat())\
            .range(start, start + limit - 1)\
            .execute()
        all_data.extend(res.data)
        if len(res.data) < limit:
            break
        start += limit
        
    df = pd.DataFrame(all_data)
    if df.empty:
        return {"symbols": [], "matrix": [], "top_pairs": [], "period_days": days}
        
    # 2. Load assets
    assets_res = db.table("assets").select("id, symbol, sector").execute()
    asset_map = {a["id"]: a for a in assets_res.data}
    
    # Format dates
    df['date'] = df['timestamp'].apply(lambda x: x.split("T")[0])
    
    # 3. Pivot
    pivot = df.pivot_table(index='date', columns='asset_id', values='returns_1d')
    
    # 5. Forward-fill then drop assets with < 50% data coverage
    pivot = pivot.ffill()
    min_periods = len(pivot) * 0.5
    pivot = pivot.dropna(axis=1, thresh=min_periods)
    
    # 4. Compute correlation
    corr_matrix = pivot.corr(method='pearson')
    
    # Prepare ordered symbols
    ordered_asset_ids = corr_matrix.columns.tolist()
    ordered_symbols = [asset_map.get(aid, {}).get("symbol", str(aid)) for aid in ordered_asset_ids]
    
    # Generate matrix
    matrix_values = corr_matrix.fillna(0).values.tolist()
    
    # Get top pairs
    top_pairs = []
    # Mask out diagonal and lower triangle to avoid duplicates
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
    
    # Rename axes to avoid duplicate column names during reset_index
    corr_matrix.index.name = 'asset_a'
    corr_matrix.columns.name = 'asset_b'
    
    corr_flat = corr_matrix.where(mask).stack().reset_index(name='correlation')
    
    # Sort by absolute correlation
    corr_flat['abs_corr'] = corr_flat['correlation'].abs()
    top_flat = corr_flat.sort_values(by='abs_corr', ascending=False).head(20)
    
    for _, row in top_flat.iterrows():
        aid_a = row['asset_a']
        aid_b = row['asset_b']
        info_a = asset_map.get(aid_a, {})
        info_b = asset_map.get(aid_b, {})
        
        top_pairs.append({
            "symbol_a": info_a.get("symbol"),
            "symbol_b": info_b.get("symbol"),
            "correlation": float(row['correlation']),
            "sector_a": info_a.get("sector"),
            "sector_b": info_b.get("sector")
        })
        
    return {
        "symbols": ordered_symbols,
        "matrix": matrix_values,
        "top_pairs": top_pairs,
        "period_days": days
    }

@router.get("/sector-average")
@cached(ttl_seconds=300)
def get_sector_correlations(
    days: int = 30,
    db=Depends(get_supabase)
):
    """
    Returns average intra-sector and inter-sector correlations.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    
    all_data = []
    start = 0
    limit = 1000
    while True:
        res = db.table("technical_features")\
            .select("asset_id, timestamp, returns_1d")\
            .gte("timestamp", since.isoformat())\
            .range(start, start + limit - 1)\
            .execute()
        all_data.extend(res.data)
        if len(res.data) < limit:
            break
        start += limit
        
    df = pd.DataFrame(all_data)
    if df.empty:
        return {"sectors": [], "matrix": [], "intra_sector": {}}
        
    assets_res = db.table("assets").select("id, symbol, sector").execute()
    asset_sector_map = {a["id"]: a.get("sector", "other") for a in assets_res.data}
    
    df['date'] = df['timestamp'].apply(lambda x: x.split("T")[0])
    pivot = df.pivot_table(index='date', columns='asset_id', values='returns_1d')
    pivot = pivot.ffill().dropna(axis=1, thresh=len(pivot)*0.5)
    
    corr_matrix = pivot.corr(method='pearson')
    
    # Map back to sectors
    sectors = sorted(list(set(asset_sector_map.values())))
    
    intra_sector = {}
    sector_matrix = []
    
    # We'll group columns by sector and compute block averages
    for i, s1 in enumerate(sectors):
        row_vals = []
        # Get assets in s1
        assets_s1 = [c for c in corr_matrix.columns if asset_sector_map.get(c) == s1]
        
        # Intra sector average
        if len(assets_s1) > 1:
            # sub matrix without diagonal
            sub_corr = corr_matrix.loc[assets_s1, assets_s1]
            mask = np.triu(np.ones_like(sub_corr, dtype=bool), k=1)
            vals = sub_corr.where(mask).stack().values
            intra_sector[s1] = float(np.mean(vals)) if len(vals) > 0 else 0.0
        elif len(assets_s1) == 1:
            intra_sector[s1] = 1.0
        else:
            intra_sector[s1] = 0.0
            
        # Inter sector average
        for s2 in sectors:
            assets_s2 = [c for c in corr_matrix.columns if asset_sector_map.get(c) == s2]
            if not assets_s1 or not assets_s2:
                row_vals.append(0.0)
            elif s1 == s2:
                row_vals.append(intra_sector[s1])
            else:
                sub_corr = corr_matrix.loc[assets_s1, assets_s2]
                val = float(np.nanmean(sub_corr.values))
                if np.isnan(val):
                    val = 0.0
                row_vals.append(val)
                
        sector_matrix.append(row_vals)
        
    # Clean up any remaining NaNs
    for key, val in intra_sector.items():
        if np.isnan(val):
            intra_sector[key] = 0.0
            
    for i in range(len(sector_matrix)):
        for j in range(len(sector_matrix[i])):
            if np.isnan(sector_matrix[i][j]):
                sector_matrix[i][j] = 0.0
        
    result = {
        "sectors": sectors,
        "matrix": sector_matrix,
        "intra_sector": intra_sector
    }
    return result
