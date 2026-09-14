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

# Files a human has READ END TO END and recorded a verdict for in FINDINGS.md.
# Their sites are excluded from the unread queue so the tool's number and the
# findings document cannot drift apart -- they did once, and the prose was
# ahead of the instrument.
HUMAN_VERIFIED = {
    "clausal/logic/specialization.py": "mechanical: name + arity + row only, 4 ctor sites",
    "clausal/logic/variables/_variables.c": "mechanical: already polymorphic over term reprs",
}



# ---------------------------------------------------------------------------
# HUMAN VERDICTS, file:line -> category. Every site the mechanical pass could
# not classify was READ. Recorded here so the exit criterion is machine-checked
# rather than asserted in prose -- the two drifted apart once already.
#
# G-term-test is the category the first taxonomy missed entirely:
# `isinstance(type(x), PredicateMeta)` asks "is x a TERM INSTANCE", which is a
# different question from `isinstance(x, PredicateMeta)` = "is x a predicate
# CLASS". Eight sites ask it, and the functor-first-tuple path already answers
# it natively.
VERDICTS = {
  # A -- PREDICATE TEST: "is this name a predicate here?" -> Database membership
  "clausal/import_diagnostics.py:201": "A", "clausal/logic/builtins/database_ops.py:275": "A",
  "clausal/logic/builtins/database_ops.py:280": "A", "clausal/logic/builtins/io.py:589": "A",
  "clausal/logic/builtins/io.py:735": "A", "clausal/logic/compiler/globals_env.py:550": "A",
  "clausal/logic/compiler_v2.py:276": "A", "clausal/logic/compiler_v2.py:678": "A",
  "clausal/logic/compiler_v2.py:745": "A", "clausal/logic/compiler_v2.py:1008": "A",
  "clausal/logic/compiler_v2.py:1022": "A", "clausal/logic/compiler_v2.py:1044": "A",
  "clausal/logic/compiler_v2.py:1717": "A", "clausal/logic/compiler_v2.py:1756": "A",
  "clausal/logic/database.py:974": "A", "clausal/logic/predicate.py:1425": "A",
  "clausal/logic/term_expansion.py:107": "A", "clausal/logic/term_expansion.py:160": "A",
  "clausal/predicate_diagnostics.py:194": "A", "clausal/testing.py:862": "A",
  "clausal/templating/term_rewriting.py:4236": "A",
  "clausal/templating/term_rewriting.py:4371": "A",
  "clausal/logic/compiler/head_match.py:846": "A",
  "clausal/logic/compiler/terms_to_ast.py:110": "A",
  "clausal/logic/compiler/terms_to_ast.py:1060": "A",
  "clausal/logic/compiler/terms_to_ast.py:1245": "A",
  "clausal/logic/compiler/arg_index.py:180": "A",
  "clausal/logic/compiler/arg_index.py:378": "A",
  "clausal/logic/compiler/_lower_goalop_shared.py:129": "A",
  "clausal/logic/builtins/inspection.py:317": "A",
  # G -- TERM TEST via isinstance(type(x), PredicateMeta) -> the tuple path answers it
  "clausal/logic/compiler/head_match.py:126": "G", "clausal/logic/solve.py:230": "G",
  "clausal/logic/solve.py:308": "G", "clausal/logic/solve.py:435": "G",
  "clausal/logic/solve.py:502": "G", "clausal/logic/solve.py:938": "G",
  "clausal/logic/term_expansion.py:44": "G", "clausal/logic/predicate.py:1481": "G",
  # C -- ATOM WIDENING: a zero-field class admitted as an atom VALUE
  "clausal/logic/builtins/inspection.py:384": "C",
  "clausal/logic/builtins/inspection.py:514": "C",
  "clausal/logic/builtins/type_checks.py:342": "C", "clausal/testing.py:1662": "C",
  # D -- DECLARATION / REGISTRATION: deleted with the class
  "clausal/logic/predicate.py:689": "D", "clausal/logic/predicate.py:1597": "D",
  "clausal/logic/predicate.py:1598": "D", "clausal/logic/predicate.py:1763": "D",
  "clausal/templating/term_rewriting.py:4218": "D",
  # H -- FOREIGN-IDENTITY DIAGNOSTIC: compares against ANOTHER copy of the engine's
  # PredicateMeta to detect a double-loaded engine. Depends on class object identity
  # ACROSS module copies, so it needs a replacement, not a deletion.
  "clausal/logic/predicate.py:1701": "H", "clausal/logic/predicate.py:1703": "H",
  # P -- PROSE: a docstring or comment that MENTIONS the name. Read and confirmed
  # non-behavioural. These reach here rather than the PROSE heuristic because they
  # contain code punctuation (backticks, parens, arrows) inside the prose.
  "clausal/logic/builtins/_registry.py:137": "P", "clausal/logic/builtins/chars.py:61": "P",
  "clausal/logic/builtins/control.py:43": "P", "clausal/logic/builtins/control.py:73": "P",
  "clausal/logic/builtins/io.py:549": "P", "clausal/logic/builtins/io.py:640": "P",
  "clausal/logic/builtins/io.py:689": "P", "clausal/logic/builtins/type_checks.py:107": "P",
  "clausal/logic/compiler/arg_index.py:104": "P",
  "clausal/logic/compiler/globals_env.py:112": "P",
  "clausal/logic/compiler/globals_env.py:524": "P",
  "clausal/logic/compiler/list_dispatch.py:444": "P",
  "clausal/logic/compiler/predicate.py:1709": "P",
  "clausal/logic/compiler/predicate.py:2167": "P",
  "clausal/logic/compiler/terms_to_ast.py:442": "P",
  "clausal/logic/compiler/terms_to_ast.py:470": "P",
  "clausal/logic/compiler_v2.py:818": "P", "clausal/logic/compiler_v2.py:958": "P",
  "clausal/logic/database.py:167": "P", "clausal/logic/database.py:959": "P",
  "clausal/logic/predicate.py:3": "P", "clausal/logic/predicate.py:1487": "P",
  "clausal/logic/predicate.py:1619": "P", "clausal/logic/solve.py:20": "P",
  "clausal/logic/solve.py:188": "P", "clausal/logic/solve.py:458": "P",
  "clausal/logic/solve.py:981": "P", "clausal/logic/solve.py:989": "P",
  "clausal/logic/solve.py:992": "P", "clausal/modules/py/datetime.py:124": "P",
  "clausal/repl.py:188": "P", "clausal/repl.py:194": "P",
  "clausal/testing.py:2153": "P", "clausal/templating/term_rewriting.py:4275": "P",
}


