"""Two corpus numbers the representation change is waiting on.

A. OBJECT-SHAPED predicate access -- does corpus Python reach a predicate as a
   module ATTRIBUTE (which spec §4 q3 removes), or by NAME (which survives)?
B. TUPLE-DATA -- does corpus code spell the tuple tag or match on it? If not, a
   re-tagging is compiler-internal and costs the corpus nothing.

Every count prints the size of what it matched. Controls at the bottom: a
pattern that must match nothing, and a pattern that must match something.
"""
import re, subprocess, collections, pathlib, sys

ROOT = pathlib.Path("/workspace/clausify-domains")
files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.py"],
                       capture_output=True, text=True).stdout.split()
print(f"corpus .py files tracked: {len(files)}")
texts = {}
for rel in files:
    try:
        texts[rel] = (ROOT / rel).read_text(errors="replace")
    except OSError:
        pass
print(f"files read: {len(texts)}   total bytes: {sum(len(t) for t in texts.values()):,}")

def count(label, pattern, flags=0):
    pat = re.compile(pattern, flags)
    hits, fs = 0, set()
    for rel, t in texts.items():
        n = len(pat.findall(t))
        if n:
            hits += n; fs.add(rel)
    return label, hits, len(fs)

print("\n=== A. how corpus Python reaches a predicate ===")
NAME_SHAPES = [
    ('call("name", ...)            NAME', r'\bcall\(\s*["\'][a-z_]\w*["\']'),
    ('load_clausal_module(...)     NAME', r'\bload_clausal_module\('),
    ('db/row/is_dynamic(f, n)      NAME', r'\b(?:row|is_dynamic|is_tabled|clauses_for)\(\s*["\'][a-z_]\w*["\']\s*,\s*\d'),
]
OBJ_SHAPES = [
    ('getattr(mod, "pred")         OBJ ', r'getattr\(\s*\w+\s*,\s*["\'][a-z_]\w*["\']'),
    ('call(mod.pred, ...)          OBJ ', r'\bcall\(\s*\w+\.\w+\s*[,)]'),
    ('module_dict["pred"]          OBJ ', r'(?:module_dict|md|ns)\[\s*["\'][a-z_]\w*["\']\s*\]'),
]
tot_name = tot_obj = 0
for label, pat in NAME_SHAPES:
    l, h, f = count(label, pat); tot_name += h
    print(f"  {l}  {h:5} occurrences in {f:3} files")
for label, pat in OBJ_SHAPES:
    l, h, f = count(label, pat); tot_obj += h
    print(f"  {l}  {h:5} occurrences in {f:3} files")
print(f"\n  NAME-shaped total : {tot_name}")
print(f"  OBJECT-shaped total: {tot_obj}")

print("\n=== B. does corpus code touch the tuple-DATA tag at all? ===")
for label, pat in [
    ("TUPLE_TAG by name          ", r'\bTUPLE_TAG\b'),
    ("$cells namespace           ", r'\$cells'),
    ("is_cell / compound_cell    ", r'\b(?:is_cell|compound_cell_shape)\b'),
    ("matching slot 0 on a type  ", r'\[0\]\s+is\s+tuple|is\s+TUPLE_TAG'),
]:
    l, h, f = count(label, pat)
    print(f"  {l}  {h:5} occurrences in {f:3} files")

print("\n-- controls --")
_, h_never, _ = count("x", r'ZZZ_THIS_CANNOT_APPEAR_ZZZ')
print(f"  a pattern that must match NOTHING : {h_never}  ({'ok' if h_never == 0 else 'BROKEN'})")
_, h_always, f_always = count("x", r'\bimport\b')
print(f"  a pattern that must match PLENTY  : {h_always} in {f_always} files  "
      f"({'ok' if h_always > 100 else 'BROKEN -- the corpus is not being read'})")
