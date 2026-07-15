import os

def search_files(directory, keywords):
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
                            if any(kw in line for kw in keywords):
                                matches.append(f"{filepath}:{line_num}: {line.strip()}")
                except Exception as e:
                    pass
    return matches

print("Search for Prediction( or predictions table insertions:")
for match in search_files('G:\\Programming\\CryptoGraph_Analytics\\backend', ['Prediction(', 'insert_prediction', 'db.add(pred']):
    print(match)

print("\nSearch for inference pipeline:")
for match in search_files('G:\\Programming\\CryptoGraph_Analytics\\ml', ['Prediction(', 'shap_values', 'insert_prediction', 'db.add(pred']):
    print(match)
