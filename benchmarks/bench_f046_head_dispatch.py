"""Micro-benchmark for the F046 str-literal head fix.

After F046, a clause head pinning a string literal (e.g. ``Color("red") <-
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
Helper(1),

Color("red") <- (Helper(1))
Color("green") <- (Helper(1))
Color("blue") <- (Helper(1))
Color("cyan") <- (Helper(1))
Color("magenta") <- (Helper(1))
Color("yellow") <- (Helper(1))
"""

_INT_SRC = """\
Helper(1),

Code(10) <- (Helper(1))
Code(20) <- (Helper(1))
Code(30) <- (Helper(1))
Code(40) <- (Helper(1))
Code(50) <- (Helper(1))
Code(60) <- (Helper(1))
"""

_str_mod = _load_inline("bench_f046_str", _STR_SRC)
_int_mod = _load_inline("bench_f046_int", _INT_SRC)


def _drain(functor: str, arg, mod) -> int:
    return sum(1 for _ in call(functor, arg, module=mod))


# Pick a literal in the middle of the table so dispatch does real work.
BENCHMARKS = [
    (
        "str head, str caller (fast == path)",
        lambda: _drain("Color", "magenta", _str_mod),
    ),
    (
        "str head, char-list caller (unify path)",
        lambda: _drain("Color", ["m", "a", "g", "e", "n", "t", "a"], _str_mod),
    ),
    (
        "int head, int caller (MatchValue baseline)",
        lambda: _drain("Code", 50, _int_mod),
    ),
]

N = 100_000


if __name__ == "__main__":
    # Sanity: every probed call must yield exactly one solution.
    assert _drain("Color", "magenta", _str_mod) == 1
    assert _drain("Color", list("magenta"), _str_mod) == 1
    assert _drain("Code", 50, _int_mod) == 1

    col_w = 44
    print(f"\n{'Dispatch':<{col_w}}  {'us/call':>10}  {'iterations':>12}")
    print("-" * (col_w + 28))
    for label, fn in BENCHMARKS:
        total_s = timeit.timeit(fn, number=N)
        us = total_s / N * 1e6
        print(f"{label:<{col_w}}  {us:>10.3f}  {N:>12,}")
    print()
