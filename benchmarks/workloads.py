"""Benchmark workloads for Clausal profiling.

Each function exercises a distinct execution pattern:

  bench_fib      -- recursive arithmetic (deref, trail mark/undo)
  bench_nqueens  -- backtracking search (choice points, indexing dispatch)
  bench_qsort    -- list unification (output phase, append, list patterns)
  bench_graph    -- sub-predicate call overhead (StepGenerator creation)
  bench_tabling  -- SLG tabling (hash lookups, suspension, completion)
  bench_struct_tabling -- SLG tabling over compound-term answers (walker
                          normalize/copy: do_deref_walk/c_copy_term/do_walk)
  bench_thunk_atoms -- ``++`` escapes over an atom-bearing argument (the
                       outbound term -> Python conversion on the thunk path)

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
    from clausal.logic.solve import solve

    F = Var()
    for _ in solve(("fib", n, F), fib):
        return int(deref(F))
    raise RuntimeError(f"fib({n}) produced no solutions")


def bench_nqueens(n: int = 8) -> int:
    """N-queens enumeration — stresses backtracking, choice points, indexing dispatch.

    queens(8) has 92 solutions and exercises deep backtracking.
    Expected wall time: ~1.2 s.
    """
    import clausal.examples.nqueens as nq
    from clausal.logic.variables import Var
    from clausal.logic.solve import solve

    count = 0
    QS = Var()
    for _ in solve(("queens", n, QS), nq):
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
    from clausal.logic.solve import _deref_walk, solve

    lst = list(range(list_size, 0, -1))
    result_len = 0
    for _ in range(reps):
        SORTED = Var()
        for _ in solve(("qsort", lst, SORTED), srt):
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
    from clausal.logic.solve import solve

    total = 0
    for _ in range(reps):
        Y, PATH = Var(), Var()
        for _ in solve(("path", 1, Y, PATH), g):
            total += 1
    return total


def bench_tabling(n: int = 5000, reps: int = 10) -> object:
    """Tabled fib(n) repeated reps times — stresses SLG tabling.

    Each repetition reloads the module so the table starts empty, forcing
    the full SLG computation: table lookup, subgoal suspension, answer
    completion, and answer consumption.
    Expected wall time: ~0.55 s per rep at n=5000, ~7.8 s at the default reps=10.

    fib/2 is functionally deterministic (each N matches exactly one clause
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

    fixture = os.path.join(_FIXTURES, "tabled_fib.seam")
    result = None
    for _ in range(reps):
        mod = load_clausal_module(fixture)
        lm = mod.__dict__["$module"]
        trail = Trail()
        R = Var()
        for _ in call("fib", n, R, module=lm, trail=trail):
            result = deref(R)
            break
        else:
            raise RuntimeError(f"fib({n}) produced no solutions")
    return result


def _cons_chain_length(node: object) -> int:
    """Length of a ``cons(H, T)`` chain, in EITHER term representation.

    The two ``struct_tabling`` benchmarks below walk the answer chain their
    fixture builds; this helper is the one place that knows what a link and
    a terminator look like, because the answer to that question changed
    twice:

    * a link is the cell ``("cons", H, T)`` (tail in slot 2) or, in the class
      representation, an instance with a ``.T`` attribute;
    * the terminator ``nil`` is a class instance in the class representation
      and the arity-0 cell ``("nil",)`` after the atoms-as-cells flip -- and
      an arity-0 cell IS a cell by shape, so ``is_cell(node)`` no longer
      separates link from terminator.  The arity does: a link's ``cell_args``
      has two slots, ``nil``'s has none.

    Terminating on the SHAPE rather than on ``node is nil`` also drops an
    identity comparison of an atom, which the atoms-as-cells design forbids
    (atoms compare by equality; two equal atom cells need not be one object).
    """
    from clausal.logic.variables import deref
    from clausal.logic.cells import cell_args, is_cell

    length = 0
    while True:
        if is_cell(node):
            args = cell_args(node)
            if len(args) < 2:       # ("nil",) -- the terminator
                return length
            node = deref(args[1])
        elif hasattr(node, "T"):    # class representation: cons(H, T)
            node = deref(node.T)
        else:                       # class representation: the nil instance
            return length
        length += 1


def bench_struct_tabling(n: int = 1500, reps: int = 3) -> int:
    """Tabled nats(n) repeated reps times — stresses SLG tabling's per-answer
    normalization/copy over COMPOUND answers (bench_tabling's Fib/2 answers
    are scalar ints; this benchmark exists because that gives the walkers
    ~0% share of a profile -- see
    .superpowers/sdd/2026-09-03-phase2-prereq-tabling-macro/task-3-report.md).

    Each repetition reloads the module so the table starts empty, same as
    bench_tabling above (see its docstring for why: a completed table's
    fresh call hits the COMPLETE fast path, which this benchmark does not
    want to measure -- it wants the full per-answer freeze/copy work every
    repetition).

    struct_tabling.seam's ``nats/2`` builds ``cons(N, cons(N-1, ...))``
    down to the 0-arity atom ``nil`` -- an O(K)-deep compound chain for
    subgoal ``nats(K, _)``. Tabling normalizes/copies each stored answer via
    ``freeze_args`` -> ``do_deref_walk`` (the C-exposed entry point for the
    walker Phase 0 sped up; see the fixture's header comment), so one
    top-level ``nats(n, _)`` call spawns n+1 tabled subgoals (K = 0..n) whose
    answer sizes sum to O(n^2) -- walk-dominated by design, and (per the
    same construction) exercises Phase 0's ``_clausal_new`` fast path, which
    builds every ``cons`` node the walk rebuilds.

    nats/2 is functionally deterministic (each N matches exactly one clause
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

    fixture = os.path.join(_FIXTURES, "struct_tabling.seam")
    length = 0
    for _ in range(reps):
        mod = load_clausal_module(fixture)
        lm = mod.__dict__["$module"]
        trail = Trail()
        L = Var()
        for _ in call("nats", n, L, module=lm, trail=trail):
            length = _cons_chain_length(deref(L))
            break
        else:
            raise RuntimeError(f"nats({n}) produced no solutions")
    return length


def bench_struct_tabling_tagged(n: int = 1500, reps: int = 3, intern: bool = False) -> int:
    """Cell-representation counterpart of ``bench_struct_tabling`` above --
    Phase 2 bridge Task 4's THE MEASUREMENT variants B (``intern=False``)
    and C (``intern=True``); variant A is ``bench_struct_tabling`` itself.

    Same tabled ``nats(N, L)`` recursion, same O(N^2) walk-dominated shape
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
    every tabled ``nats`` answer's cons-cell is interned as it is stored,
    so a structurally-equal cons chain -- including the SAME chain
    re-derived by a later rep's fresh module/table (every rep computes an
    identical ``nats(n, _)`` chain) -- collapses onto an earlier rep's
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
        clear_intern_table,
        set_intern_enabled,
    )

    fixture = os.path.join(_FIXTURES, "struct_tabling_tagged.seam")
    clear_intern_table()
    set_intern_enabled(intern)
    try:
        length = 0
        for _ in range(reps):
            mod = load_clausal_module(fixture)
            lm = mod.__dict__["$module"]
            L = Var()
            for _ in call("nats", n, L, module=lm):
                length = _cons_chain_length(deref(L))
                break
            else:
                raise RuntimeError(f"nats({n}) produced no solutions")
        return length
    finally:
        set_intern_enabled(False)


