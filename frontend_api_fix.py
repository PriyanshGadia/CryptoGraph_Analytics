import os
import glob

for root, _, files in os.walk('frontend'):
    if 'node_modules' in root or '.next' in root: continue
    for f in files:
        if f.endswith('.tsx') or f.endswith('.ts'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Check for literal string paths like "/api/..." or `/api/...` or '/api/...'
            # Also avoiding replacing /api/v1/ again if it somehow exists
            original_content = content
            content = content.replace('"/api/', '"/api/v1/')
            content = content.replace('`/api/', '`/api/v1/')
            content = content.replace("'/api/", "'/api/v1/")
            
            # Fix double replacements just in case
            content = content.replace('"/api/v1/v1/', '"/api/v1/')
            content = content.replace('`/api/v1/v1/', '`/api/v1/')
            content = content.replace("'/api/v1/v1/", "'/api/v1/")

            if content != original_content:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(content)
                print(f'Updated {path}')
