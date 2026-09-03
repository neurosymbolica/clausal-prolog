"""Micro-benchmark for the Phase 0 term-construction fast path.

Compares three ways to build a saturated (all-args-given) `PredicateMeta`
term:

  (A) slow path  — ``cls(v0, .., vn)``, going through ``PredicateMeta.__call__``
                    (arity checking, keyword/positional merge, `__init__`);
  (B) fast path  — ``cls._clausal_new(v0, .., vn)``, the exec-generated
                    classmethod from Phase 0 Task 1 (``cls.__new__`` + direct
                    field assignment, no checks);
  (C) reference  — a bare ``(name, v0, .., vn)`` tuple literal, as a rough
                    floor for "what construction costs when Python does the
                    absolute minimum".

Measured at arities 1, 3, and 8, using ``make_predicate`` to mint throwaway
classes. Batches for (A), (B), (C) are interleaved within a single process
run (this repo's perf-gate convention) so GC/thermal drift hits all three
variants equally instead of favoring whichever runs first or last. No
baseline files are saved — this is a point-in-time honesty check, not a
regression gate.

Usage (from project root):
    /workspace/clausal/venv/bin/python benchmarks/bench_term_construction.py
"""

from __future__ import annotations

import os
import sys
import timeit

# Running this file directly (`python benchmarks/bench_term_construction.py`)
# puts the script's own directory at sys.path[0], NOT the repo root, so a
# `clausal` install elsewhere on sys.path (e.g. the canonical checkout) can
# shadow this worktree's package. Force the repo root to the front so the
# worktree's `clausal` (with Phase 0's `_clausal_new`) is what gets imported.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from clausal.logic.predicate import make_predicate

ARITIES = [1, 3, 8]

# Number of timeit calls per batch, and number of interleaved batches per
# variant (so the total work per variant is BATCHES * N calls).
N = 100_000
BATCHES = 5


def _make_variants(arity: int):
    """Build (slow_call, fast_call, tuple_call) zero-arg thunks for `arity`."""
    fields = [f"a{i}" for i in range(arity)]
    cls = make_predicate(f"Bench{arity}", fields)
    values = tuple(range(arity))
    name = cls.__name__

    # Sanity: fast path must build an equal term to the slow path.
    assert cls(*values) == cls._clausal_new(*values)

    if arity == 1:
        (v0,) = values
        slow = lambda: cls(v0)
        fast = lambda: cls._clausal_new(v0)
        ref = lambda: (name, v0)
    elif arity == 3:
        v0, v1, v2 = values
        slow = lambda: cls(v0, v1, v2)
        fast = lambda: cls._clausal_new(v0, v1, v2)
        ref = lambda: (name, v0, v1, v2)
    elif arity == 8:
        v0, v1, v2, v3, v4, v5, v6, v7 = values
        slow = lambda: cls(v0, v1, v2, v3, v4, v5, v6, v7)
        fast = lambda: cls._clausal_new(v0, v1, v2, v3, v4, v5, v6, v7)
        ref = lambda: (name, v0, v1, v2, v3, v4, v5, v6, v7)
    else:
        raise ValueError(f"unsupported arity {arity}")

    return {"A: cls(...)": slow, "B: cls._clausal_new(...)": fast, "C: tuple literal": ref}


def _interleaved_timings(variants: dict) -> dict:
    """Run BATCHES interleaved timeit batches per variant; return ns/op totals."""
    totals_s = {label: 0.0 for label in variants}
    for _ in range(BATCHES):
        for label, fn in variants.items():
            totals_s[label] += timeit.timeit(fn, number=N)
    total_calls = BATCHES * N
    return {label: (total_s / total_calls) * 1e9 for label, total_s in totals_s.items()}


if __name__ == "__main__":
    col_w = 26
    print(f"\n{'Arity':>5}  {'Variant':<{col_w}}  {'ns/op':>10}  {'A/B ratio':>10}")
    print("-" * (5 + col_w + 34))

    for arity in ARITIES:
        variants = _make_variants(arity)
        ns = _interleaved_timings(variants)
        a_ns = ns["A: cls(...)"]
        b_ns = ns["B: cls._clausal_new(...)"]
        ratio = a_ns / b_ns if b_ns else float("inf")
        for label, val in ns.items():
            ratio_str = f"{ratio:>9.2f}x" if label == "A: cls(...)" else ""
            print(f"{arity:>5}  {label:<{col_w}}  {val:>10.1f}  {ratio_str:>10}")
        print(f"{'':>5}  {'-> A/B speedup':<{col_w}}  {'':>10}  {ratio:>9.2f}x")
        if arity == 3 and ratio < 4.0:
            print(
                f"\n*** WARNING: arity-3 A/B ratio {ratio:.2f}x is BELOW the "
                "expected >=4x fast-path speedup. ***\n"
            )
        print()
