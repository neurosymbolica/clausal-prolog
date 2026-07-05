"""Shared fixtures for the 2026-07-05 Fable partition audit suite.

Run these tests PER FILE only — `pytest tests/` OOM-SIGKILLs on this box.

C-finding toolkit (spec §"C-finding verification toolkit"):
- ``refcount_stable`` — object-count AND allocation deltas over a stress loop
  (catches leaks that show up as growth in the Python heap / GC graph).
- ``getrefcount_stable`` — per-object ``sys.getrefcount`` delta over a stress
  loop (catches C-level refcount leaks on an object the GC-graph count can't
  see, e.g. a leaked reference on a long-lived object).
"""
import gc
import sys
import tracemalloc

import pytest


@pytest.fixture
def clear_query_cache():
    """Clear solve._query_cache — it keys by arg *types*, so back-to-back
    solves with differing non-Var args need a clear between them."""
    from clausal.logic import solve
    solve._query_cache.clear()
    yield
    solve._query_cache.clear()


@pytest.fixture
def refcount_stable():
    """Return a helper asserting no unbounded object-count OR allocation growth
    across a stress loop. Tracks both ``len(gc.get_objects())`` and
    ``tracemalloc`` current-size deltas — the allocation delta catches leaks of
    objects that are freed from the GC graph but whose backing memory is not.
    Usage:
        refcount_stable(lambda: do_work(), iterations=2000)
        refcount_stable(thunk, iterations=5000, tol=64, alloc_tol=65536)
    """
    def _run(thunk, iterations=2000, tol=64, alloc_tol=65536):
        thunk()  # warm up caches
        gc.collect()
        started_tracing = not tracemalloc.is_tracing()
        if started_tracing:
            tracemalloc.start()
        gc.collect()
        alloc_before, _ = tracemalloc.get_traced_memory()
        obj_before = len(gc.get_objects())
        for _ in range(iterations):
            thunk()
        gc.collect()
        obj_after = len(gc.get_objects())
        alloc_after, _ = tracemalloc.get_traced_memory()
        if started_tracing:
            tracemalloc.stop()
        assert obj_after - obj_before <= tol, (
            f"object growth {obj_after - obj_before} over {iterations} iters "
            f"exceeds tolerance {tol} — suspected leak"
        )
        assert alloc_after - alloc_before <= alloc_tol, (
            f"allocation growth {alloc_after - alloc_before} bytes over "
            f"{iterations} iters exceeds tolerance {alloc_tol} — suspected leak"
        )
    return _run


@pytest.fixture
def getrefcount_stable():
    """Return a helper asserting a specific long-lived object's refcount does
    not grow across a stress loop. Catches C-level refcount leaks that
    ``gc.get_objects()`` counting cannot see (a C function that over-INCREFs an
    argument it holds a borrowed reference to leaves the object's refcount
    climbing without adding a new object to the graph).

    ``sys.getrefcount`` returns a value inflated by the temporary argument
    reference, but that inflation is identical before and after, so the delta is
    the signal. Usage:
        getrefcount_stable(obj, lambda: use(obj), iterations=2000)
    """
    def _run(obj, exercise, iterations=2000, tol=0):
        exercise()  # warm up caches
        gc.collect()
        before = sys.getrefcount(obj)
        for _ in range(iterations):
            exercise()
        gc.collect()
        after = sys.getrefcount(obj)
        assert after - before <= tol, (
            f"refcount of {obj!r} grew by {after - before} over {iterations} "
            f"iters (tol {tol}) — suspected C-level refcount leak"
        )
    return _run
