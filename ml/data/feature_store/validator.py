import sys
from datetime import datetime, timedelta
from store import FeatureStore

def main() -> None:
    store = FeatureStore()
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=90)
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    assets = ["BTC", "ETH", "SOL"]
    
    print(f"Loading features for {assets} from {start_str} to {end_str}...")
    features = store.load_node_features(start_str, end_str, assets)
    
    if not features:
        print("Error: No features loaded.")
        sys.exit(1)
        
    try:
        store.validate_features(features)
    except Exception as e:
        print(f"Validation failed: {e}")
        sys.exit(1)
        
    labels = store.get_target_labels(features, horizon_days=1)
    
    for symbol, df in features.items():
        row_count = len(df)
        min_date = df["timestamp"].min()
        max_date = df["timestamp"].max()
        nan_count = df.isna().sum().sum()
        
        lbl_dist = labels[symbol].value_counts().to_dict() if symbol in labels else {}
        
        print(f"\nAsset: {symbol}")
        print(f"Row count: {row_count}")
        print(f"Date range: {min_date} to {max_date}")
        print(f"NaN count total: {nan_count}")
        print(f"Label distribution: {lbl_dist}")
        
    print("\n✅ Feature store validation passed")

if __name__ == "__main__":
    main()
