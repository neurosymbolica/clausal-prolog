"""Census: which modules does the import/local clash refusal hit?

The refusal (``compiler_v2._refuse_import_local_clashes``, ruling
2026-09-26, narrowed the same day) rejects a module that imports a predicate
indicator AND declares it locally where the local declaration would be
silently unreachable or ignored: any local procedure declaration (clauses,
-dynamic, -discontiguous, -table) against a DATA import, and a local
-dynamic against a STATIC procedure import (``compiler_v2._import_clash``,
which has the full table, including -shallow, -meta_predicate and -table).
The census calls the engine's own ``_import_local_clashes``: one copy of
the rule.
Clauses against a procedure import are the load gate's older refusal and
are not counted here.  This
loads every ``.clausal`` / ``.seam`` / ``.pl`` file under the given roots, each
in a FRESH subprocess, with the check patched into REPORT mode: it records
the clashes it would refuse and lets the load continue, so a file is still
counted if it fails later for an unrelated reason.

Usage::

    PYTHONPATH=<engine tree> <engine tree>/venv/bin/python \\
        tools/import_local_clash_census/census.py [--jobs N] [--json OUT] ROOT...

It prints the SIZE of every population: files found, files whose OWN module
reached the check (the denominator -- per module, not per subprocess, since
loading a file also loads what it imports), files hit, and files that never
reached it (not evaluated -- a load error before step 3e, or not a module).
``--self-test`` runs the controls: a generated DATA-import clash that must be
reported as a hit, and the allowed assert-through idiom (a local -dynamic of
an imported dynamic procedure) that must NOT be.

Each file is loaded under its stem as the module name, with its own
directory and every ROOT on ``sys.path`` so sibling ``-import_from``s
resolve.  A module that only loads under a dotted package name may show up
as "not evaluated"; the count says how many.
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
import json, os, sys
path, roots = sys.argv[1], sys.argv[2:]
sys.path[:0] = [os.path.dirname(path)] + roots
stem = os.path.splitext(os.path.basename(path))[0]
out = {"path": path, "module": stem, "reached": False, "clashes": [],
       "error": None}
try:
    import clausal.logic.compiler_v2 as cv2
    def report(module_items, predicate_nodes, module_name):
        # Per MODULE: loading the file under test also loads what it
        # imports, and an owner reaching the check says nothing about the
        # file itself.
        if module_name != stem:
            return
        out["reached"] = True
        for name, arity, declaration, text, owner, kind in \
                cv2._import_local_clashes(module_items, predicate_nodes):
            out["clashes"].append({"module": module_name,
                                   "indicator": f"{name}/{arity}",
                                   "local": declaration, "import": text,
                                   "kind": kind})
    cv2._refuse_import_local_clashes = report
    from clausal.import_hook import _load_module, _load_prolog_module
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
        return {"path": path, "reached": False, "clashes": [],
                "error": f"timeout after {timeout}s"}
    for line in proc.stdout.splitlines():
        if line.startswith("CENSUS-RESULT "):
            return json.loads(line[len("CENSUS-RESULT "):])
    return {"path": path, "reached": False, "clashes": [],
            "error": f"child exited {proc.returncode} with no result"}


def census(roots, jobs, timeout):
    files = sorted(set(find_files(roots)))
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        for result in pool.map(lambda p: run_one(p, roots, timeout), files):
            results.append(result)
    return files, results


def report(files, results, stream=sys.stdout):
    reached = [r for r in results if r["reached"]]
    hits = [r for r in results if r["clashes"]]
    print(f"files found:            {len(files)}", file=stream)
    print(f"reached the check:      {len(reached)}  (the denominator)", file=stream)
    print(f"not evaluated:          {len(results) - len(reached)}", file=stream)
    print(f"HIT (would be refused): {len(hits)}", file=stream)
    for r in hits:
        for c in r["clashes"]:
            print(f"  {r['path']}: {c['module']} {c['indicator']} "
                  f"local {c['local']} vs {c['import']} ({c['kind']})",
                  file=stream)
    return hits


def self_test(jobs, timeout):
    with tempfile.TemporaryDirectory() as d:
        Path(d, "cen_owner.clausal").write_text(
            "-module(cen_owner, [edge(A, B)])\n")
        Path(d, "cen_importer.clausal").write_text(
            "-import_from(cen_owner, [edge])\n-module(cen_importer, [z(X)])\n"
            "-dynamic(edge/2)\nz(1),\n")
        Path(d, "cen_dyn_owner.clausal").write_text(
            "-module(cen_dyn_owner, [link/2])\n-dynamic(link/2)\n")
        Path(d, "cen_idiom.clausal").write_text(
            "-import_from(cen_dyn_owner, [link])\n-module(cen_idiom, [z(X)])\n"
            "-dynamic(link/2)\nz(1),\n")
        files, results = census([d], jobs, timeout)
        hits = report(files, results)
        by_name = {os.path.basename(r["path"]): r for r in results}
        idiom = by_name.get("cen_idiom.clausal", {})
        # The negative control counts only if the idiom file ITSELF reached
        # the check (not just the owner it imports).
        ok = (len(files) == 4
              and all(r["reached"] for r in results)
              and idiom.get("reached") and not idiom.get("clashes")
              and len(hits) == 1
              and hits[0]["path"].endswith("cen_importer.clausal"))
        print(f"negative control cen_idiom.clausal: reached="
              f"{idiom.get('reached')} clashes={len(idiom.get('clashes', []))}")
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
