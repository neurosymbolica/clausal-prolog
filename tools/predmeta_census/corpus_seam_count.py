"""How the corpus actually invokes predicates, counted on the real population."""
import re, subprocess, pathlib
ROOT = pathlib.Path("/workspace/clausify-domains")
def ls(pat):
    return subprocess.run(["git","-C",str(ROOT),"ls-files",pat],
                          capture_output=True,text=True).stdout.split()
seam = ls("*.seam"); cla = ls("*.clausal"); py = ls("*.py")
print(f"populations: .seam {len(seam)}   .clausal {len(cla)}   .py {len(py)}")

def scan(files, pats):
    out = {k: [0,set()] for k in pats}
    read = 0
    for rel in files:
        try: t = (ROOT/rel).read_text(errors="replace")
        except OSError: continue
        read += 1
        for k, p in pats.items():
            n = len(p.findall(t))
            if n: out[k][0] += n; out[k][1].add(rel)
    return read, out

# the `--` GOAL/TERM seam: `--name(` with the two dashes ADJACENT (that adjacency
# IS the operator -- `a < --b` and `a <- -b` parse identically otherwise).
pats = {
  "--pred(...)   the seam":            re.compile(r'--[a-z_]\w*\('),
  "++escape      python back in":      re.compile(r'\+\+[A-Za-z_]\w*'),
  "if --goal:    goal position":       re.compile(r'\bif\s+(?:not\s+)?--[a-z_]\w*\('),
  "for x in --goal:":                  re.compile(r'\bfor\s+[^\n]{1,60}\s+in\s+--[a-z_]\w*\('),
}
read, res = scan(seam, pats)
print(f"\n=== .seam harnesses ({read} read) ===")
for k, (n, fs) in res.items():
    print(f"  {k:36} {n:5} occurrences in {len(fs):3} files")

pats2 = {"test(...)  in-language tests": re.compile(r'^test\(', re.M)}
read2, res2 = scan(cla, pats2)
print(f"\n=== .clausal rulebases ({read2} read) ===")
for k, (n, fs) in res2.items():
    print(f"  {k:36} {n:5} occurrences in {len(fs):3} files")

print("\n-- control --")
_, ctl = scan(seam, {"must be zero": re.compile(r'ZZZ_NOPE_ZZZ'),
                     "must be many": re.compile(r'\w+')})
print(f"  zero-pattern: {ctl['must be zero'][0]}   many-pattern: {ctl['must be many'][0]:,}")
