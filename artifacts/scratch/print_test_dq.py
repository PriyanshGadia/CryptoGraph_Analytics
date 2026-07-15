with open('G:\\Programming\\CryptoGraph_Analytics\\backend\\test_data_quality.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
for i, line in enumerate(lines, 1):
    print(f"{i}: {line.strip()}")
