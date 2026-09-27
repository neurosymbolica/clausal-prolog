"""Census: where does Python code still use ``Compound`` / ``KWTerm``?

Both classes are being retired before 1.0 (the cell ``('f', 1, 2)`` is the
term).  This tool counts, by AST, for each class:

* ``construct``  -- a call ``Compound(...)`` / ``T.Compound(...)`` / an alias;
* ``isinstance`` -- ``isinstance``/``issubclass`` naming it (also in a tuple);
* ``type_is``    -- ``type(x) is Compound`` and the ``==``/``!=``/``is not`` forms;
* ``match``      -- a ``case Compound(...)`` class pattern;
* ``subclass``   -- a class statement with it as a base;
* ``import``     -- ``from ... import Compound [as X]``;
* ``refs``       -- every reference to the name (or an alias), any position.

A name counts when it is spelled ``Compound``/``KWTerm``, is an alias bound
by ``from ... import Compound as X``, or is an attribute ``m.Compound``.
Nothing else is resolved: ``PCompound`` (the Prolog reader's AST class) and a
local variable ``compound`` are different names and never count.

REPORT-ONLY.  It reads each file and calls ``ast.parse``; it never imports or
executes a scanned file.  It prints the SIZE of every population (files
found, parsed, unparsed, files that hit) so an empty result can be told from
a scan that saw nothing.  ``--self-test`` runs a positive fixture with exact
expected counts and a negative fixture that must count zero::

    python tools/compound_census/census.py --self-test
    python tools/compound_census/census.py [--sites] [--per-file N] ROOT...

Exit status: 0 on a clean scan, 1 if any file failed to parse, 2 on a failed
self-test.  The run-time half (constructions actually executed during a
pytest run) is ``compound_census_plugin.py`` next to this file.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

CLASSES = ("Compound", "KWTerm")
KINDS = ("refs", "import", "construct", "isinstance", "type_is", "match",
         "subclass")
SUFFIXES = (".py",)
SKIP_DIRS = {"venv", ".venv", "build", "dist", ".git", "__pycache__",
             "node_modules", "site-packages", ".tox", ".mypy_cache"}


def _names(tree: ast.AST) -> dict[str, str]:
    """Map every local name that denotes a tracked class to that class."""
    names = {c: c for c in CLASSES}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                if a.name in CLASSES:
                    names[a.asname or a.name] = a.name
    return names


def _cls(node: ast.AST, names: dict[str, str]) -> str | None:
    """The tracked class *node* denotes, or None."""
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.Attribute) and node.attr in CLASSES:
        return node.attr
    return None


def scan_source(src: str, filename: str = "<src>"):
    """Return ``(counts, sites)`` for one source text, or None if it does not
    parse.  *counts* is a Counter keyed ``(class, kind)``; *sites* lists
    ``(class, lineno)`` for each construction."""
    try:
        tree = ast.parse(src, filename=filename)
    except (SyntaxError, ValueError):
        return None
    names = _names(tree)
    c: Counter = Counter()
    sites: list[tuple[str, int]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                if a.name in CLASSES:
                    c[a.name, "import"] += 1
        elif isinstance(n, ast.Call):
            k = _cls(n.func, names)
            if k:
                c[k, "construct"] += 1
                sites.append((k, n.lineno))
            elif (isinstance(n.func, ast.Name)
                  and n.func.id in ("isinstance", "issubclass")
                  and len(n.args) == 2):
                t = n.args[1]
                for e in (t.elts if isinstance(t, ast.Tuple) else [t]):
                    k = _cls(e, names)
                    if k:
                        c[k, "isinstance"] += 1
        elif isinstance(n, ast.Compare):
            if any(isinstance(o, (ast.Is, ast.IsNot, ast.Eq, ast.NotEq))
                   for o in n.ops):
                for x in [n.left, *n.comparators]:
                    k = _cls(x, names)
                    if k:
                        c[k, "type_is"] += 1
        elif isinstance(n, ast.MatchClass):
            k = _cls(n.cls, names)
            if k:
                c[k, "match"] += 1
        elif isinstance(n, ast.ClassDef):
            for b in n.bases:
                k = _cls(b, names)
                if k:
                    c[k, "subclass"] += 1
        # every reference, any position
        k = None
        if isinstance(n, ast.Name) and n.id in names:
            k = names[n.id]
        elif isinstance(n, ast.Attribute) and n.attr in CLASSES:
            k = n.attr
        if k:
            c[k, "refs"] += 1
    return c, sites


def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)
        for f in sorted(fn):
            if f.endswith(SUFFIXES):
                yield Path(dp) / f


def census(roots):
    """Scan *roots*; return a result dict with every population's size."""
    total: Counter = Counter()
    per_file: list[tuple[int, str, Counter]] = []
    sites: list[tuple[str, str, int]] = []
    found = parsed = 0
    unparsed: list[str] = []
    for root in roots:
        for p in iter_files(Path(root)):
            found += 1
            r = scan_source(p.read_text(encoding="utf-8", errors="replace"),
                            str(p))
            if r is None:
                unparsed.append(str(p))
                continue
            parsed += 1
            c, s = r
            if c:
                total.update(c)
                per_file.append((sum(c[k, "refs"] for k in CLASSES), str(p), c))
                sites.extend((k, str(p), ln) for k, ln in s)
    return {"found": found, "parsed": parsed, "unparsed": unparsed,
            "counts": total, "per_file": per_file, "sites": sites}


