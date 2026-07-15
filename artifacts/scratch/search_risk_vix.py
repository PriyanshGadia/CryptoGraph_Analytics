with open('G:\\Programming\\CryptoGraph_Analytics\\frontend\\app\\risk\\page.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
for i, line in enumerate(lines, 1):
    if 'vix' in line.lower() or 'correlation' in line.lower() or 'macro' in line.lower():
        print(f"{i}: {line.strip()}")
