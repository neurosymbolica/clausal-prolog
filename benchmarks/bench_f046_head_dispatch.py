"""Micro-benchmark for the F046 str-literal head fix.

After F046, a clause head pinning a string literal (e.g. ``color("red") <-
body``) compiles to a wildcard capture + a same-type-short-circuit unify guard
(``_scap == "red" or unify(_scap, "red", trail)``) instead of a bare
``MatchValue``. This script measures the dispatch cost of a str-literal
dispatch table for:

  (i)  a same-type **str** caller  — should hit the fast ``==`` disjunct;
  (ii) a **char-list** caller       — falls through to ``unify()`` (the path
                                       F046 actually repairs).

Both are compared against an ``int``-literal dispatch table of the same shape,
which still compiles to ``MatchValue`` (untouched by F046) — a rough yardstick
for "what native match dispatch costs here". Use this to confirm the same-type
str path stays close to the int baseline and the char-list path is acceptable.

Usage (from project root):
    python benchmarks/bench_f046_head_dispatch.py
"""

from __future__ import annotations

import os
import tempfile
import timeit

from clausal.import_hook import _load_module
from clausal.logic.solve import call


def _load_inline(name: str, source: str):
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path).__dict__["$module"]
    finally:
        os.unlink(path)


# A str-literal dispatch table and an int-literal table of identical shape.
_STR_SRC = """\
helper(1),

color("red") <- (helper(1))
color("green") <- (helper(1))
color("blue") <- (helper(1))
color("cyan") <- (helper(1))
color("magenta") <- (helper(1))
color("yellow") <- (helper(1))
"""

_INT_SRC = """\
helper(1),

code(10) <- (helper(1))
code(20) <- (helper(1))
code(30) <- (helper(1))
code(40) <- (helper(1))
code(50) <- (helper(1))
code(60) <- (helper(1))
"""

_str_mod = _load_inline("bench_f046_str", _STR_SRC)
_int_mod = _load_inline("bench_f046_int", _INT_SRC)


def _drain(functor: str, arg, mod) -> int:
    return sum(1 for _ in call(functor, arg, module=mod))


# Pick a literal in the middle of the table so dispatch does real work.
BENCHMARKS = [
    (
        "str head, str caller (fast == path)",
        lambda: _drain("color", "magenta", _str_mod),
    ),
    (
        "str head, char-list caller (unify path)",
        lambda: _drain("color", ["m", "a", "g", "e", "n", "t", "a"], _str_mod),
    ),
    (
        "int head, int caller (MatchValue baseline)",
        lambda: _drain("code", 50, _int_mod),
    ),
]

N = 100_000


if __name__ == "__main__":
    # Sanity: every probed call must yield exactly one solution.
    assert _drain("color", "magenta", _str_mod) == 1
    assert _drain("color", list("magenta"), _str_mod) == 1
    assert _drain("code", 50, _int_mod) == 1

    col_w = 44
    print(f"\n{'Dispatch':<{col_w}}  {'us/call':>10}  {'iterations':>12}")
    print("-" * (col_w + 28))
    for label, fn in BENCHMARKS:
        total_s = timeit.timeit(fn, number=N)
        us = total_s / N * 1e6
        print(f"{label:<{col_w}}  {us:>10.3f}  {N:>12,}")
    print()