def bench_naf_ite(n: int = 3000) -> str:
    """NAF + ITE loops — stresses ``$naf_has_solution`` and if_/3 over a
    reified closure condition, in both the one-step and many-step shapes.
    (The general soft-cut ITE condition driver these loops were written for
    was removed when if_/3 came to require a reifiable condition, ruling
    2026-10-01.)

    Each sub-loop recurses *n* times; every iteration drives one NAF or ITE
    mini-trampoline.  See tests/fixtures/bench_naf_ite.seam for the four
    shapes.  Expected wall time: 0.2–1.0 s total (tune *n* to land there).
    """
    from clausal.testing import load_clausal_module
    from clausal.logic.solve import call

    fixture = os.path.join(_FIXTURES, "bench_naf_ite.seam")
    mod = load_clausal_module(fixture)
    for name in ("naf_fact_loop", "naf_chain_loop", "ite_det_loop", "ite_multi_loop"):
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


def bench_thunk_atoms(n: int = 100_000) -> int:
    """``++`` escape over an atom-bearing argument — the outbound-conversion
    benchmark named by the atoms-as-cells/strings design's perf gate.

    ``ThunkLoop/4`` recurses *n* times; every iteration evaluates one
    ``++len(L)`` escape whose single thunk argument is the five-element atom
    list ``[a, b, c, d, e]``.  The thunk argument path is where the design's
    §9.1 single outbound conversion lands: the compiler lowers a thunk
    argument to ``$to_python`` (a full recursive walk that unwraps each atom
    cell to its spelling) where it used to lower to a single-level
    ``$deref``.  This workload is deliberately shaped so that walk is the
    only thing that changed under it -- the loop around it is a plain tail
    recursion over integers, and the list is bound once, in ``thunk_atoms/2``,
    then passed down unchanged.

    Returns the accumulated sum (5 per iteration, so ``5 * n``), not a bare
    ``"ok"``: the accumulator is what forces every ``++`` result to be
    consumed rather than discarded by an optimiser.

    The source is written to a temp file rather than living in
    ``tests/fixtures/`` so this benchmark can be run against an arbitrary
    engine checkout by path, which is what the interleaved A/B gate does.

    Expected wall time (n=100 000): ~2 s.
    """
    import tempfile

    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref

    source = (
        "-private([a, b, c, d, e])\n"
        "-allow_singletons\n"
        "\n"
        "thunk_loop(0, _L, S, S),\n"
        "thunk_loop(N, L, ACC, S) <- (N > 0, K is ++len(L), ACC1 == ACC + K,\n"
        "                            M == N - 1, thunk_loop(M, L, ACC1, S)),\n"
        "\n"
        "thunk_atoms(N, S) <- (thunk_loop(N, [a, b, c, d, e], 0, S)),\n"
    )
    from clausal._suffixes import CLAUSAL_SUFFIXES  # the seam suffix

    with tempfile.NamedTemporaryFile(
        suffix=CLAUSAL_SUFFIXES[0], mode="w", delete=False
    ) as f:
        f.write(source)
        path = f.name
    try:
        pymod = _load_module("bench_thunk_atoms_src", path)
    finally:
        os.unlink(path)
    lm = pymod.__dict__["$module"]

    S = Var()
    for _ in call("thunk_atoms", n, S, module=lm):
        return int(deref(S))
    raise RuntimeError(f"thunk_atoms({n}) produced no solutions")


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
        ("bench_thunk_atoms", lambda: bench_thunk_atoms(20_000)),
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
