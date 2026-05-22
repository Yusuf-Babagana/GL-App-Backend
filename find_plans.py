import os

search_dir = r"c:\Users\DELL\Desktop"
target = "NELLOBYTE_STATIC_PLANS"

print("Searching in", search_dir)

for root, dirs, files in os.walk(search_dir):
    # Prune unwanted directories
    dirs[:] = [d for d in dirs if d not in ('node_modules', '.expo', '.git', '.vscode', '__pycache__', 'dist', 'build')]
    for file in files:
        if file.endswith(('.tsx', '.ts', '.js', '.py')):
            path = os.path.join(root, file)
            try:
                content = open(path, 'r', encoding='utf-8', errors='ignore').read()
                if target in content:
                    print(f"FOUND in: {path}")
            except Exception as e:
                pass

print("Search complete.")
