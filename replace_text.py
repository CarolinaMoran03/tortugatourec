import os

directory = r'c:\Users\CM\Documents\tortugatour (1)\tortugatour\tortugatour'
count = 0

for root, _, files in os.walk(directory):
    if '.venv' in root or '__pycache__' in root or '.git' in root:
        continue
    for file in files:
        if file.endswith('.html') or file.endswith('.py'):
            path = os.path.join(root, file)
            if 'replace_text.py' in path: continue
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                if 'TortugaTour' in content:
                    content = content.replace('TortugaTour', 'TortugaTur')
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    count += 1
            except Exception as e:
                pass

print(f"Replaced in {count} files")
