import os

def search_files(directory, keyword):
    matches = []
    for root, dirs, files in os.walk(directory):
        if 'node_modules' in root or '.next' in root or '.git' in root:
            continue
        for file in files:
            if file.endswith('.tsx') or file.endswith('.ts') or file.endswith('.js') or file.endswith('.css'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            if keyword in line.lower():
                                matches.append(f"{filepath}:{line_num}: {line.strip()}")
                except Exception as e:
                    pass
    return matches

print("Search for 'subgraph':")
for match in search_files('G:\\Programming\\CryptoGraph_Analytics\\frontend', 'subgraph')[:30]:
    print(match)

print("\nSearch for 'spheres':")
for match in search_files('G:\\Programming\\CryptoGraph_Analytics\\frontend', 'spheres')[:30]:
    print(match)

print("\nSearch for 'explain':")
for match in search_files('G:\\Programming\\CryptoGraph_Analytics\\frontend', 'explain')[:30]:
    print(match)
