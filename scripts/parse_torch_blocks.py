#!/usr/bin/env python3
"""Parse torch.md skip blocks to understand the structure."""
import re
from collections import Counter

with open("docs/torch.md") as f:
    lines = f.readlines()

blocks = []
current_h3 = ""
current_h2 = ""
i = 0
while i < len(lines):
    line = lines[i].rstrip()
    if line.startswith("## "):
        current_h2 = line[3:].strip()
    elif line.startswith("### "):
        current_h3 = line[4:].strip()
    elif line == "```clausal":
        if i + 1 < len(lines) and lines[i + 1].strip() == "# skip":
            content_lines = []
            j = i + 2
            while j < len(lines) and lines[j].rstrip() != "```":
                content_lines.append(lines[j].rstrip())
                j += 1
            blocks.append({
                "h2": current_h2,
                "h3": current_h3,
                "start_line": i + 1,
                "end_line": j + 1,
                "content": content_lines,
            })
            i = j
    i += 1

print(f"Total blocks: {len(blocks)}")
h3_counts = Counter(b["h3"] for b in blocks)
for h3, count in h3_counts.items():
    print(f"  {h3}: {count}")
