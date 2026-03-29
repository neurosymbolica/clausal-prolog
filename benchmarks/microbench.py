"""Micro-benchmarks for Clausal's core primitive operations.

Measures nanoseconds-per-operation for:
  - deref on unbound Var
  - deref on directly-bound Var
  - deref walking a chain of 5 Vars
  - unify(Var, atom, trail)
  - trail.mark() + trail.undo(mark)
  - StepGenerator allocation
  - trampoline dispatch (1-step)

Usage (from project root):
    python benchmarks/microbench.py
"""

from __future__ import annotations

import timeit
from typing import Callable

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import StepGenerator, trampoline, DONE


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_bound_var() -> tuple[Var, Trail]:
    """Return a Var bound to 42, plus the Trail that keeps it bound."""
    v = Var()
    t = Trail()
    unify(v, 42, t)
    return v, t


def _make_chain(depth: int = 5) -> tuple[Var, Trail]:
    """Return the head of a chain of `depth` Vars all ultimately bound to 42."""
    t = Trail()
    vs = [Var() for _ in range(depth)]
    for i in range(depth - 1):
        unify(vs[i], vs[i + 1], t)
    unify(vs[-1], 42, t)
    return vs[0], t


# ── minimal generator for StepGenerator / trampoline benchmarks ──────────────

def _done_fn(this_generator: StepGenerator, parent: object) -> object:
    """Predicate that immediately signals DONE (no solutions)."""
    yield (parent, DONE)


def _one_solution_fn(this_generator: StepGenerator, parent: object) -> object:
    """Predicate that yields one solution then DONE."""
    yield (None, 42)   # root computation done; 42 is final answer


# ── benchmark table ───────────────────────────────────────────────────────────

N = 1_000_000  # iterations per measurement

_unbound = Var()
_bound, _bound_trail = _make_bound_var()
_chain, _chain_trail = _make_chain(5)
_trail = Trail()


BENCHMARKS: list[tuple[str, Callable]] = [
    (
        "deref(unbound Var)",
        lambda: deref(_unbound),
    ),
    (
        "deref(bound Var, 1-step)",
        lambda: deref(_bound),
    ),
    (
        "deref(chain depth=5)",
        lambda: deref(_chain),
    ),
    (
        "unify(Var, 42, trail) + undo",
        lambda: (
            lambda v=Var(), m=_trail.mark(): (unify(v, 42, _trail), _trail.undo(m))
        )(),
    ),
    (
        "trail.mark() + trail.undo()",
        lambda: _trail.undo(_trail.mark()),
    ),
    (
        "StepGenerator allocation",
        lambda: StepGenerator(_done_fn, None),
    ),
    (
        "trampoline (1 step, root done)",
        lambda: trampoline(StepGenerator(_one_solution_fn, None)),
    ),
]


def _run(label: str, fn: Callable, n: int = N) -> float:
    """Return nanoseconds per call."""
    total_s = timeit.timeit(fn, number=n)
    return total_s / n * 1e9


if __name__ == "__main__":
    col_w = 36
    print(f"\n{'Operation':<{col_w}}  {'ns/call':>10}  {'iterations':>12}")
    print("-" * (col_w + 28))
    for label, fn in BENCHMARKS:
        ns = _run(label, fn)
        print(f"{label:<{col_w}}  {ns:>10.1f}  {N:>12,}")
    print()
