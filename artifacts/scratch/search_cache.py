import os

def search_files(directory, keyword):
    matches = []
    for root, dirs, files in os.walk(directory):
        if 'venv' in root or '.git' in root or '__pycache__' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            if keyword in line:
                                matches.append(f"{filepath}:{line_num}: {line.strip()}")
                except Exception as e:
                    pass
    return matches

print("Search for 'def cached':")
for match in search_files('G:\\Programming\\CryptoGraph_Analytics\\backend', 'def cached'):
    print(match)

print("\nSearch for '@cached':")
for match in search_files('G:\\Programming\\CryptoGraph_Analytics\\backend', '@cached'):
    print(match)
