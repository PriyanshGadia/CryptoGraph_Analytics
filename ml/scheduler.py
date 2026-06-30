"""
Scheduled data refresh for ST-GCN platform.
Refresh intervals:
  OHLCV prices:    every 5 minutes  (Binance API)
  Technical feats: every 6 hours    (computed from OHLCV)
  Predictions:     every 24 hours   (real GCN inference)
  Enrich assets:   every 24 hours   (sector + market cap from CoinGecko)
"""
import time
import subprocess
import sys
import os
import logging
from datetime import datetime, timezone
from pathlib import Path

# Change working directory to ml/ so relative paths work
os.chdir(Path(__file__).parent)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCHEDULER] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scheduler.log", mode="a", encoding="utf-8")
    ]
)
log = logging.getLogger(__name__)

INTERVALS = {
    "ohlcv":         300,     # 5 minutes
    "features":      21600,   # 6 hours
    "predictions":   86400,   # 24 hours
    "enrich_assets": 86400,   # 24 hours - refreshes market cap daily
}

SCRIPTS = {
    "ohlcv":         "data/ingestion/binance_collector.py",
    "features":      "data/feature_engineering/technical_indicators.py",
    "predictions":   "pipelines/inference_pipeline.py",
    "enrich_assets": "data/ingestion/enrich_assets.py",
}

last_run = {k: 0.0 for k in SCRIPTS}
run_count = {k: 0    for k in SCRIPTS}

def run_script(name: str, path: str) -> bool:
    """Run a script. Returns True on success."""
    log.info(f"Starting: {name} ({path})")
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=600   # 10 min max
        )
        elapsed = round(time.time() - start, 1)
        if result.returncode == 0:
            run_count[name] += 1
            log.info(f"Done: {name} in {elapsed}s (run #{run_count[name]})")
            return True
        else:
            log.error(f"Failed: {name} after {elapsed}s\n"
                      f"stderr: {result.stderr[-300:]}")
            return False
    except subprocess.TimeoutExpired:
        log.error(f"Timeout: {name} exceeded 10 minutes")
        return False
    except Exception as e:
        log.error(f"Exception in {name}: {e}")
        return False

def format_next_run(name: str) -> str:
    elapsed  = time.time() - last_run[name]
    interval = INTERVALS[name]
    remaining = max(0, interval - elapsed)
    if remaining < 60:
        return f"{int(remaining)}s"
    elif remaining < 3600:
        return f"{int(remaining/60)}m"
    else:
        return f"{remaining/3600:.1f}h"

def print_status() -> None:
    log.info("--- Scheduler Status -------------------------------")
    for name in SCRIPTS:
        next_in = format_next_run(name)
        runs    = run_count[name]
        log.info(f"  {name:<15} next in {next_in:<8} | runs: {runs}")
    log.info("----------------------------------------------------")

def main() -> None:
    log.info("ST-GCN Scheduler started")
    log.info("Intervals: ohlcv=5min | features=6hr | "
             "predictions=24hr | enrich_assets=24hr")
    log.info("Press Ctrl+C to stop")

    # Run in this specific order on startup:
    # enrich_assets FIRST so sectors are set before any collector runs
    STARTUP_ORDER = [
        "enrich_assets",  # set sectors first
        "ohlcv",          # now safe — sectors already exist
        "features",
        "predictions",
    ]

    for name in STARTUP_ORDER:
        path = SCRIPTS[name]
        success = run_script(name, path)
        last_run[name] = time.time()
        if not success:
            log.warning(f"Initial run of {name} failed - will retry at next interval")
        time.sleep(10)  # stagger startup

    status_timer = time.time()

    while True:
        now = time.time()

        # Print status every 30 minutes
        if now - status_timer >= 1800:
            print_status()
            status_timer = now

        # Check each script
        for name, interval in INTERVALS.items():
            if now - last_run[name] >= interval:
                run_script(name, SCRIPTS[name])
                last_run[name] = time.time()

        time.sleep(60)  # check every minute

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Scheduler stopped by user")
        print_status()
