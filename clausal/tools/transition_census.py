"""The transition-construct census: a "count must not grow" ratchet.

Operator ruling D13 (2026-09-30): ``\\+`` (the seam's ``not``), once/1,
forall/2, memberchk/2, the ``findall(_, G, [])`` negation backdoor and
make_quantity/3 are ALLOWED where they already are and must not be added.
``if_/3`` is not one of them -- it is library(reif)'s pure conditional, the
replacement target -- and is not counted.

The census walks source roots, counts each construct's GOAL-position sites
per file with the loaders' own counters, and compares them with a committed
baseline (``transition_census_baseline.json`` beside this file):

* a seam file (``.seam`` / ``.clausal``) -- each ``head <- body`` clause
  statement, its body counted by
  :func:`clausal.logic.compiler.terms_to_goalop.count_transition_constructs`
  (the seam loader's counter; here without a module database, so a goal it
  cannot convert is reported as SKIPPED, never silently dropped);
* a ``.pl`` file -- the native front end's reader and its
  :class:`~clausal.tools.iso_l3_directives.Uses` counter, the one that fills
  ``l3_stats["transition_constructs"]``.

A count above the baseline, for any (file, construct), fails (exit 1).  A
count below it is reported; ``--update`` writes the new baseline.  The census
prints its SIZE (files scanned, constructs found); scanning nothing, or
finding nothing, is an error (exit 2) -- a ratchet over an empty population
passes vacuously.

Usage::

    python -m clausal.tools.transition_census            # check
    python -m clausal.tools.transition_census --update   # re-baseline
    python -m clausal.tools.transition_census --base B ROOT ...
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
import warnings
from pathlib import Path

from clausal._suffixes import CLAUSAL_SUFFIXES, PROLOG_SUFFIX

#: The repository root (``clausal/tools/`` -> two levels up).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOTS = ("clausal", "tests", "docs")
BASELINE = Path(__file__).with_name("transition_census_baseline.json")

_SKIP_DIRS = frozenset({"__pycache__", "__transformed__", "build", "site",
                        "venv", "node_modules"})


def _keys() -> tuple[str, ...]:
    from clausal.logic.compiler.terms_to_goalop import TRANSITION_KEYS  # noqa: PLC0415
    return TRANSITION_KEYS


# ── per-file counters ────────────────────────────────────────────────────────


def _seam_clause_bodies(source: str, filename: str) -> tuple[list, list]:
    """The bodies of a seam file's ``head <- body`` clause statements (and
    ``head >> body`` DCG rules), as
    the pythonic nodes the compiler's converter takes.  Arrow detection is
    the transformer's own (``<`` and ``-`` adjacent in the source)."""
    from clausal.pythonic_ast.conversion_from_python_ast import visit  # noqa: PLC0415
    from clausal.templating.term_rewriting import _detect_arrow  # noqa: PLC0415
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(source, filename=filename)
    lines = source.splitlines(keepends=True)
    bodies: list = []
    dcg: list = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.Expr):
            continue
        exprs = (stmt.value.elts if isinstance(stmt.value, ast.Tuple)
                 else [stmt.value])
        for e in exprs:
            if isinstance(e, ast.BinOp) and isinstance(e.op, ast.RShift):
                # A DCG rule ``head >> body``: the loader counts the clause
                # it translates to, whose goals are the body's ``not`` /
                # ``{...}`` goals (a nonterminal is not a construct).
                dcg.append(visit(e.right))
                continue
            if not isinstance(e, ast.Compare):
                continue
            try:
                arrow = _detect_arrow(e.left, e.ops, e.comparators, lines)
            except (SyntaxError, ValueError):
                continue    # the loader refuses it; nothing to count
            if arrow is not None:
                bodies.append(visit(arrow[1]))
    return bodies, dcg


def count_seam_file(path: Path) -> tuple[dict, int]:
    """-> (counts, skipped goals) for one seam file."""
    from clausal.logic.compiler.terms_to_goalop import (  # noqa: PLC0415
        count_transition_constructs)
    source = path.read_text(encoding="utf-8")
    skipped: list = []
    bodies, dcg = _seam_clause_bodies(source, str(path))
    counts = count_transition_constructs(bodies, skipped=skipped)
    # A DCG body's terminals and nonterminals are not goals the converter
    # takes: walk it for its constructs, without reporting them as skipped.
    count_transition_constructs(dcg, counts=counts)
    return counts, len(skipped)


