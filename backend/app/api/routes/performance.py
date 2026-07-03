"""Performance routes — local SQLAlchemy backend."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc, text
from datetime import datetime, timezone, timedelta
import numpy as np
from app.api.deps import get_db
from app.db.models_sqla import Prediction, Asset, OHLCV
from app.core.cache import cached

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("")
@router.get("/")
@cached(ttl_seconds=300)
def get_model_performance(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """
    Computes model accuracy metrics by comparing past predictions
    against actual price moves using local SQLite data.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    # 1. Get all predictions from last N days
    preds = db.query(Prediction).filter(
        Prediction.predicted_at >= since
    ).order_by(desc(Prediction.predicted_at)).all()

    empty_result = {
        "period_days": days,
        "total_predictions": 0,
        "total_scored": 0,
        "overall_accuracy": 0,
        "per_direction_accuracy": {},
        "per_asset_accuracy": {},
        "confidence_calibration": [],
        "confusion_matrix": [],
        "confusion_labels": ["strong_up", "up", "neutral", "down", "strong_down"],
        "rolling_accuracy": [],
        "strategy_return_pct": 0,
        "strategy_sharpe": 0,
        "strategy_win_rate": 0,
        "model_version": "unknown",
    }

    if not preds:
        return empty_result

    # Get all assets
    assets = db.query(Asset).all()
    asset_map = {a.id: a.symbol for a in assets}

    # 2. Get OHLCV for price comparisons (batched)
    since_ohlcv = since - timedelta(days=2)
    ohlcv_rows = db.query(OHLCV).filter(
        OHLCV.timestamp >= since_ohlcv
    ).all()

    # Build price map: asset_id -> date_str -> close
    price_map = {}
    for r in ohlcv_rows:
        aid = r.asset_id
        ts = r.timestamp
        date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        if aid not in price_map:
            price_map[aid] = {}
        price_map[aid][date_str] = r.close

    # Accumulators
    total_predictions = len(preds)
    total_scored = 0
    correct_count = 0

    dir_stats = {d: {"total": 0, "correct": 0} for d in ["strong_up", "up", "neutral", "down", "strong_down"]}
    asset_stats = {}
    for aid in asset_map:
        asset_stats[aid] = {"total": 0, "correct": 0, "conf_sum": 0, "best_dir": {}}

    calib_buckets = {i: {"total": 0, "correct": 0} for i in range(10)}

    confusion_labels = ["strong_up", "up", "neutral", "down", "strong_down"]
    label_to_idx = {l: i for i, l in enumerate(confusion_labels)}
    confusion_matrix = [[0 for _ in range(5)] for _ in range(5)]

    daily_stats = {}

    # Strategy simulation
    capital = 100.0
    strategy_returns = []
    winning_trades = 0
    total_trades = 0

    model_version = preds[0].model_version or "unknown"

    for p in preds:
        aid = p.asset_id
        ts = p.predicted_at or p.timestamp
        if not ts:
            continue
        date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]

        try:
            pred_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue

        next_day_str = (pred_date + timedelta(days=1)).strftime("%Y-%m-%d")

        direction = p.direction or "neutral"
        conf = p.confidence or 0

        if date_str not in daily_stats:
            daily_stats[date_str] = {"total": 0, "correct": 0}

        close_today = None
        close_next = None

        if aid in price_map and date_str in price_map[aid]:
            close_today = price_map[aid][date_str]
            if next_day_str in price_map[aid]:
                close_next = price_map[aid][next_day_str]
            else:
                sym = asset_map.get(aid)
                if sym:
                    from app.core.streams.binance_ws import get_global_market_state
                    market_state = get_global_market_state()
                    live_price = market_state.get(sym, {}).get("current_price", 0)
                    if live_price > 0:
                        close_next = live_price
        else:
            ohlcv_today = db.query(OHLCV).filter(
                OHLCV.asset_id == aid,
                OHLCV.timestamp <= ts
            ).order_by(desc(OHLCV.timestamp)).first()
            if ohlcv_today:
                close_today = ohlcv_today.close
                sym = asset_map.get(aid)
                if sym:
                    from app.core.streams.binance_ws import get_global_market_state
                    market_state = get_global_market_state()
                    live_price = market_state.get(sym, {}).get("current_price", 0)
                    if live_price > 0:
                        close_next = live_price

        if close_today and close_next and close_today > 0:
            actual_return = (close_next - close_today) / close_today

            # Determine actual class
            if actual_return > 0.03:
                actual_class = "strong_up"
            elif actual_return > 0:
                actual_class = "up"
            elif actual_return < -0.03:
                actual_class = "strong_down"
            elif actual_return < 0:
                actual_class = "down"
            else:
                actual_class = "neutral"

            pred_idx = label_to_idx.get(direction, 2)
            actual_idx = label_to_idx.get(actual_class, 2)
            confusion_matrix[pred_idx][actual_idx] += 1

            was_correct = False
            if direction in ["up", "strong_up"] and actual_return > 0:
                was_correct = True
            elif direction in ["down", "strong_down"] and actual_return < 0:
                was_correct = True
            elif direction == "neutral" and abs(actual_return) < 0.01:
                was_correct = True

            total_scored += 1
            if was_correct:
                correct_count += 1
                daily_stats[date_str]["correct"] += 1
                if direction in dir_stats:
                    dir_stats[direction]["correct"] += 1
                if aid in asset_stats:
                    asset_stats[aid]["correct"] += 1

            daily_stats[date_str]["total"] += 1
            if direction in dir_stats:
                dir_stats[direction]["total"] += 1

            if aid in asset_stats:
                asset_stats[aid]["total"] += 1
                asset_stats[aid]["conf_sum"] += conf

                best_dir = asset_stats[aid]["best_dir"]
                if direction not in best_dir:
                    best_dir[direction] = {"total": 0, "correct": 0}
                best_dir[direction]["total"] += 1
                if was_correct:
                    best_dir[direction]["correct"] += 1

            bucket_idx = min(int(conf * 10), 9) if conf <= 1 else min(int(conf / 10), 9)
            calib_buckets[bucket_idx]["total"] += 1
            if was_correct:
                calib_buckets[bucket_idx]["correct"] += 1

            # Strategy simulation
            conf_threshold = 0.65 if conf <= 1 else 65
            if direction in ["up", "strong_up"] and conf > conf_threshold:
                trade_return = actual_return
                strategy_returns.append(trade_return)
                capital *= (1 + trade_return)
                total_trades += 1
                if trade_return > 0:
                    winning_trades += 1

    overall_accuracy = correct_count / total_scored if total_scored > 0 else 0

    per_direction_accuracy = {}
    for d, stats in dir_stats.items():
        per_direction_accuracy[d] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0

    per_asset_accuracy = {}
    for aid, stats in asset_stats.items():
        if stats["total"] > 0:
            sym = asset_map.get(aid, str(aid))
            acc = stats["correct"] / stats["total"]
            avg_conf = stats["conf_sum"] / stats["total"]

            best_d = "N/A"
            best_d_acc = -1
            for d, dstats in stats["best_dir"].items():
                if dstats["total"] >= 3:
                    dacc = dstats["correct"] / dstats["total"]
                    if dacc > best_d_acc:
                        best_d_acc = dacc
                        best_d = d

            per_asset_accuracy[sym] = {
                "accuracy": acc,
                "correct": stats["correct"],
                "wrong": stats["total"] - stats["correct"],
                "avg_confidence": avg_conf,
                "best_direction": best_d,
            }

    confidence_calibration = []
    for i in range(10):
        b_range = f"{i*10}-{(i+1)*10}%"
        stats = calib_buckets[i]
        if stats["total"] > 0:
            act_acc = (stats["correct"] / stats["total"]) * 100
            confidence_calibration.append({
                "confidence_range": b_range,
                "actual_accuracy": act_acc,
                "count": stats["total"],
            })

    # Rolling accuracy
    sorted_dates = sorted(daily_stats.keys())
    rolling_accuracy = []
    for i, date_str in enumerate(sorted_dates):
        start_7d = max(0, i - 6)
        tot_7d = sum(daily_stats[d]["total"] for d in sorted_dates[start_7d:i+1])
        corr_7d = sum(daily_stats[d]["correct"] for d in sorted_dates[start_7d:i+1])
        acc_7d = (corr_7d / tot_7d * 100) if tot_7d > 0 else 0

        start_30d = max(0, i - 29)
        tot_30d = sum(daily_stats[d]["total"] for d in sorted_dates[start_30d:i+1])
        corr_30d = sum(daily_stats[d]["correct"] for d in sorted_dates[start_30d:i+1])
        acc_30d = (corr_30d / tot_30d * 100) if tot_30d > 0 else 0

        rolling_accuracy.append({
            "date": date_str,
            "accuracy_7d": acc_7d,
            "accuracy_30d": acc_30d,
        })

    strategy_return_pct = (capital - 100) / 100 * 100

    if len(strategy_returns) > 1:
        ret_array = np.array(strategy_returns)
        mean_ret = np.mean(ret_array)
        std_ret = np.std(ret_array)
        strategy_sharpe = float((mean_ret / std_ret) * np.sqrt(365)) if std_ret > 0 else 0.0
    else:
        strategy_sharpe = 0.0

    strategy_win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

    return {
        "period_days": days,
        "total_predictions": total_predictions,
        "total_scored": total_scored,
        "overall_accuracy": overall_accuracy,
        "per_direction_accuracy": per_direction_accuracy,
        "per_asset_accuracy": per_asset_accuracy,
        "confidence_calibration": confidence_calibration,
        "confusion_matrix": confusion_matrix,
        "confusion_labels": confusion_labels,
        "rolling_accuracy": rolling_accuracy,
        "strategy_return_pct": strategy_return_pct,
        "strategy_sharpe": strategy_sharpe,
        "strategy_win_rate": strategy_win_rate,
        "model_version": model_version,
    }
