"""P0 of the PredicateMeta retirement: classify every reference by WHICH QUESTION it asks.

The spec's §4.4 warns that `isinstance(x, PredicateMeta)` sites are asking different
questions and must be separated before they can be rewritten -- the same
one-stem-two-questions confusion that produced `predicate.is_atom` ->
`is_zero_field_class` during THE FLIP. Reading the sites shows it is worse than two:

  A  PREDICATE TEST          "is this name a predicate here?"  -> a Database membership test
  B  TERM CONSTRUCTION       resolve name -> class -> CALL it  -> build a functor-first tuple
  C  ZERO-FIELD-CLASS TEST   `... and not term._fields`, the LEGACY ATOM shape -> should be
                             gone once atoms are tuples everywhere; that these sites exist
                             means THE FLIP did not fully eliminate zero-field classes
  D  DECLARATION             `metaclass=PredicateMeta` / `$PredicateMeta` in emitted AST
  E  IMPORT                  an import statement; follows whatever its users do
  ?  UNCLASSIFIED            must be read by a human

A site classified wrong is a SILENT behaviour change, so `?` is the honest default and the
exit criterion is zero `?`, not a high classification rate.
"""
from __future__ import annotations
import pathlib, re, sys, collections

ROOT = pathlib.Path("/workspace/clausal/clausal")
PAT = re.compile(r"PredicateMeta")


def classify(line: str) -> str:
    t = line.strip()
    if t.startswith("#") or t.startswith("*") or t.startswith("//"):
        return "COMMENT"
    if re.search(r"^\s*(from|import)\b.*PredicateMeta", t):
        return "E-import"
    if "metaclass=" in t or "$PredicateMeta" in t:
        return "D-declaration"
    if "_fields" in t and "PredicateMeta" in t:
        return "C-zerofield"
    if re.search(r"isinstance\(\s*(pred_cls|pred_obj|cls|mi_cls|owner)\s*,\s*PredicateMeta", t):
        return "A-predicate-test"
    if re.search(r"isinstance\(\s*(binding|resolved|target)\s*,\s*PredicateMeta", t):
        return "B-term-construction?"
    if re.search(r"isinstance\(.*PredicateMeta", t):
        return "?-isinstance"
    return "?"


def main() -> int:
    rows = []
    for p in sorted(ROOT.rglob("*")):
        if p.suffix not in (".py", ".c", ".h") or not p.is_file():
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if PAT.search(line):
                rows.append((str(p.relative_to(ROOT.parent)), n, classify(line), line.strip()[:88]))
    counts = collections.Counter(r[2] for r in rows)
    print(f"{len(rows)} references in {len({r[0] for r in rows})} files\n")
    for k, v in counts.most_common():
        print(f"  {v:4}  {k}")
    unresolved = [r for r in rows if r[2].startswith("?")]
    print(f"\n  UNCLASSIFIED (must be read): {len(unresolved)}")
    print(f"  EXIT CRITERION: 0 unclassified. Currently {len(unresolved)}.\n")
    by_file = collections.Counter(r[0] for r in unresolved)
    for f, c in by_file.most_common(10):
        print(f"    {c:3}  {f}")
    if "--sites" in sys.argv:
        print()
        for f, n, k, txt in unresolved:
            print(f"  {f}:{n}  [{k}]  {txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
