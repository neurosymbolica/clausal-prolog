"""Micro-benchmark for the bytes-as-lists head-dispatch path.

After bytes-as-lists, a clause head pinning a bytes literal (e.g.
``Code(b"red") <- body``) compiles to a wildcard capture + same-type
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
Helper(1),

Color(b"red") <- (Helper(1))
Color(b"green") <- (Helper(1))
Color(b"blue") <- (Helper(1))
Color(b"cyan") <- (Helper(1))
Color(b"magenta") <- (Helper(1))
Color(b"yellow") <- (Helper(1))
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

_bytes_mod = _load_inline("bench_bytes_str", _BYTES_SRC)
_int_mod = _load_inline("bench_bytes_int", _INT_SRC)


def _drain(functor: str, arg, mod) -> int:
    return sum(1 for _ in call(functor, arg, module=mod))


BENCHMARKS = [
    (
        "bytes head, bytes caller (fast == path)",
        lambda: _drain("Color", b"magenta", _bytes_mod),
    ),
    (
        "bytes head, int-list caller (unify path)",
        lambda: _drain("Color", list(b"magenta"), _bytes_mod),
    ),
    (
        "int head, int caller (MatchValue baseline)",
        lambda: _drain("Code", 50, _int_mod),
    ),
]

N = 100_000


if __name__ == "__main__":
    assert _drain("Color", b"magenta", _bytes_mod) == 1
    assert _drain("Color", list(b"magenta"), _bytes_mod) == 1
    assert _drain("Code", 50, _int_mod) == 1

    col_w = 44
    print(f"\n{'Dispatch':<{col_w}}  {'us/call':>10}  {'iterations':>12}")
    print("-" * (col_w + 28))
    for label, fn in BENCHMARKS:
        total_s = timeit.timeit(fn, number=N)
        us = total_s / N * 1e6
        print(f"{label:<{col_w}}  {us:>10.3f}  {N:>12,}")
    print()
