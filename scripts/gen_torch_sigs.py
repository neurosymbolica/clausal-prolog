#!/usr/bin/env python3
"""Generate torch_sigs.txt and updated torch.md from skip blocks."""
import re
from collections import defaultdict

with open("docs/torch.md") as f:
    lines = f.readlines()

# Parse blocks
blocks = []
current_h3 = ""
current_h2 = ""
i = 0
while i < len(lines):
    line = lines[i].rstrip()
    if line.startswith("## "):
        current_h2 = line[3:].strip()
        current_h3 = current_h2  # reset h3 to h2 name for blocks before first h3
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
                "start_line": i,       # 0-indexed, line of ```clausal
                "end_line": j,          # 0-indexed, line of closing ```
                "content": content_lines,
            })
            i = j
    i += 1

def h3_to_section(h3):
    """Convert h3 heading to snake_case section name."""
    # Handle comma-separated names
    h3 = h3.lower()
    h3 = re.sub(r'[,\s]+', '_', h3)
    h3 = re.sub(r'[^a-z0-9_]', '', h3)
    h3 = re.sub(r'_+', '_', h3)
    h3 = h3.strip('_')
    return h3

# Assign section names with _ex2/_ex3 for duplicates
h3_count = defaultdict(int)
for b in blocks:
    h3 = b["h3"]
    h3_count[h3] += 1
    occurrence = h3_count[h3]
    base = h3_to_section(h3)
    if not base:
        base = "import"  # the unnamed block at top
    if occurrence == 1:
        b["section"] = base
    else:
        b["section"] = f"{base}_ex{occurrence}"


# Generate sigs.txt
sigs_lines = []
current_section_h2 = ""
for b in blocks:
    if b["h2"] != current_section_h2:
        current_section_h2 = b["h2"]
        if sigs_lines:
            sigs_lines.append("")
        sigs_lines.append(f'# === {current_section_h2} ===')
        sigs_lines.append("")

    sigs_lines.append(f'--8<-- [start:{b["section"]}]')
    for cl in b["content"]:
        sigs_lines.append(cl)
    sigs_lines.append(f'--8<-- [end:{b["section"]}]')
    sigs_lines.append("")

with open("tests/fixtures/docs/torch_sigs.txt", "w") as f:
    f.write("\n".join(sigs_lines))

print(f"Wrote {len(sigs_lines)} lines to torch_sigs.txt")
print(f"Sections: {[b['section'] for b in blocks]}")

# Generate updated torch.md
new_lines = []
block_idx = 0
i = 0
while i < len(lines):
    if block_idx < len(blocks) and i == blocks[block_idx]["start_line"]:
        b = blocks[block_idx]
        # Replace ```clausal\n# skip\n...\n``` with ```clausal\n--8<--...\n```
        new_lines.append("```clausal\n")
        new_lines.append(f'--8<-- "tests/fixtures/docs/torch_sigs.txt:{b["section"]}"\n')
        new_lines.append("```\n")
        i = b["end_line"] + 1  # skip past closing ```
        block_idx += 1
    else:
        new_lines.append(lines[i])
        i += 1

with open("docs/torch.md", "w") as f:
    f.writelines(new_lines)

print(f"Updated torch.md ({len(new_lines)} lines)")
