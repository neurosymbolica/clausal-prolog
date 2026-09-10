"""Micro-benchmark for the bytes-as-lists head-dispatch path.

After bytes-as-lists, a clause head pinning a bytes literal (e.g.
``code(b"red") <- body``) compiles to a wildcard capture + same-type
short-circuit unify guard (``_bcap == b"red" or unify(_bcap, b"red", trail)``)
instead of a bare ``MatchValue``. This measures dispatch cost for:

  (i)  a same-type **bytes** caller — should hit the fast ``==`` disjunct;
  (ii) an **int-list** caller        — falls through to ``unify()`` (the
                                        codes-model path).

Compared against an ``int``-literal dispatch table (still ``MatchValue``).

Usage (from project root):
    python benchmarks/bench_bytes_dispatch.py
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


_BYTES_SRC = """\
helper(1),

color(b"red") <- (helper(1))
color(b"green") <- (helper(1))
color(b"blue") <- (helper(1))
color(b"cyan") <- (helper(1))
color(b"magenta") <- (helper(1))
color(b"yellow") <- (helper(1))
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

_bytes_mod = _load_inline("bench_bytes_str", _BYTES_SRC)
_int_mod = _load_inline("bench_bytes_int", _INT_SRC)


def _drain(functor: str, arg, mod) -> int:
    return sum(1 for _ in call(functor, arg, module=mod))


BENCHMARKS = [
    (
        "bytes head, bytes caller (fast == path)",
        lambda: _drain("color", b"magenta", _bytes_mod),
    ),
    (
        "bytes head, int-list caller (unify path)",
        lambda: _drain("color", list(b"magenta"), _bytes_mod),
    ),
    (
        "int head, int caller (MatchValue baseline)",
        lambda: _drain("code", 50, _int_mod),
    ),
]

N = 100_000


if __name__ == "__main__":
    assert _drain("color", b"magenta", _bytes_mod) == 1
    assert _drain("color", list(b"magenta"), _bytes_mod) == 1
    assert _drain("code", 50, _int_mod) == 1

    col_w = 44
    print(f"\n{'Dispatch':<{col_w}}  {'us/call':>10}  {'iterations':>12}")
    print("-" * (col_w + 28))
    for label, fn in BENCHMARKS:
        total_s = timeit.timeit(fn, number=N)
        us = total_s / N * 1e6
        print(f"{label:<{col_w}}  {us:>10.3f}  {N:>12,}")
    print()
