import os

def search_files(directory, keyword):
    matches = []
    for root, dirs, files in os.walk(directory):
        if 'node_modules' in root or '.next' in root or '.git' in root:
            continue
        for file in files:
            if file.endswith('.tsx') or file.endswith('.ts'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            if keyword in line:
                                matches.append(f"{filepath}:{line_num}: {line.strip()}")
                except Exception as e:
                    pass
    return matches

for match in search_files('G:\\Programming\\CryptoGraph_Analytics\\frontend', 'ForceGraph2D'):
    print(match)
