import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend')))
from app.db.database import SessionLocal
from app.db.models import Asset, OHLCV

def main():
    db = SessionLocal()
    try:
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="3mo", timeout=5.0)
        btc_asset = db.query(Asset).filter(Asset.symbol == "BTC").first()
        btc_ohlcv = db.query(OHLCV).filter(
            OHLCV.asset_id == btc_asset.id,
            OHLCV.timestamp >= datetime.now(timezone.utc) - timedelta(days=90)
        ).order_by(OHLCV.timestamp.asc()).all()
        
        # 1. Original method
        btc_df_orig = pd.DataFrame([{"date": r.timestamp, "close": r.close} for r in btc_ohlcv])
        btc_df_orig["date"] = pd.to_datetime(btc_df_orig["date"]).dt.tz_localize(None)
        btc_df_orig = btc_df_orig.set_index("date")
        btc_ret_orig = btc_df_orig["close"].pct_change().dropna()
        
        vix_hist_orig = vix_hist.copy()
        vix_hist_orig.index = pd.to_datetime(vix_hist_orig.index).tz_localize(None)
        vix_ret_orig = vix_hist_orig["Close"].pct_change().dropna()
        
        combined_orig = pd.DataFrame({"btc": btc_ret_orig, "vix": vix_ret_orig}).dropna()
        print(f"Original Combined size: {len(combined_orig)}")
        if len(combined_orig) > 0:
            print(f"Original Correlation: {combined_orig.corr().iloc[0, 1]}")
            
        # 2. Normalized method
        btc_df_norm = pd.DataFrame([{"date": r.timestamp, "close": r.close} for r in btc_ohlcv])
        btc_df_norm["date"] = pd.to_datetime(btc_df_norm["date"]).dt.tz_localize(None).dt.normalize()
        btc_df_norm = btc_df_norm.groupby("date").last()
        btc_ret_norm = btc_df_norm["close"].pct_change().dropna()
        
        vix_hist_norm = vix_hist.copy()
        vix_hist_norm.index = pd.to_datetime(vix_hist_norm.index).tz_localize(None).normalize()
        vix_ret_norm = vix_hist_norm["Close"].pct_change().dropna()
        
        combined_norm = pd.DataFrame({"btc": btc_ret_norm, "vix": vix_ret_norm}).dropna()
        print(f"Normalized Combined size: {len(combined_norm)}")
        if len(combined_norm) > 0:
            print(f"Normalized Correlation: {combined_norm.corr().iloc[0, 1]}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == '__main__':
    main()
