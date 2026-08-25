"""Benchmark workloads for Clausal profiling.

Each function exercises a distinct execution pattern:

  bench_fib      -- recursive arithmetic (deref, trail mark/undo)
  bench_nqueens  -- backtracking search (choice points, indexing dispatch)
  bench_qsort    -- list unification (output phase, append, list patterns)
  bench_graph    -- sub-predicate call overhead (StepGenerator creation)
  bench_tabling  -- SLG tabling (hash lookups, suspension, completion)

Run standalone to verify all workloads complete without error:
    python benchmarks/workloads.py
"""

from __future__ import annotations

import os
import sys

# Ensure test fixtures directory is on sys.path for tabling benchmark.
_FIXTURES = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures")
if _FIXTURES not in sys.path:
    sys.path.insert(0, _FIXTURES)


def bench_fib(n: int = 25) -> int:
    """Naive recursive Fibonacci — stresses deref, trail.mark/undo, StepGenerator.

    fib(25) performs ~150 000 recursive calls without memoisation.
    Expected wall time: ~0.8 s.
    """
    import clausal.examples.fibonacci as fib
    from clausal.logic.variables import Var, deref

    F = Var()
    for _ in fib.Fib(n, F):
        return int(deref(F))
    raise RuntimeError(f"Fib({n}) produced no solutions")


def bench_nqueens(n: int = 8) -> int:
    """N-queens enumeration — stresses backtracking, choice points, indexing dispatch.

    queens(8) has 92 solutions and exercises deep backtracking.
    Expected wall time: ~1.2 s.
    """
    import clausal.examples.nqueens as nq
    from clausal.logic.variables import Var

    count = 0
    QS = Var()
    for _ in nq.Queens(n, QS):
        count += 1
    return count


def bench_qsort(list_size: int = 20, reps: int = 200) -> int:
    """Quicksort repeated reps times — stresses list unification output phase.

    Each call sorts a 20-element reversed list, exercising [H|T] patterns,
    append/3, and list construction at every level of the recursion.
    Expected wall time: ~0.3 s.
    """
    import clausal.examples.sorting as srt
    from clausal.logic.variables import Var, deref
    from clausal.logic.solve import _deref_walk

    lst = list(range(list_size, 0, -1))
    result_len = 0
    for _ in range(reps):
        SORTED = Var()
        for _ in srt.Qsort(lst, SORTED):
            result_len = len(_deref_walk(deref(SORTED)))
            break
    return result_len


def bench_graph(reps: int = 500) -> int:
    """Graph path enumeration repeated reps times — stresses StepGenerator creation.

    Each call enumerates all paths from node 1 via Path/3, which calls
    PathAcc/4 and Edge/2 recursively, creating a new StepGenerator per
    sub-predicate call.
    Expected wall time: ~0.4 s.
    """
    import clausal.examples.graph as g
    from clausal.logic.variables import Var

    total = 0
    for _ in range(reps):
        Y, PATH = Var(), Var()
        for _ in g.Path(1, Y, PATH):
            total += 1
    return total


def bench_tabling(n: int = 5000, reps: int = 10) -> object:
    """Tabled Fibonacci(n) repeated reps times — stresses SLG tabling.

    Each repetition reloads the module so the table starts empty, forcing
    the full SLG computation: table lookup, subgoal suspension, answer
    completion, and answer consumption.
    Expected wall time: ~0.7 s.
    """
    from clausal.testing import load_clausal_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, Trail, deref

    fixture = os.path.join(_FIXTURES, "tabled_fib.clausal")
    result = None
    for _ in range(reps):
        mod = load_clausal_module(fixture)
        lm = mod.__dict__["$module"]
        trail = Trail()
        R = Var()
        for _ in call("Fib", n, R, module=lm, trail=trail):
            result = deref(R)
    return result


def bench_naf_ite(n: int = 3000) -> str:
    """NAF + general-ITE drive loops — stresses ``$naf_has_solution`` and the
    ITE condition driver in both the trivial one-step and many-step shapes.

    Each sub-loop recurses *n* times; every iteration drives one NAF or ITE
    mini-trampoline.  See tests/fixtures/bench_naf_ite.clausal for the four
    shapes.  Expected wall time: 0.2–1.0 s total (tune *n* to land there).
    """
    from clausal.testing import load_clausal_module
    from clausal.logic.solve import call

    fixture = os.path.join(_FIXTURES, "bench_naf_ite.clausal")
    mod = load_clausal_module(fixture)
    for name in ("NafFactLoop", "NafChainLoop", "IteDetLoop", "IteMultiLoop"):
        pred = getattr(mod, name)
        # ``load_clausal_module`` evicts its private module name from
        # sys.modules once loaded (see its docstring), so iterating the
        # term instance directly (``pred(n)``) can't auto-infer the module
        # via ``__module__`` lookup.  Passing the PredicateMeta class to
        # ``call()`` takes its fast path (``_get_dispatch()``), which needs
        # no module at all.
        for _ in call(pred, n):
            break
        else:
            raise RuntimeError(f"{name}({n}) produced no solutions")
    return "ok"


# ── Smoke-test all workloads ──────────────────────────────────────────────────

if __name__ == "__main__":
    import time

    workloads = [
        ("bench_fib",     lambda: bench_fib(25)),
        ("bench_nqueens", lambda: bench_nqueens(8)),
        ("bench_qsort",   lambda: bench_qsort()),
        ("bench_graph",   lambda: bench_graph()),
        ("bench_tabling", lambda: bench_tabling()),
        ("bench_naf_ite",  lambda: bench_naf_ite()),
    ]

    for name, fn in workloads:
        t0 = time.perf_counter()
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - one bad workload shouldn't hide the rest
            elapsed = time.perf_counter() - t0
            print(f"{name:20s}  ERROR={exc!r}  {elapsed:.3f}s")
            continue
        elapsed = time.perf_counter() - t0
        print(f"{name:20s}  result={result!r:>12}  {elapsed:.3f}s")
