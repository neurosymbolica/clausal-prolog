"""Micro-benchmark: what building a saturated (all-args-given) term costs.

A term is a CELL -- the plain tuple ``(name, a0, .., an)``.  Three ways to
build one are timed:

  (A) ``build_term_cell``  -- ``clausal.logic.predicate.build_term_cell``,
                              the one home of construction against a
                              registered signature (the arity check and the
                              keyword/positional placement), as a clause
                              head's ``$head`` reaches it;
  (B) keyword placement    -- ``build_term_cell`` with every slot NAMED, the
                              placement path a keyword construction takes;
  (C) tuple literal        -- a bare ``(name, v0, .., vn)``, the floor: what
                              construction costs when Python does the
                              absolute minimum.

Measured at arities 1, 3 and 8.  Batches for (A), (B), (C) are interleaved
within a single process run (this repo's perf-gate convention), so GC and
thermal drift hit all three equally instead of favouring whichever runs first
or last.  No baseline files are saved -- this is a point-in-time honesty
check, not a regression gate.

It used to time a ``make_predicate`` class's ``__call__`` against its Phase 0
``_clausal_new`` fast path.  W4a removed ``_clausal_new`` (the script had not
run since) and W4b-3 slice 6 retired ``make_predicate``: a term is a tuple,
and ``build_term_cell`` is the checked path to one.

Usage (from project root):
    ./venv/bin/python benchmarks/bench_term_construction.py
"""

from __future__ import annotations

import os
import sys
import timeit

# Running this file directly (`python benchmarks/bench_term_construction.py`)
# puts the script's own directory at sys.path[0], NOT the repo root, so a
# `clausal` install elsewhere on sys.path (e.g. the canonical checkout) can
# shadow this worktree's package.  Force the repo root to the front.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import clausal  # noqa: E402
from clausal.logic.predicate import build_term_cell  # noqa: E402

ARITIES = [1, 3, 8]

# Number of timeit calls per batch, and number of interleaved batches per
# variant (so the total work per variant is BATCHES * N calls).
N = 100_000
BATCHES = 5

A = "A: build_term_cell(pos)"
B = "B: build_term_cell(kw)"
C = "C: tuple literal"


def _make_variants(arity: int):
    """Build (A, B, C) zero-arg thunks for *arity*."""
    name = f"bench{arity}"
    fields = tuple(f"a{i}" for i in range(arity))
    values = tuple(range(arity))
    keywords = dict(zip(fields, values))

    def by_position():
        return build_term_cell(name, fields, values, {})

    def by_keyword():
        # build_term_cell consumes its kwargs dict: hand it a fresh one.
        return build_term_cell(name, fields, (), dict(keywords))

    def literal():
        return (name, *values)

    # Sanity: all three build the same term.
    assert by_position() == by_keyword() == literal() == (name, *values)
    return {A: by_position, B: by_keyword, C: literal}


def _interleaved_timings(variants: dict) -> dict:
    """Run BATCHES interleaved timeit batches per variant; return ns/op."""
    totals_s = {label: 0.0 for label in variants}
    for _ in range(BATCHES):
        for label, fn in variants.items():
            totals_s[label] += timeit.timeit(fn, number=N)
    total_calls = BATCHES * N
    return {label: (total_s / total_calls) * 1e9
            for label, total_s in totals_s.items()}


if __name__ == "__main__":
    print(f"engine: {clausal.__file__}")
    col_w = 26
    print(f"\n{'Arity':>5}  {'Variant':<{col_w}}  {'ns/op':>10}  "
          f"{'x literal':>10}")
    print("-" * (5 + col_w + 34))

    for arity in ARITIES:
        ns = _interleaved_timings(_make_variants(arity))
        floor = ns[C]
        for label, val in ns.items():
            ratio = val / floor if floor else float("inf")
            print(f"{arity:>5}  {label:<{col_w}}  {val:>10.1f}  "
                  f"{ratio:>9.2f}x")
        print()
