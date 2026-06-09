"""
Full ETL pipeline. Run daily to refresh all data.
"""
import subprocess
import sys
import sentry_sdk
from dotenv import load_dotenv

def run_step(script_path: str, step_name: str) -> None:
    """Run a Python script as subprocess. On failure: log to Sentry, raise."""
    print(f"▶ Starting: {step_name}")
    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        sentry_sdk.capture_message(f"ETL step failed: {step_name}\n{result.stderr}")
        raise RuntimeError(f"{step_name} failed:\n{result.stderr}")
    print(f"✅ Done: {step_name}")

def main():
    load_dotenv("ml/.env")
    
    # Initialize sentry safely if available in env
    import os
    dsn = os.environ.get("SENTRY_DSN")
    if dsn:
        sentry_sdk.init(dsn=dsn)
        
    steps = [
        ("ml/data/ingestion/binance_collector.py",             "Binance OHLCV"),
        ("ml/data/ingestion/fred_collector.py",                "FRED Macro"),
        ("ml/data/ingestion/fear_greed_collector.py",          "Fear & Greed"),
        ("ml/data/ingestion/sentiment_collector.py",           "CoinGecko Sentiment"),
        ("ml/data/feature_engineering/technical_indicators.py","Technical Indicators"),
        ("ml/data/feature_engineering/sentiment_features.py",  "Sentiment Features"),
        ("ml/data/feature_engineering/macro_features.py",      "Macro Normalization"),
        ("ml/data/feature_store/validator.py",                 "Feature Validation"),
    ]
    for script, name in steps:
        run_step(script, name)
    print("🎉 ETL Pipeline completed successfully")

if __name__ == "__main__":
    main()
