import os

for root, _, files in os.walk('frontend'):
    if 'node_modules' in root or '.next' in root: continue
    for f in files:
        if f.endswith('.tsx') or f.endswith('.ts'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            original_content = content
            # Add ?api_key=${process.env.NEXT_PUBLIC_API_KEY} to WebSocket urls if not present
            # We look for WebSocket( and add the api key at the end of the template literal string
            if 'new WebSocket(' in content:
                import re
                # replace: new WebSocket(`${WS_BASE}/api/v1/stream/predictions`);
                # with: new WebSocket(`${WS_BASE}/api/v1/stream/predictions?api_key=${process.env.NEXT_PUBLIC_API_KEY}`);
                content = re.sub(
                    r"new WebSocket\(`([^`]+)`\)",
                    r"new WebSocket(`\1?api_key=${process.env.NEXT_PUBLIC_API_KEY}`)",
                    content
                )
                
            if content != original_content:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(content)
                print(f'Updated {path}')
