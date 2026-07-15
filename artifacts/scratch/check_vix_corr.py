import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone, timedelta

# Adjust path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend')))

from app.db.database import SessionLocal
from app.db.models import Asset, OHLCV

def main():
    db = SessionLocal()
    try:
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="3mo", timeout=5.0)
        print(f"VIX history size: {len(vix_hist)}")
        
        btc_asset = db.query(Asset).filter(Asset.symbol == "BTC").first()
        if not btc_asset:
            print("BTC asset not found in DB")
            return
            
        btc_ohlcv = db.query(OHLCV).filter(
            OHLCV.asset_id == btc_asset.id,
            OHLCV.timestamp >= datetime.now(timezone.utc) - timedelta(days=90)
        ).order_by(OHLCV.timestamp.asc()).all()
        
        print(f"BTC OHLCV records: {len(btc_ohlcv)}")
        
        if len(btc_ohlcv) > 0:
            btc_df = pd.DataFrame([{"date": r.timestamp, "close": r.close} for r in btc_ohlcv])
            print("BTC DF Head:")
            print(btc_df.head(5))
            
            btc_df["date"] = pd.to_datetime(btc_df["date"]).dt.tz_localize(None)
            btc_df = btc_df.set_index("date")
            btc_ret = btc_df["close"].pct_change().dropna()
            
            vix_hist.index = pd.to_datetime(vix_hist.index).tz_localize(None)
            vix_ret = vix_hist["Close"].pct_change().dropna()
            
            print(f"BTC returns size: {len(btc_ret)}")
            print(f"VIX returns size: {len(vix_ret)}")
            
            combined = pd.DataFrame({"btc": btc_ret, "vix": vix_ret}).dropna()
            print(f"Combined size: {len(combined)}")
            if len(combined) > 0:
                print("Combined Head:")
                print(combined.head(5))
                corr = combined.corr().iloc[0, 1]
                print(f"Correlation: {corr}")
            else:
                print("Combined is empty!")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == '__main__':
    main()
