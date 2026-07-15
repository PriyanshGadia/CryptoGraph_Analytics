with open('G:\\Programming\\CryptoGraph_Analytics\\frontend\\app\\coin\\[symbol]\\page.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if 'correlations' in line:
        print(f"{i}: {line.strip()}")
