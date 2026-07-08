import os

file_path = r"g:\Programming\CryptoGraph_Analytics\frontend\app\graph\page.tsx"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace hardcoded white/ border and background values with theme-aware classes
content = content.replace("border-white/5", "border-text/5")
content = content.replace("border border-white/5", "border border-text/5")
content = content.replace("border-white/10", "border-text/10")
content = content.replace("border border-white/10", "border border-text/10")
content = content.replace("hover:bg-white/10", "hover:bg-text/5")
content = content.replace("hover:bg-white/5", "hover:bg-text/5")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Replaced graph borders successfully.")
