with open('G:\\Programming\\CryptoGraph_Analytics\\frontend\\app\\coin\\[symbol]\\page.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
for i, line in enumerate(lines, 1):
    if '.map' in line or 'ohlcv' in line.lower() or 'fetch' in line or 'useSWR' in line:
        print(f"{i}: {line.strip()}")
