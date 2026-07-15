import os

def search_files(directory, keyword):
    matches = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.tsx'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            if keyword in line.lower():
                                matches.append(f"{filepath}:{line_num}: {line.strip()}")
                except Exception as e:
                    pass
    return matches

for match in search_files('G:\\Programming\\CryptoGraph_Analytics\\frontend\\app', 'attribution'):
    print(match)
