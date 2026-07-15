import yfinance as yf
for sym in ['SUI', 'APT', 'ARB', 'JUP', 'POL', 'TON', 'UNI', 'MATIC', 'GRT', 'MKR', 'OCEAN', 'STX', 'TAO', 'CORE', 'EOS']:
    ticker = yf.Ticker(f'{sym}-USD')
    try:
        info = ticker.info
        print(f'{sym}: marketCap={info.get("marketCap")}, circSupply={info.get("circulatingSupply")}, price={info.get("previousClose")}')
    except Exception as e:
        print(f'{sym} failed: {e}')
