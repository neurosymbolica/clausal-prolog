"""Shared fixtures for the 2026-07-05 Fable partition audit suite.

Run these tests PER FILE only — `pytest tests/` OOM-SIGKILLs on this box.
"""
import gc

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
    """Return a helper asserting no unbounded refcount/object growth across a
    stress loop. Usage:
        refcount_stable(lambda: do_work(), iterations=2000)
    """
    def _run(thunk, iterations=2000, tol=64):
        thunk()  # warm up caches
        gc.collect()
        before = len(gc.get_objects())
        for _ in range(iterations):
            thunk()
        gc.collect()
        after = len(gc.get_objects())
        assert after - before <= tol, (
            f"object growth {after - before} over {iterations} iters "
            f"exceeds tolerance {tol} — suspected leak"
        )
    return _run