def count_pl_file(path: Path) -> tuple[dict, int]:
    """-> (counts, unreadable items) for one ``.pl`` file: the native front
    end's reader and ``Uses`` counter, over every clause it reads."""
    from clausal.tools.iso_l3 import iter_iso  # noqa: PLC0415
    from clausal.tools.iso_l3_directives import Uses  # noqa: PLC0415
    source = path.read_text(encoding="utf-8")
    uses = Uses()
    unreadable = 0
    items, _table = iter_iso(source)
    for it in items:
        kind = type(it).__name__
        if kind == "Clause":
            uses.clause(it.term)
        elif kind == "SyntaxIssue":
            unreadable += 1
    return dict(uses.transition), unreadable


# ── the census ───────────────────────────────────────────────────────────────


def _source_files(roots, base: Path):
    seen = set()
    for root in roots:
        root = Path(root)
        if not root.is_absolute():
            root = base / root
        if root.is_file():
            cands = [root]
        else:
            cands = sorted(p for p in root.rglob("*") if p.is_file())
        for p in cands:
            rel = p.relative_to(base) if p.is_relative_to(base) else p
            if any(part in _SKIP_DIRS or part.startswith(".")
                   for part in rel.parts[:-1]):
                continue
            if p.suffix in CLAUSAL_SUFFIXES or p.suffix == PROLOG_SUFFIX:
                if p not in seen:
                    seen.add(p)
                    yield p, rel.as_posix()


def census(roots=DEFAULT_ROOTS, base: Path = REPO_ROOT) -> dict:
    """Count every source file under *roots* (relative to *base*).  ->
    ``{"files": {rel: {"surface", "counts", "skipped"}}, "errors": {rel:
    msg}, "scanned": {surface: n}}``."""
    files: dict = {}
    errors: dict = {}
    scanned = {"seam": 0, "pl": 0}
    for path, rel in _source_files(roots, base):
        surface = "pl" if path.suffix == PROLOG_SUFFIX else "seam"
        scanned[surface] += 1
        try:
            if surface == "pl":
                counts, skipped = count_pl_file(path)
            else:
                counts, skipped = count_seam_file(path)
        except Exception as e:  # noqa: BLE001 -- reported, never hidden
            errors[rel] = f"{type(e).__name__}: {e}".splitlines()[0][:200]
            continue
        files[rel] = {"surface": surface, "counts": counts,
                      "skipped": skipped}
    return {"files": files, "errors": errors, "scanned": scanned}


def totals(result: dict) -> dict:
    out = {s: dict.fromkeys(_keys(), 0) for s in ("seam", "pl")}
    for rec in result["files"].values():
        for k, n in rec["counts"].items():
            out[rec["surface"]][k] += n
    return out


def baseline_of(result: dict) -> dict:
    """The baseline document: per file, its NONZERO counts; plus totals."""
    return {
        "_comment": ("transition-construct census baseline (D13: allowed-"
                     "existing, no-new). Regenerate with `python -m "
                     "clausal.tools.transition_census --update`."),
        "totals": totals(result),
        "files": {rel: c for rel, c in sorted(
            (rel, _row(rec)) for rel, rec in result["files"].items()) if c},
    }


#: The baseline key of a file's goals/items the census could not count: it
#: is ratcheted like a construct, so a construct cannot hide in a goal the
#: converter refuses or a ``.pl`` item the reader cannot read.
UNREADABLE = "unreadable"


def _row(rec: dict) -> dict:
    """A file's NONZERO counts, its unreadable goals/items included."""
    row = {k: n for k, n in rec["counts"].items() if n}
    if rec["skipped"]:
        row[UNREADABLE] = rec["skipped"]
    return row


def compare(result: dict, baseline: dict) -> tuple[list, list]:
    """-> (grown, shrunk): ``(file, key, baseline, now)`` per changed count."""
    grown, shrunk = [], []
    base_files = baseline.get("files", {})
    now_files = {rel: _row(rec) for rel, rec in result["files"].items()}
    for rel in sorted(set(base_files) | set(now_files)):
        was = base_files.get(rel, {})
        now = now_files.get(rel, {})
        for k in (*_keys(), UNREADABLE):
            a, b = was.get(k, 0), now.get(k, 0)
            if b > a:
                grown.append((rel, k, a, b))
            elif b < a:
                shrunk.append((rel, k, a, b))
    return grown, shrunk


