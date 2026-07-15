with open('G:\\Programming\\CryptoGraph_Analytics\\ml\\pipelines\\inference_pipeline.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if 'xai_explainer' in line or 'explainability' in line:
        print(f"{i}: {line.strip()}")