def classify(line: str) -> str:
    t = line.strip()
    if t.startswith("#") or t.startswith("*") or t.startswith("//") or t.startswith("/*"):
        return "COMMENT"
    # PROSE: a docstring or comment line that merely MENTIONS the name. Detected by
    # the absence of any code punctuation that could make it executable. Added after
    # a first pass left 195 sites "unclassified" of which most were docstring text --
    # the classifier only knew about `#` comments and docstring prose fell through.
    if not re.search(r"[=():\[\]]", t.replace("PredicateMeta", "")):
        return "PROSE"
    if re.search(r"``PredicateMeta``|`PredicateMeta`", t) and not re.search(
            r"isinstance|issubclass|metaclass=|:\s*PredicateMeta|->\s*PredicateMeta", t):
        return "PROSE"
    # ANNOTATION: a type position, not a behavioural use.
    if re.search(r":\s*[\"\']?PredicateMeta|->\s*[\"\']?PredicateMeta|"
                 r"dict\[[^\]]*PredicateMeta|PredicateMeta\s*\|\s*", t):
        return "F-annotation"
    # An import CONTINUATION line: bare names in a parenthesised import list.
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*(\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*\s*,?$", t):
        return "E-import"
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
    verified = [r for r in rows if r[0] in HUMAN_VERIFIED]
    unresolved = [r for r in rows
                  if r[2].startswith("?") and r[0] not in HUMAN_VERIFIED
                  and f"{r[0]}:{r[1]}" not in VERDICTS]
    from collections import Counter as _C
    vc = _C(VERDICTS.values())
    print("  HUMAN VERDICTS: " + ", ".join(f"{k}={v}" for k, v in sorted(vc.items())))
    print(f"\n  human-verified files : {len(HUMAN_VERIFIED)} "
          f"({len(verified)} sites, all verdicts in FINDINGS.md)")
    for f, verdict in HUMAN_VERIFIED.items():
        print(f"      {f} -- {verdict}")
    print(f"\n  STILL TO READ: {len(unresolved)}")
    print(f"  EXIT CRITERION: 0 still-to-read. Currently {len(unresolved)}.\n")
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
