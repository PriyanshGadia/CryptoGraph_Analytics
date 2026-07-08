import json

log_path = r'C:\Users\gadia\.gemini\antigravity\brain\6ef28010-a304-44b1-a836-9db612d63220\.system_generated\logs\overview.txt'
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get('step_index') == 984:
                print(data['content'][:5000])
                break
        except Exception:
            pass
