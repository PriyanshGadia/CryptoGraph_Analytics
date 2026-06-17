"""Correlation matrix and sector-average routes — local SQLAlchemy backend."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
from app.api.deps import get_db
from app.db.models_sqla import Asset
from app.core.cache import cached

router = APIRouter(prefix="/correlations", tags=["correlations"])


@router.get("/matrix")
@cached(ttl_seconds=300)
def get_correlation_matrix(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Computes Pearson correlation matrix for all assets using local DB."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Batched query for all technical features in range
    rows = db.execute(text("""
        SELECT asset_id, timestamp, returns_1d
        FROM technical_features
        WHERE timestamp >= :since
    """), {"since": since.isoformat()}).fetchall()

    if not rows:
        return {"symbols": [], "matrix": [], "top_pairs": [], "period_days": days}

    df = pd.DataFrame(rows, columns=["asset_id", "timestamp", "returns_1d"])
    df["date"] = df["timestamp"].apply(lambda x: str(x).split("T")[0] if isinstance(x, str) else str(x)[:10])

    # Load assets
    assets = db.query(Asset).all()
    asset_map = {a.id: a for a in assets}

    # Pivot
    pivot = df.pivot_table(index="date", columns="asset_id", values="returns_1d")
    pivot = pivot.ffill()
    min_periods = max(1, int(len(pivot) * 0.5))
    pivot = pivot.dropna(axis=1, thresh=min_periods)

    if pivot.shape[1] < 2:
        return {"symbols": [], "matrix": [], "top_pairs": [], "period_days": days}

    corr_matrix = pivot.corr(method="pearson")

    # Ordered symbols
    ordered_asset_ids = corr_matrix.columns.tolist()
    ordered_symbols = [
        asset_map.get(aid).symbol if asset_map.get(aid) else str(aid)
        for aid in ordered_asset_ids
    ]

    matrix_values = corr_matrix.fillna(0).values.tolist()

    # Top correlated pairs
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
    corr_matrix.index.name = "asset_a"
    corr_matrix.columns.name = "asset_b"
    corr_flat = corr_matrix.where(mask).stack().reset_index(name="correlation")
    corr_flat["abs_corr"] = corr_flat["correlation"].abs()
    top_flat = corr_flat.sort_values(by="abs_corr", ascending=False).head(20)

    top_pairs = []
    for _, row in top_flat.iterrows():
        info_a = asset_map.get(row["asset_a"])
        info_b = asset_map.get(row["asset_b"])
        top_pairs.append({
            "symbol_a": info_a.symbol if info_a else str(row["asset_a"]),
            "symbol_b": info_b.symbol if info_b else str(row["asset_b"]),
            "correlation": float(row["correlation"]),
            "sector_a": info_a.sector if info_a else "other",
            "sector_b": info_b.sector if info_b else "other",
        })

    return {
        "symbols": ordered_symbols,
        "matrix": matrix_values,
        "top_pairs": top_pairs,
        "period_days": days,
    }


@router.get("/sector-average")
@cached(ttl_seconds=300)
def get_sector_correlations(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Returns average intra-sector and inter-sector correlations using local DB."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = db.execute(text("""
        SELECT asset_id, timestamp, returns_1d
        FROM technical_features
        WHERE timestamp >= :since
    """), {"since": since.isoformat()}).fetchall()

    if not rows:
        return {"sectors": [], "matrix": [], "intra_sector": {}}

    df = pd.DataFrame(rows, columns=["asset_id", "timestamp", "returns_1d"])
    df["date"] = df["timestamp"].apply(lambda x: str(x).split("T")[0] if isinstance(x, str) else str(x)[:10])

    assets = db.query(Asset).all()
    asset_sector_map = {a.id: (a.sector or "other") for a in assets}

    pivot = df.pivot_table(index="date", columns="asset_id", values="returns_1d")
    pivot = pivot.ffill().dropna(axis=1, thresh=max(1, len(pivot) // 2))

    if pivot.shape[1] < 2:
        return {"sectors": [], "matrix": [], "intra_sector": {}}

    corr_matrix = pivot.corr(method="pearson")

    sectors = sorted(set(asset_sector_map.values()))
    intra_sector = {}
    sector_matrix = []

    for s1 in sectors:
        row_vals = []
        assets_s1 = [c for c in corr_matrix.columns if asset_sector_map.get(c) == s1]

        if len(assets_s1) > 1:
            sub_corr = corr_matrix.loc[assets_s1, assets_s1]
            mask = np.triu(np.ones_like(sub_corr, dtype=bool), k=1)
            vals = sub_corr.where(mask).stack().values
            intra_sector[s1] = float(np.nanmean(vals)) if len(vals) > 0 else 0.0
        elif len(assets_s1) == 1:
            intra_sector[s1] = 1.0
        else:
            intra_sector[s1] = 0.0

        for s2 in sectors:
            assets_s2 = [c for c in corr_matrix.columns if asset_sector_map.get(c) == s2]
            if not assets_s1 or not assets_s2:
                row_vals.append(0.0)
            elif s1 == s2:
                row_vals.append(intra_sector[s1])
            else:
                sub_corr = corr_matrix.loc[assets_s1, assets_s2]
                val = float(np.nanmean(sub_corr.values))
                row_vals.append(0.0 if np.isnan(val) else val)

        sector_matrix.append(row_vals)

    # Clean NaN
    for key, val in intra_sector.items():
        try:
            if val is None or np.isnan(val):
                intra_sector[key] = 0.0
        except (TypeError, ValueError):
            intra_sector[key] = 0.0
    for i in range(len(sector_matrix)):
        for j in range(len(sector_matrix[i])):
            try:
                if sector_matrix[i][j] is None or np.isnan(sector_matrix[i][j]):
                    sector_matrix[i][j] = 0.0
            except (TypeError, ValueError):
                sector_matrix[i][j] = 0.0

    return {
        "sectors": sectors,
        "matrix": sector_matrix,
        "intra_sector": intra_sector,
    }
