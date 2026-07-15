with open('G:\\Programming\\CryptoGraph_Analytics\\ml\\pipelines\\inference_pipeline.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
for i, line in enumerate(lines, 1):
    if 't_shap_attributions' in line or 'shap' in line:
        print(f"{i}: {line.strip()}")
