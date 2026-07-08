import os

file_path = r"g:\Programming\CryptoGraph_Analytics\frontend\app\graph\page.tsx"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Helper function to replace exact parts or line-match blocks
def replace_fuzzy(tgt_lines_str, rpl_lines_str):
    global content
    content_lines = content.splitlines()
    target_lines = [l.strip() for l in tgt_lines_str.strip().splitlines()]
    replacement_lines = rpl_lines_str.splitlines()
    
    match_idx = -1
    for i in range(len(content_lines) - len(target_lines) + 1):
        match = True
        for j in range(len(target_lines)):
            if content_lines[i+j].strip() != target_lines[j]:
                match = False
                break
        if match:
            match_idx = i
            break
            
    if match_idx != -1:
        # Check original indentation of the first line
        orig_line = content_lines[match_idx]
        indent = orig_line[:len(orig_line) - len(orig_line.lstrip())]
        
        indented_repl = []
        for rl in replacement_lines:
            if rl.strip() == "":
                indented_repl.append("")
            else:
                indented_repl.append(indent + rl.lstrip())
                
        content_lines[match_idx : match_idx + len(target_lines)] = indented_repl
        content = "\n".join(content_lines)
        print(f"Replaced block successfully starting with: {target_lines[0][:30]}...")
        return True
    else:
        print(f"FAILED to find block starting with: {target_lines[0][:30]}...")
        return False

# 1. Replace imports
replace_fuzzy(
    'import { useChartPalette } from "@/lib/useChartPalette";',
    'import { useChartPalette } from "@/lib/useChartPalette";\nimport { useTheme } from "next-themes";'
)

# 2. Replace SECTOR_COLORS and SECTOR_LABELS
replace_fuzzy(
    """const SECTOR_COLORS: Record<string, string> = {
  layer1: "#6366f1",
  defi: "#22c55e",
  exchange: "#f59e0b",
  payment: "#06b6d4",
  gaming: "#a855f7",
  privacy: "#ef4444",
  storage: "#f97316",
  other: "#64748b",
};

const SECTOR_LABELS: Record<string, string> = {
  layer1: "Layer 1", defi: "DeFi", exchange: "Exchange", payment: "Payment",
  gaming: "Gaming", privacy: "Privacy", storage: "Storage", other: "Other",
};""",
    """const SECTOR_COLORS: Record<string, string> = {
  "Layer 1": "#6366f1",
  "Layer 2": "#3b82f6",
  "DeFi": "#22c55e",
  "Infrastructure": "#f59e0b",
  "Gaming": "#a855f7",
  "Meme": "#ec4899",
  "Other": "#64748b",
};

const SECTOR_LABELS: Record<string, string> = {
  "Layer 1": "Layer 1",
  "Layer 2": "Layer 2",
  "DeFi": "DeFi",
  "Infrastructure": "Infrastructure",
  "Gaming": "Gaming",
  "Meme": "Meme",
  "Other": "Other",
};"""
)

# 3. Replace EDGE_STYLES
replace_fuzzy(
    """const EDGE_STYLES: Record<string, { color: string; opacity: number; widthMul: number }> = {
  correlation: { color: "#6366f1", opacity: 0.6, widthMul: 3 },
  sector:      { color: "#22c55e", opacity: 0.4, widthMul: 2 },
  market_cap:  { color: "#f59e0b", opacity: 0.4, widthMul: 2 },
};""",
    """const EDGE_STYLES: Record<string, { color: string; opacity: number; widthMul: number }> = {
  positive_correlation: { color: "#22c55e", opacity: 0.6, widthMul: 3 },
  negative_correlation: { color: "#ef4444", opacity: 0.6, widthMul: 3 },
};"""
)

# 4. Replace GraphPage component hook usage
replace_fuzzy(
    """export default function GraphPage() {
  const palette = useChartPalette();""",
    """export default function GraphPage() {
  const palette = useChartPalette();
  const { resolvedTheme } = useTheme();"""
)

# 5. Replace nodeCanvasObject
replace_fuzzy(
    """const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D) => {
    const r = node.radius || 7;
    const color = node.color || "#64748b";
    // Circle fill
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
    // White border
    ctx.strokeStyle = "rgba(255,255,255,0.8)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    // Label below
    ctx.font = "10px monospace";
    ctx.textAlign = "center";
    ctx.fillStyle = palette.text;
    ctx.fillText(node.symbol, node.x, node.y + r + 12);
  }, [palette.text]);""",
    """const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D) => {
    const r = node.radius || 7;
    const color = node.color || "#64748b";
    // Circle fill
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
    // Border (halo effect)
    ctx.strokeStyle = resolvedTheme === "dark" ? "#0b0d12" : "#f6f1e7";
    ctx.lineWidth = 2;
    ctx.stroke();
    // Label below
    ctx.font = "bold 9px monospace";
    ctx.textAlign = "center";
    ctx.fillStyle = palette.text;
    ctx.fillText(node.symbol, node.x, node.y + r + 12);
  }, [palette.text, resolvedTheme]);"""
)

# 6. Replace ForceGraph2D
replace_fuzzy(
    """<ForceGraph2D
            ref={graphRef}""",
    """<ForceGraph2D
            key={resolvedTheme || 'dark'}
            ref={graphRef}"""
)

# 7. Replace Legend connection types
replace_fuzzy(
    """{Object.entries({ correlation: "Price Correlation", sector: "Sector Relation", market_cap: "Size Equivalence" }).map(([key, label]) => (""",
    """{Object.entries({ positive_correlation: "Positive Correlation", negative_correlation: "Negative Correlation" }).map(([key, label]) => ("""
)

# Write final modified content back
with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Finished processing.")