def report(result: dict, out=sys.stdout, per_file: bool = True) -> int:
    """Print the census; -> constructs found (all surfaces)."""
    keys = _keys()
    if per_file:
        for rel, rec in sorted(result["files"].items()):
            if any(rec["counts"].values()):
                print(f"{rel}: " + ", ".join(
                    f"{k} {n}" for k, n in rec["counts"].items() if n),
                    file=out)
    tot = totals(result)
    found = 0
    for surface in ("seam", "pl"):
        n = sum(tot[surface].values())
        found += n
        print(f"TOTAL {surface}: {result['scanned'][surface]} files, "
              f"{n} constructs (" + ", ".join(
                  f"{k} {tot[surface][k]}" for k in keys) + ")", file=out)
    skipped = {s: sum(r["skipped"] for r in result["files"].values()
                      if r["surface"] == s) for s in ("seam", "pl")}
    print(f"SIZE: {sum(result['scanned'].values())} files scanned, "
          f"{found} constructs found; not counted: {skipped['seam']} seam "
          f"goals the converter refuses, {skipped['pl']} .pl items the "
          f"reader cannot read (an op/3 or library operator the census "
          f"does not load), {len(result['errors'])} whole files",
          file=out)
    for rel, msg in sorted(result["errors"].items()):
        print(f"  not counted: {rel}: {msg}", file=out)
    return found


def check(roots=DEFAULT_ROOTS, base: Path = REPO_ROOT,
          baseline_path: Path = BASELINE, *, update: bool = False,
          per_file: bool = True, out=sys.stdout) -> int:
    """Run the census and the ratchet; -> exit status (0 ok, 1 a count
    grew or a file could not be counted at all, 2 an empty census or a
    missing baseline)."""
    result = census(roots, base)
    found = report(result, out, per_file=per_file)
    if result["errors"] and not update:
        # A file the census cannot read at all would otherwise read as
        # "shrank to zero" -- and pass.
        print(f"FAIL: {len(result['errors'])} file(s) could not be counted "
              "(listed above)", file=out)
        return 1
    if not sum(result["scanned"].values()) or not found:
        print("ERROR: the census is EMPTY (N=0): a ratchet over nothing "
              "passes vacuously", file=out)
        return 2
    if update:
        baseline_path.write_text(
            json.dumps(baseline_of(result), indent=1, sort_keys=False) + "\n",
            encoding="utf-8")
        print(f"baseline written: {baseline_path}", file=out)
        return 1 if result["errors"] else 0
    if not baseline_path.exists():
        print(f"ERROR: no baseline at {baseline_path} (run --update)",
              file=out)
        return 2
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    grown, shrunk = compare(result, baseline)
    for rel, k, a, b in shrunk:
        print(f"shrank: {rel}: {k} {a} -> {b} (lock it in: --update)",
              file=out)
    for rel, k, a, b in grown:
        print(f"GREW: {rel}: {k} {a} -> {b}", file=out)
    if grown:
        print(f"FAIL: {len(grown)} transition-construct count(s) grew; "
              "D13 is allowed-existing, no-new (rewrite with if_/3 and "
              "reified tests, or re-baseline with --update if the growth "
              "is a move, not a new site)", file=out)
        return 1
    print("OK: no transition-construct count grew", file=out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m clausal.tools.transition_census",
        description=__doc__.split("\n\n")[0])
    ap.add_argument("roots", nargs="*", default=list(DEFAULT_ROOTS),
                    help="files/directories to scan (default: %(default)s, "
                         "relative to --base)")
    ap.add_argument("--base", type=Path, default=REPO_ROOT,
                    help="the directory paths are keyed relative to")
    ap.add_argument("--baseline", type=Path, default=BASELINE)
    ap.add_argument("--update", action="store_true",
                    help="write the baseline instead of checking it")
    ap.add_argument("--totals-only", action="store_true",
                    help="omit the per-file lines")
    a = ap.parse_args(argv)
    return check(a.roots, a.base.resolve(), a.baseline, update=a.update,
                 per_file=not a.totals_only)


if __name__ == "__main__":
    sys.exit(main())
