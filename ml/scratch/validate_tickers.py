import yfinance as yf
import pandas as pd

tickers_to_test = [
    # New additions
    "MATIC-USD", "STX-USD", "KAVA-USD", "DASH-USD", "ZRX-USD", "BAL-USD", 
    "YFI-USD", "KNC-USD", "WAVES-USD", "ZIL-USD", "REN-USD", "STORJ-USD", 
    "BAND-USD", "CELR-USD", "SKL-USD", "NMR-USD", "MIOTA-USD", "QTUM-USD"
]

print("Validating tickers on yfinance...")
failed = []
for t in tickers_to_test:
    try:
        df = yf.download(t, period="5d", progress=False)
        if df.empty:
            print(f"[-] {t}: EMPTY DATAFRAME")
            failed.append(t)
        else:
            print(f"[+] {t}: OK (shape={df.shape})")
    except Exception as e:
        print(f"[-] {t}: ERROR ({e})")
        failed.append(t)

if failed:
    print(f"\nFailed tickers: {failed}")
else:
    print("\nAll tickers validated successfully!")
