"""Benchmark workloads for Clausal profiling.

Each function exercises a distinct execution pattern:

  bench_fib      -- recursive arithmetic (deref, trail mark/undo)
  bench_nqueens  -- backtracking search (choice points, indexing dispatch)
  bench_qsort    -- list unification (output phase, append, list patterns)
  bench_graph    -- sub-predicate call overhead (StepGenerator creation)
  bench_tabling  -- SLG tabling (hash lookups, suspension, completion)
  bench_struct_tabling -- SLG tabling over compound-term answers (walker
                          normalize/copy: do_deref_walk/c_copy_term/do_walk)

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
    Expected wall time: ~0.55 s per rep at n=5000, ~7.8 s at the default reps=10.

    Fib/2 is functionally deterministic (each N matches exactly one clause
    head), so it has exactly one answer. This loop used to iterate the
    ``call()`` generator to exhaustion instead of stopping at the first
    answer -- wrong shape: forcing full enumeration where one answer
    suffices (2026-09-03 diagnosis, see
    .superpowers/sdd/2026-09-03-phase2-prereq-tabling-macro/task-2-report.md).
    Building the table (SLG lookup/suspend/complete) to answer the single
    query is already the "full SLG computation" the docstring promises;
    redoing the completed top-level generator for a *second* solution
    additionally walks its still-parked nested call frames looking for
    alternatives that provably don't exist, which is exponential in n
    because those frames resume by generator state rather than by a fresh
    table lookup. That redo cost is a real engine limitation (tracked
    separately), not something this benchmark needs to exercise -- taking
    the first answer and moving on is the correct, intentional shape, same
    as bench_fib above.
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
            break
        else:
            raise RuntimeError(f"Fib({n}) produced no solutions")
    return result


def bench_struct_tabling(n: int = 1500, reps: int = 3) -> int:
    """Tabled Nats(n) repeated reps times — stresses SLG tabling's per-answer
    normalization/copy over COMPOUND answers (bench_tabling's Fib/2 answers
    are scalar ints; this benchmark exists because that gives the walkers
    ~0% share of a profile -- see
    .superpowers/sdd/2026-09-03-phase2-prereq-tabling-macro/task-3-report.md).

    Each repetition reloads the module so the table starts empty, same as
    bench_tabling above (see its docstring for why: a completed table's
    fresh call hits the COMPLETE fast path, which this benchmark does not
    want to measure -- it wants the full per-answer freeze/copy work every
    repetition).

    struct_tabling.clausal's ``Nats/2`` builds ``cons(N, cons(N-1, ...))``
    down to the 0-arity atom ``nil`` -- an O(K)-deep compound chain for
    subgoal ``Nats(K, _)``. Tabling normalizes/copies each stored answer via
    ``freeze_args`` -> ``do_deref_walk`` (the C-exposed entry point for the
    walker Phase 0 sped up; see the fixture's header comment), so one
    top-level ``Nats(n, _)`` call spawns n+1 tabled subgoals (K = 0..n) whose
    answer sizes sum to O(n^2) -- walk-dominated by design, and (per the
    same construction) exercises Phase 0's ``_clausal_new`` fast path, which
    builds every ``cons`` node the walk rebuilds.

    Nats/2 is functionally deterministic (each N matches exactly one clause
    head), so it has exactly one answer per subgoal -- same first-answer
    stopping shape as bench_tabling and bench_fib above, not full
    enumeration.

    Returns the length of the answer chain (an int -- no float() conversion,
    same digit-count-style display discipline as bench_tabling's bignum
    result), not the chain term itself (dumping a 1500-deep nested compound
    inline is unreadable).

    The practical ceiling on n is not time (O(n^2) is slow but finite) --
    it's C recursion depth: do_deref_walk/do_walk (clausal/logic/
    _tabling_core.c, clausal/logic/variables/_variables.c) each hard-cap
    recursive descent at MAX_DEPTH = 50000, so an n approaching that bound
    would hit the depth guard on the chain walk before it hit any
    time-based limit.
    Expected wall time (n=1500, reps=3): ~4-5 s.
    """
    from clausal.testing import load_clausal_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, Trail, deref

    fixture = os.path.join(_FIXTURES, "struct_tabling.clausal")
    length = 0
    for _ in range(reps):
        mod = load_clausal_module(fixture)
        lm = mod.__dict__["$module"]
        nil = mod.nil
        trail = Trail()
        L = Var()
        for _ in call("Nats", n, L, module=lm, trail=trail):
            length = 0
            node = deref(L)
            while node is not nil:
                length += 1
                node = deref(node.T)
            break
        else:
            raise RuntimeError(f"Nats({n}) produced no solutions")
    return length


def bench_struct_tabling_tagged(n: int = 1500, reps: int = 3, intern: bool = False) -> int:
    """Cell-representation counterpart of ``bench_struct_tabling`` above --
    Phase 2 bridge Task 4's THE MEASUREMENT variants B (``intern=False``)
    and C (``intern=True``); variant A is ``bench_struct_tabling`` itself.

    Same tabled ``Nats(N, L)`` recursion, same O(N^2) walk-dominated shape
    (see ``bench_struct_tabling``'s docstring), but running the
    ``-tagged_terms`` fixture (``tests/fixtures/struct_tabling_tagged.
    clausal``, Task 3) instead: every ``cons(N, T)`` construction/match is
    the cell literal ``('cons', n, t)`` (a plain tuple) rather than a
    class instance. ``nil`` stays a class atom in BOTH fixtures (Phase 3
    does the atom pivot, not this bridge) -- the chain-length walk below
    therefore handles a cell node and the final ``nil`` sentinel
    differently, via ``is_cell``.

    ``intern=True`` flips ``clausal.logic.cells``' module-level interning
    switch on for the duration of this call (Task 4's ``intern_cell`` /
    the ``TableEntry.add_answer`` hook in ``clausal/logic/tabling.py``):
    every tabled ``Nats`` answer's cons-cell is interned as it is stored,
    so a structurally-equal cons chain -- including the SAME chain
    re-derived by a later rep's fresh module/table (every rep computes an
    identical ``Nats(n, _)`` chain) -- collapses onto an earlier rep's
    already-interned object instead of staying a freshly-walked/copied
    tuple every time. ``intern=False`` (default) leaves the switch off:
    freeze/copy work only, same shape of work as variant B / a plain
    cell-representation run with no interning.

    The intern table is cleared once, before the rep loop (not between
    reps) -- so within a single call, reps AFTER the first can reuse
    rep 1's interned cons cells (that cross-rep reuse is the effect this
    benchmark variant exists to measure), but two separate
    ``bench_struct_tabling_tagged`` calls (e.g. back-to-back invocations
    from the smoke test at the bottom of this file, or two rounds of a
    driver script) don't leak interned state into each other. The switch
    is always restored to OFF in a ``finally`` so an exception here can't
    leave a later, unrelated benchmark/test running with interning
    silently enabled.
    """
    from clausal.testing import load_clausal_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    from clausal.logic.cells import (
        cell_args,
        clear_intern_table,
        is_cell,
        set_intern_enabled,
    )

    fixture = os.path.join(_FIXTURES, "struct_tabling_tagged.clausal")
    clear_intern_table()
    set_intern_enabled(intern)
    try:
        length = 0
        for _ in range(reps):
            mod = load_clausal_module(fixture)
            lm = mod.__dict__["$module"]
            nil = mod.nil
            L = Var()
            for _ in call("Nats", n, L, module=lm):
                length = 0
                node = deref(L)
                while node is not nil:
                    length += 1
                    node = deref(cell_args(node)[1]) if is_cell(node) else deref(node.T)
                break
            else:
                raise RuntimeError(f"Nats({n}) produced no solutions")
        return length
    finally:
        set_intern_enabled(False)


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
        ("bench_struct_tabling", lambda: bench_struct_tabling()),
        ("bench_struct_tabling_tagged (intern=False)",
         lambda: bench_struct_tabling_tagged(300, 2, intern=False)),
        ("bench_struct_tabling_tagged (intern=True)",
         lambda: bench_struct_tabling_tagged(300, 2, intern=True)),
        ("bench_naf_ite",  lambda: bench_naf_ite()),
    ]

    def _display(result: object) -> str:
        # bench_tabling(5000) returns a ~1046-digit int (Fib(5000)) -- dumping
        # the full decimal expansion inline is unreadable and, historically,
        # this codepath is the one that used to float()-convert bignums
        # (see .superpowers/sdd/2026-09-03-phase2-prereq-tabling-macro/
        # task-2-report.md); print a digit count instead of the value itself.
        if isinstance(result, int) and abs(result) >= 10**20:
            return f"<int, {len(str(abs(result)))} digits>"
        return repr(result)

    for name, fn in workloads:
        t0 = time.perf_counter()
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - one bad workload shouldn't hide the rest
            elapsed = time.perf_counter() - t0
            print(f"{name:20s}  ERROR={exc!r}  {elapsed:.3f}s")
            continue
        elapsed = time.perf_counter() - t0
        print(f"{name:20s}  result={_display(result):>12}  {elapsed:.3f}s")
