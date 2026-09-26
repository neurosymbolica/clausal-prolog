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
        tools/atom_export_predicate_census/census.py [--jobs N] [--json OUT] \\
        [--path IMPORT_DIR ...] ROOT...

``--path`` adds a directory to the import path without searching it for
files: the tree root when ROOT is one subdirectory whose modules import
each other by dotted paths from that root, or a directory of shared
library modules the files import.

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
extra = [p for p in os.environ.get("CENSUS_EXTRA_PATH", "").split(os.pathsep) if p]
sys.path[:0] = [os.path.dirname(path)] + roots
# AFTER everything else, PYTHONPATH included: an import-only directory must
# never shadow the engine under test.
sys.path.extend(extra)
out_extra = extra
stem = os.path.splitext(os.path.basename(path))[0]
out = {"path": path, "module": stem, "reached": False, "names": [],
       "error": None, "extra_path": out_extra}
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
        out["engine"] = cv2.__file__
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


def run_one(path, roots, timeout, extra_path=()):
    env = dict(os.environ)
    env["CENSUS_EXTRA_PATH"] = os.pathsep.join(extra_path)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD, path, *roots],
            capture_output=True, text=True, timeout=timeout,
            cwd=os.path.dirname(path) or ".", env=env)
    except subprocess.TimeoutExpired:
        return {"path": path, "reached": False, "names": [],
                "error": f"timeout after {timeout}s"}
    for line in proc.stdout.splitlines():
        if line.startswith("CENSUS-RESULT "):
            return json.loads(line[len("CENSUS-RESULT "):])
    return {"path": path, "reached": False, "names": [],
            "error": f"child exited {proc.returncode} with no result"}


def census(roots, jobs, timeout, extra_path=()):
    files = sorted(set(find_files(roots)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(
            lambda p: run_one(p, roots, timeout, extra_path), files))
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


def check_extra_path(paths):
    """Refuse an import-only directory that does not exist, or that holds a
    ``clausal`` package: the census must run the engine under test, and a
    second copy on the path is exactly the kind of fail-open that makes two
    trees report the same number.  Returns the absolute paths."""
    checked = []
    for p in paths:
        p = os.path.abspath(p)
        if not os.path.isdir(p):
            raise SystemExit(f"REFUSING: --path {p} does not exist")
        if os.path.exists(os.path.join(p, "clausal", "__init__.py")):
            raise SystemExit(
                f"REFUSING: --path {p} contains a `clausal` package, which "
                f"could shadow the engine under test")
        checked.append(p)
    return checked


def self_test(jobs, timeout):
    with tempfile.TemporaryDirectory() as d:
        roots, lib = os.path.join(d, "root"), os.path.join(d, "lib")
        os.makedirs(roots)
        os.makedirs(lib)
        # The must-warn module imports a helper that lives ONLY under the
        # --path directory, so it reaches the check only if --path reaches
        # the child (CENSUS_EXTRA_PATH).
        Path(lib, "aw_helper.clausal").write_text(
            "-module(aw_helper, [helper(X)])\nhelper(1),\n")
        Path(roots, "aw_warns.clausal").write_text(
            "-import_from(aw_helper, [helper])\n"
            "-module(aw_warns, [foo, kind(X)])\nfoo,\nkind(foo),\n")
        Path(roots, "aw_quiet.clausal").write_text(
            "-module(aw_quiet, [foo, kind(X)])\nkind(foo),\n")
        files, results = census([roots], jobs, timeout, [lib])
        hits = report(files, results)
        by_name = {os.path.basename(r["path"]): r for r in results}
        quiet = by_name.get("aw_quiet.clausal", {})
        warns = by_name.get("aw_warns.clausal", {})
        # And without --path the importing module must NOT reach the check.
        _, bare = census([roots], jobs, timeout)
        bare_warns = {os.path.basename(r["path"]): r for r in bare}.get(
            "aw_warns.clausal", {})
        # The children must run THIS tree's engine (the tool's own tree,
        # two levels up), not another copy on the path.
        tree = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        engine_ok = all(
            r.get("engine", "").startswith(tree + os.sep)
            for r in results if r.get("reached"))
        print(f"engine under test: {tree} (children agree: {engine_ok})")
        ok = (len(files) == 2 and all(r["reached"] for r in results)
              and len(hits) == 1 and hits[0]["names"] == ["foo"]
              and warns.get("extra_path") == [lib]
              and quiet.get("reached") and not quiet.get("names")
              and not bare_warns.get("reached") and engine_ok)
        print(f"--path control: with it reached={warns.get('reached')}, "
              f"without it reached={bare_warns.get('reached')}")
        print("SELF-TEST", "PASS" if ok else "FAIL")
        return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("roots", nargs="*")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--json", help="write per-file results here")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--path", action="append", default=[], metavar="DIR",
        help="an extra directory for imports only, NOT searched for files "
             "(repeatable) -- e.g. the tree root when ROOT is one "
             "subdirectory, or a directory of shared library modules")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.jobs, args.timeout)
    if not args.roots:
        parser.error("give at least one ROOT")
    roots = [os.path.abspath(r) for r in args.roots]
    extra = check_extra_path(args.path)
    files, results = census(roots, args.jobs, args.timeout, extra)
    if not files:
        print("REFUSING: no .clausal/.seam/.pl files found under the roots")
        return 2
    report(files, results)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
