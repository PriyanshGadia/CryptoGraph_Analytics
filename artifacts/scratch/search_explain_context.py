with open('G:\\Programming\\CryptoGraph_Analytics\\backend\\app\\api\\routes\\explain.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if 'context' in line:
        print(f"{i}: {line.strip()}")