def report(res, *, show_sites=False, per_file=0, out=sys.stdout) -> None:
    w = out.write
    w(f"files found {res['found']}, parsed {res['parsed']}, "
      f"unparsed {len(res['unparsed'])}\n")
    for p in res["unparsed"]:
        w(f"  UNPARSED {p}\n")
    for k in CLASSES:
        hit = sum(1 for _, _, c in res["per_file"] if c[k, "refs"])
        w(f"{k}: files hit {hit}/{res['parsed']}  "
          + "  ".join(f"{kind} {res['counts'][k, kind]}" for kind in KINDS)
          + "\n")
    if per_file:
        for n, p, c in sorted(res["per_file"], key=lambda x: (-x[0], x[1]))[:per_file]:
            w(f"  {n:5d} {p}  " + " ".join(
                f"{k}.{kind}={c[k, kind]}" for k in CLASSES
                for kind in ("construct", "isinstance") if c[k, kind]) + "\n")
    if show_sites:
        for k, p, ln in res["sites"]:
            w(f"  SITE {k} {p}:{ln}\n")


# ── self-test ────────────────────────────────────────────────────────────────

_POSITIVE = '''
from clausal.terms import Compound, KWTerm
from clausal.terms import Compound as C
import clausal.terms as T
a = Compound("f", (1,))
b = C("g", ())
c = T.Compound("h", (2,))
d = KWTerm("r", x=1)
isinstance(a, Compound)
isinstance(a, (int, C, T.KWTerm))
type(a) is Compound
class Sub(Compound):
    pass
match a:
    case Compound(functor="f"):
        pass
'''
#: exact (class, kind) -> count for _POSITIVE
_POSITIVE_EXPECT = {
    ("Compound", "import"): 2, ("KWTerm", "import"): 1,
    ("Compound", "construct"): 3, ("KWTerm", "construct"): 1,
    ("Compound", "isinstance"): 2, ("KWTerm", "isinstance"): 1,
    ("Compound", "type_is"): 1, ("Compound", "match"): 1,
    ("Compound", "subclass"): 1,
    ("Compound", "refs"): 8, ("KWTerm", "refs"): 2,
}
_NEGATIVE = '''
from clausal.tools.prolog_ast import PCompound
compound = PCompound("f", [])
s = "Compound(functor='f', args=())"
def kwterm(x):
    return x
kwterm(compound)
# Compound("in a comment")
'''


def self_test(out=sys.stdout) -> bool:
    ok = True
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pos.py").write_text(_POSITIVE)
        (Path(d) / "neg.py").write_text(_NEGATIVE)
        (Path(d) / "broken.py").write_text("def (:\n")
        pos = census([Path(d) / "pos.py"])
        neg = census([Path(d) / "neg.py"])
        bad = census([Path(d) / "broken.py"])
    got = {k: v for k, v in pos["counts"].items() if v}
    if pos["parsed"] != 1 or got != _POSITIVE_EXPECT:
        out.write(f"SELF-TEST FAIL positive: parsed={pos['parsed']} got={got} "
                  f"expected={_POSITIVE_EXPECT}\n")
        ok = False
    if neg["parsed"] != 1 or sum(neg["counts"].values()) != 0:
        out.write(f"SELF-TEST FAIL negative: parsed={neg['parsed']} "
                  f"got={dict(neg['counts'])}\n")
        ok = False
    if bad["found"] != 1 or len(bad["unparsed"]) != 1:
        out.write(f"SELF-TEST FAIL unparsed file not reported: {bad}\n")
        ok = False
    n = sum(_POSITIVE_EXPECT.values())
    out.write(f"self-test {'PASS' if ok else 'FAIL'}: positive fixture "
              f"{n} expected hits over {len(_POSITIVE_EXPECT)} (class, kind) "
              f"cells; negative fixture must be 0\n")
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("roots", nargs="*")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--sites", action="store_true",
                    help="list every construction site")
    ap.add_argument("--per-file", type=int, default=0, metavar="N",
                    help="list the N files with the most references")
    a = ap.parse_args(argv)
    if a.self_test:
        return 0 if self_test() else 2
    if not a.roots:
        ap.error("give at least one ROOT, or --self-test")
    res = census(a.roots)
    report(res, show_sites=a.sites, per_file=a.per_file)
    return 1 if res["unparsed"] else 0


if __name__ == "__main__":
    sys.exit(main())
