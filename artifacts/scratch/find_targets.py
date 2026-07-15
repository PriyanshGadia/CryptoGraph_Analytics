with open('G:\\Programming\\CryptoGraph_Analytics\\frontend\\app\\coin\\[symbol]\\page.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("Line 115-125:")
for idx in range(115, 126):
    print(f"{idx}: {lines[idx-1].strip()}")

print("\nLine 345-355:")
for idx in range(345, 356):
    print(f"{idx}: {lines[idx-1].strip()}")

print("\nLine 690-700:")
for idx in range(690, 701):
    print(f"{idx}: {lines[idx-1].strip()}")

print("\nLine 720-730:")
for idx in range(720, 731):
    print(f"{idx}: {lines[idx-1].strip()}")
