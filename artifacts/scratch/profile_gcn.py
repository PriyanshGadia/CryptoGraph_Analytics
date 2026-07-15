import time
import torch
from pathlib import Path
from ml.pipelines.training_pipeline_enterprise import EnterpriseSTGCNModel
from ml.data.feature_store.store import FeatureStore
from ml.graph.graph_builder import DynamicGraphBuilder
from datetime import datetime, timedelta, timezone

MODEL_PATH = Path("ml/artifacts/best_model.pt")
model = EnterpriseSTGCNModel.load(str(MODEL_PATH))
model.to(torch.device("cpu"))
model.eval()

# Load features for a single step
store = FeatureStore()
symbols = ["BTC", "ETH", "SOL"]
now = datetime.now(timezone.utc)
end_date = now.strftime("%Y-%m-%d")
start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
features = store.load_node_features(start_date, end_date, symbols, expected_features=24)

builder = DynamicGraphBuilder(supabase_client=None, asset_symbols=symbols, feature_dim=24)
proc_features = {}
for s in symbols:
    df = features[s].copy()
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    proc_features[s] = df

start_dt = datetime.combine((now - timedelta(days=30)).date(), datetime.min.time()).replace(tzinfo=timezone.utc)
end_dt = datetime.combine(now.date(), datetime.min.time()).replace(tzinfo=timezone.utc)

graph_sequence = builder.build_temporal_graph_sequence(
    start_date=start_dt,
    end_date=end_dt,
    features=proc_features,
    lookback_window=14,
)

t0 = time.time()
with torch.no_grad():
    pred, log_var = model([graph_sequence], return_uncertainty=True)
t1 = time.time()
print(f"Forward pass took: {t1 - t0:.4f} seconds")
