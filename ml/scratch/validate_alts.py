import yfinance as yf

alt_tickers = [
    "LRC-USD", "XNO-USD", "SC-USD", "DGB-USD", "RVN-USD", "IOTA-USD", 
    "ONT-USD", "OMG-USD", "ICX-USD", "LSK-USD", "XVG-USD", "SYS-USD"
]

print("Testing alternatives...")
for t in alt_tickers:
    try:
        df = yf.download(t, period="5d", progress=False)
        if df.empty:
            print(f"[-] {t}: EMPTY")
        else:
            print(f"[+] {t}: OK (shape={df.shape})")
    except Exception as e:
        print(f"[-] {t}: ERROR ({e})")
