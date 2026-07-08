import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import f1_score, precision_score, recall_score, classification_report
from sklearn.model_selection import TimeSeriesSplit

# Add project root to Python path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))
if str(root_dir / "backend") not in sys.path:
    sys.path.append(str(root_dir / "backend"))

from ml.data.feature_store.store import FeatureStore

def get_db_symbols():
    try:
        from app.db.database import SessionLocal
        from app.db.models import Asset
        db = SessionLocal()
        try:
            assets = db.query(Asset.symbol).all()
            if assets:
                return [a.symbol for a in assets]
        finally:
            db.close()
    except Exception:
        pass
    return ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE"]

SYMBOLS = get_db_symbols()

def main():
    print("=========================================================")
    print(" XGBoost i3-Optimized Fast Training Pipeline")
    print("=========================================================")
    print("[Step 1] Loading features from FeatureStore...")
    
    store = FeatureStore()
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=730)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")
    
    features = store.load_node_features(start_date, end_date, SYMBOLS, expected_features=24)
    available_symbols = [s for s in SYMBOLS if s in features and not features[s].empty]
    
    if not available_symbols:
        print("No features found. Run ingestion first.")
        return
        
    print(f"Loaded features for {len(available_symbols)} assets.")

    print("\n[Step 2] Building Tabular Dataset...")
    
    feature_cols = [
        "open", "high", "low", "close", "volume", 
        "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
        "returns_1d", "returns_7d", "volatility_7d", 
        "sentiment_score", "fear_greed_norm", "community_score", "public_interest", 
        "sentiment_rolling_3d", "sentiment_momentum", "market_cap_usd",
        "fed_rate", "cpi", "inflation", "vix"
    ]
    
    all_data = []
    
    # Process features and labels
    for sym in available_symbols:
        df = features[sym].copy()
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
            
        df.index = df.index.floor('D')
        df = df[~df.index.duplicated(keep='last')]
        
        # Shift returns to create the target variable (predict next day's return)
        df['target_return_1d'] = df['returns_1d'].shift(-1)
        df = df.dropna(subset=['target_return_1d'])
        
        # Determine classification thresholds
        ret_mean = df['target_return_1d'].mean()
        ret_std = df['target_return_1d'].std()
        
        # 3-class system: 0 (Down), 1 (Neutral), 2 (Up)
        def classify(x):
            if x < ret_mean - 0.5 * ret_std:
                return 0
            elif x > ret_mean + 0.5 * ret_std:
                return 2
            return 1
            
        df['target_class'] = df['target_return_1d'].apply(classify)
        
        # Extract features
        available_cols = [c for c in feature_cols if c in df.columns]
        X_df = df[available_cols].fillna(0.0)
        y_df = df['target_class']
        
        for idx in range(len(X_df)):
            all_data.append({
                'date': df.index[idx],
                'symbol': sym,
                'features': X_df.iloc[idx].values,
                'label': y_df.iloc[idx],
                'raw_return': df['target_return_1d'].iloc[idx]
            })

    # Sort chronologically to prevent lookahead bias
    all_data.sort(key=lambda x: x['date'])
    
    X = np.array([d['features'] for d in all_data])
    y = np.array([d['label'] for d in all_data])
    raw_returns = np.array([d['raw_return'] for d in all_data])
    
    # Chronological Split: 70% Train, 30% Test
    split_idx = int(len(X) * 0.7)
    
    X_train, y_train = X[:split_idx], y[:split_idx]
    X_test, y_test, returns_test = X[split_idx:], y[split_idx:], raw_returns[split_idx:]
    
    print(f"Dataset Size: {len(X)} | Train: {len(X_train)} | Test: {len(X_test)}")
    
    print("\n[Step 3] Training XGBoost Classifier (i3 Optimized)...")
    start_time = time.time()
    
    # XGBoost configuration optimized for i3 (multi-threading limited to physical cores)
    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        n_jobs=-1,  # Uses all available CPU cores efficiently
        random_state=42,
        objective="multi:softmax",
        num_class=3
    )
    
    model.fit(X_train, y_train)
    
    print(f"Training completed in {time.time() - start_time:.2f} seconds.")
    
    print("\n[Step 4] Evaluating Metrics...")
    
    y_pred_train = model.predict(X_train)
    train_f1 = f1_score(y_train, y_pred_train, average='macro')
    
    y_pred_test = model.predict(X_test)
    test_f1 = f1_score(y_test, y_pred_test, average='macro')
    test_precision = precision_score(y_test, y_pred_test, average='macro')
    test_recall = recall_score(y_test, y_pred_test, average='macro')
    
    print(f"\nTraining F1 Score (Macro): {train_f1:.4f}")
    print(f"Test F1 Score (Macro):     {test_f1:.4f}")
    
    # Simulate trading strategy: Long on 2 (Up), Short on 0 (Down), Do nothing on 1 (Neutral)
    strategy_returns = []
    for pred, actual_ret in zip(y_pred_test, returns_test):
        if pred == 2:
            strategy_returns.append(actual_ret)
        elif pred == 0:
            strategy_returns.append(-actual_ret)
        else:
            strategy_returns.append(0.0)
            
    strategy_returns = np.array(strategy_returns)
    mean_ret = np.mean(strategy_returns)
    std_ret = np.std(strategy_returns)
    
    # Annualized Sharpe Ratio (assuming roughly 365 trading days in crypto)
    sharpe_ratio = (mean_ret / std_ret) * np.sqrt(365) if std_ret > 0 else 0.0
    
    win_rate = np.mean(strategy_returns > 0)
    profit_factor = np.sum(strategy_returns[strategy_returns > 0]) / (abs(np.sum(strategy_returns[strategy_returns < 0])) + 1e-9)
    
    print(f"Strategy Sharpe Ratio:     {sharpe_ratio:.4f}")
    print(f"Strategy Win Rate:         {win_rate:.2%}")
    print(f"Strategy Profit Factor:    {profit_factor:.4f}")
    
    # Save artifacts
    artifacts_dir = root_dir / "ml" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    metrics = {
        "train_f1": float(train_f1),
        "test_f1": float(test_f1),
        "precision_macro": float(test_precision),
        "recall_macro": float(test_recall),
        "sharpe_ratio": float(sharpe_ratio),
        "win_rate": float(win_rate),
        "profit_factor": float(profit_factor)
    }
    
    with open(artifacts_dir / "xgboost_metrics.json", "w") as f:
        json.dump(metrics, f, indent=4)
        
    model.save_model(artifacts_dir / "xgboost_model.json")
    print("\nMetrics and model saved to ml/artifacts/")
    
if __name__ == "__main__":
    main()
