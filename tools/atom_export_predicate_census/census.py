"""Census: which modules does the atom-export / name/0 warning fire for?

``ClausalAtomExportDefinedAsPredicateWarning`` (operator ruling 2026-09-26)
fires at load when a module exports a bare name as an ATOM
(``-module(m, [..., foo, ...])``) and also defines the predicate ``foo/0``.
This loads every ``.clausal`` / ``.seam`` / ``.pl`` file under the given
roots, each in a FRESH subprocess (the warning runs in ``compile_module``,
so a cached bytecode load still reaches it), and records the warning for
the module under test only -- loading a file also loads what it imports.

Usage::

    PYTHONPATH=<engine tree> <engine tree>/venv/bin/python \\
        tools/atom_export_predicate_census/census.py [--jobs N] [--json OUT] ROOT...

It prints the SIZE of every population: files found, files whose own module
reached the check (the denominator), files not evaluated (a load error
before the check, or not a module), and the modules that warn, with each
name.  ``--self-test`` runs the controls: a module that must warn and one
that must not, both of which must reach the check.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SUFFIXES = (".clausal", ".seam", ".pl")
SKIP_DIRS = {"venv", ".venv", "build", "dist", ".git", "__pycache__",
             "node_modules", "site-packages"}

_CHILD = r'''
import json, os, sys, warnings
path, roots = sys.argv[1], sys.argv[2:]
sys.path[:0] = [os.path.dirname(path)] + roots
stem = os.path.splitext(os.path.basename(path))[0]
out = {"path": path, "module": stem, "reached": False, "names": [],
       "error": None}
try:
    import clausal.logic.compiler_v2 as cv2
    from clausal.lint_warnings import ClausalAtomExportDefinedAsPredicateWarning as W
    real = cv2._warn_atom_exports_defined_as_predicates
    def spy(module_items, predicate_nodes, module_name):
        if module_name != stem:
            return real(module_items, predicate_nodes, module_name)
        out["reached"] = True
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            real(module_items, predicate_nodes, module_name)
        out["names"] = [str(w.message).split("`")[1] for w in caught
                        if issubclass(w.category, W)]
    cv2._warn_atom_exports_defined_as_predicates = spy
    from clausal.import_hook import _load_module, _load_prolog_module
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if path.endswith(".pl"):
            _load_prolog_module(stem, path)
        else:
            _load_module(stem, path)
except BaseException as exc:  # noqa: BLE001 -- recorded, never fatal
    msg = str(exc).splitlines()[0][:200] if str(exc) else ""
    out["error"] = f"{type(exc).__name__}: {msg}"
print("CENSUS-RESULT " + json.dumps(out))
'''


def find_files(roots):
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in sorted(filenames):
                if name.endswith(SUFFIXES):
                    yield os.path.join(dirpath, name)


def run_one(path, roots, timeout):
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD, path, *roots],
            capture_output=True, text=True, timeout=timeout,
            cwd=os.path.dirname(path) or ".")
    except subprocess.TimeoutExpired:
        return {"path": path, "reached": False, "names": [],
                "error": f"timeout after {timeout}s"}
    for line in proc.stdout.splitlines():
        if line.startswith("CENSUS-RESULT "):
            return json.loads(line[len("CENSUS-RESULT "):])
    return {"path": path, "reached": False, "names": [],
            "error": f"child exited {proc.returncode} with no result"}


def census(roots, jobs, timeout):
    files = sorted(set(find_files(roots)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(lambda p: run_one(p, roots, timeout), files))
    return files, results


def report(files, results, stream=sys.stdout):
    reached = [r for r in results if r["reached"]]
    hits = [r for r in results if r["names"]]
    print(f"files found:            {len(files)}", file=stream)
    print(f"reached the check:      {len(reached)}  (the denominator)", file=stream)
    print(f"not evaluated:          {len(results) - len(reached)}", file=stream)
    print(f"WARNING modules:        {len(hits)}", file=stream)
    for r in hits:
        print(f"  {r['path']}: {', '.join(r['names'])}", file=stream)
    return hits


def self_test(jobs, timeout):
    with tempfile.TemporaryDirectory() as d:
        Path(d, "aw_warns.clausal").write_text(
            "-module(aw_warns, [foo, kind(X)])\nfoo,\nkind(foo),\n")
        Path(d, "aw_quiet.clausal").write_text(
            "-module(aw_quiet, [foo, kind(X)])\nkind(foo),\n")
        files, results = census([d], jobs, timeout)
        hits = report(files, results)
        by_name = {os.path.basename(r["path"]): r for r in results}
        quiet = by_name.get("aw_quiet.clausal", {})
        ok = (len(files) == 2 and all(r["reached"] for r in results)
              and len(hits) == 1 and hits[0]["names"] == ["foo"]
              and hits[0]["path"].endswith("aw_warns.clausal")
              and quiet.get("reached") and not quiet.get("names"))
        print("SELF-TEST", "PASS" if ok else "FAIL")
        return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("roots", nargs="*")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--json", help="write per-file results here")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.jobs, args.timeout)
    if not args.roots:
        parser.error("give at least one ROOT")
    roots = [os.path.abspath(r) for r in args.roots]
    files, results = census(roots, args.jobs, args.timeout)
    if not files:
        print("REFUSING: no .clausal/.seam/.pl files found under the roots")
        return 2
    report(files, results)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
