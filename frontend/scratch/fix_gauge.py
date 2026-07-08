import os

file_path = r"g:\Programming\CryptoGraph_Analytics\frontend\app\sentiment\page.tsx"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace block
target = """        {/* Text */}
        <text x={cx} y={cy - 25} textAnchor="middle" fill="rgb(var(--text))" fontSize="44" fontWeight="900" className="font-mono tracking-tighter">
          {Math.round(value)}
        </text>
        <text x={cx} y={cy + 10} textAnchor="middle" fill={zoneColor} fontSize="14" fontWeight="bold" className="uppercase tracking-widest">
          {zoneLabel}
        </text>
      </svg>
    </div>"""

replacement = """      </svg>
      {/* Text Label Below SVG */}
      <div className="flex flex-col items-center -mt-6 relative z-20">
        <span className="text-5xl font-black text-text font-mono tracking-tighter">
          {Math.round(value)}
        </span>
        <span className="text-xs font-bold tracking-widest uppercase mt-1" style={{ color: zoneColor }}>
          {zoneLabel}
        </span>
      </div>
    </div>"""

# Try both CRLF and LF replacements
if target in content:
    content = content.replace(target, replacement)
    print("Replaced with LF format successfully.")
else:
    target_crlf = target.replace("\\n", "\\r\\n")
    # Let's try replacing with split lines
    content_lines = content.splitlines()
    target_lines = target.splitlines()
    
    # find where target lines match
    match_idx = -1
    for i in range(len(content_lines) - len(target_lines) + 1):
        match = True
        for j in range(len(target_lines)):
            if content_lines[i+j].strip() != target_lines[j].strip():
                match = False
                break
        if match:
            match_idx = i
            break
            
    if match_idx != -1:
        print(f"Found match at line {match_idx + 1}")
        # Build replacement lines with matching indentation
        indent = "      "
        replacement_lines = [
            "      </svg>",
            "      {/* Text Label Below SVG */}",
            "      <div className=\"flex flex-col items-center -mt-6 relative z-20\">",
            "        <span className=\"text-5xl font-black text-text font-mono tracking-tighter\">",
            "          {Math.round(value)}",
            "        </span>",
            "        <span className=\"text-xs font-bold tracking-widest uppercase mt-1\" style={{ color: zoneColor }}>",
            "          {zoneLabel}",
            "        </span>",
            "      </div>",
            "    </div>"
        ]
        content_lines[match_idx : match_idx + len(target_lines)] = replacement_lines
        content = "\\n".join(content_lines)
        print("Replaced with line matching successfully.")
    else:
        print("Could not find block.")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
