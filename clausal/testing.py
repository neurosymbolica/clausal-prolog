"""clausal.testing — test runner for .clausal predicate modules.

Discovers test/1 clauses in .clausal files and runs them. Each test clause
is a rule of the form:

    test("description") <- goal1, goal2, ...

A test passes if its body succeeds (produces at least one solution).

Standalone usage
----------------
    python -m clausal.testing clausal/examples/
    python -m clausal.testing clausal/examples/fibonacci.clausal

Pytest integration
------------------
The conftest.py plugin (see conftest.py at project root) uses this module
to collect and run .clausal tests as individual pytest items.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class TestResult:
    name: str
    passed: bool
    error: Exception | None = None
    duration: float = 0.0


@dataclass
class FileResults:
    path: str
    results: list[TestResult] = field(default_factory=list)


def load_clausal_module(path: str | Path) -> object:
    """Load a .clausal file as a Python module and return it."""
    # Ensure import hook is installed.
    import clausal.import_hook  # noqa: F401

    from clausal.import_hook import _load_module

    path = str(path)
    mod_name = f"_clausal_test_{os.path.basename(path).removesuffix('.clausal')}"

    # _load_module handles sys.modules eviction internally.
    old = sys.modules.get(mod_name)
    try:
        mod = _load_module(mod_name, path)
    finally:
        # Avoid polluting sys.modules across test runs.
        if old is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = old
    return mod


def collect_tests(mod: object) -> list[str]:
    """Return the list of test/1 clause descriptions from a loaded module."""
    logic_module = mod.__dict__.get("$module")
    if logic_module is None:
        return []
    clauses = logic_module.db.clauses_for("Test", 1)
    descriptions = []
    for clause in clauses:
        head = clause.head
        # Head is a PredicateMeta instance or Compound with 1 arg (the description).
        if hasattr(head, "args"):
            desc = head.args[0]
        else:
            from clausal.logic.predicate import term_field_names
            names = term_field_names(head)
            desc = getattr(head, names[0]) if names else str(head)
        # Description might be a string or a ground value.
        descriptions.append(str(desc))
    return descriptions


def run_test(mod: object, description: str) -> TestResult:
    """Run a single test/1 clause by description. Returns a TestResult."""
    from clausal.logic.solve import call

    logic_module = mod.__dict__["$module"]
    t0 = time.perf_counter()
    try:
        solutions = list(call("Test", description, module=logic_module))
        passed = len(solutions) > 0
        return TestResult(name=description, passed=passed,
                          duration=time.perf_counter() - t0)
    except Exception as e:
        return TestResult(name=description, passed=False, error=e,
                          duration=time.perf_counter() - t0)


def run_file(path: str | Path) -> FileResults:
    """Load a .clausal file and run all its test/1 clauses."""
    path = str(path)
    results = FileResults(path=path)
    try:
        mod = load_clausal_module(path)
    except Exception as e:
        results.results.append(TestResult(name="<load>", passed=False, error=e))
        return results
    for desc in collect_tests(mod):
        results.results.append(run_test(mod, desc))
    return results


def discover_clausal_files(roots: list[str | Path]) -> Iterator[Path]:
    """Yield all .clausal files under the given roots."""
    for root in roots:
        root = Path(root)
        if root.is_file() and root.suffix == ".clausal":
            yield root
        elif root.is_dir():
            yield from sorted(root.rglob("*.clausal"))


# ── CLI ───────────────────────────────────────────────────────────────────────


def main(args: list[str] | None = None) -> int:
    """Run .clausal tests from the command line. Returns exit code."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run test/1 clauses in .clausal files",
    )
    parser.add_argument("paths", nargs="+", help=".clausal files or directories")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show individual test results")
    parser.add_argument("--strict", "--fail-on-empty", dest="strict",
                        action="store_true",
                        help="Exit non-zero when no Test(...) clauses are collected")
    parsed = parser.parse_args(args)

    # Validate paths up front so a mistyped path or wrong cwd is an error, not a
    # silently-green run.  A non-existent path, or a file that exists but is not a
    # .clausal/.pl file, is reported and forces a non-zero exit.
    bad_paths: list[str] = []
    for path in parsed.paths:
        p = Path(path)
        if not p.exists():
            bad_paths.append(f"no such file or directory: {path}")
        elif p.is_file() and p.suffix != ".clausal":
            bad_paths.append(f"not a .clausal file: {path}")
    if bad_paths:
        for msg in bad_paths:
            print(f"error: {msg}", file=sys.stderr)
        return 2

    total_passed = 0
    total_failed = 0
    files_seen = 0
    failures: list[tuple[str, TestResult]] = []

    for path in discover_clausal_files(parsed.paths):
        files_seen += 1
        file_results = run_file(path)
        rel = os.path.relpath(file_results.path)

        for r in file_results.results:
            if r.passed:
                total_passed += 1
                if parsed.verbose:
                    print(f"  PASS  {rel}::{r.name}")
            else:
                total_failed += 1
                failures.append((rel, r))
                if parsed.verbose:
                    msg = f"  FAIL  {rel}::{r.name}"
                    if r.error:
                        msg += f"  ({r.error})"
                    print(msg)

    # Summary
    print()
    if failures:
        print("FAILURES:")
        for rel, r in failures:
            err = f" — {r.error}" if r.error else ""
            print(f"  {rel}::{r.name}{err}")
        print()

    total = total_passed + total_failed

    # Distinguish "nothing to run" from "everything passed": files that exist but
    # contain no Test(...) clauses (or roots with no .clausal files at all) would
    # otherwise print a misleading [PASSED].
    if total == 0:
        if files_seen == 0:
            print("no .clausal files found")
        else:
            print(f"{files_seen} file(s) collected, but no Test(...) clauses found")
        if parsed.strict:
            print("0 tests [NO TESTS]")
            return 1
        print("0 tests [NO TESTS] (use --strict to fail)")
        return 0

    status = "PASSED" if total_failed == 0 else "FAILED"
    print(f"{total} tests: {total_passed} passed, {total_failed} failed [{status}]")
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
