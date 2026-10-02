"""Regression test: successive solve() queries on one loaded module must not
leak the first query's ground argument values into later queries.

Background
----------
``solve()`` compiles a top-level goal into a zero-arity ``_query`` predicate,
baking ground arguments into the generated code as literal constants. The
compiled function is memoised in ``solve._query_cache``. The cache key keyed on
argument *types* only (``int``, ``str``, …) rather than *values*, so
``plus_ten(1, V)`` and ``plus_ten(2, V)`` shared a cache entry — every query
after the first silently reused code with the first query's constant baked in,
returning wrong answers with no error.

See ``todo/query-state-leak-across-solve-calls-bug.md``.
"""

from __future__ import annotations

import os
import textwrap

import pytest

import clausal.import_hook  # noqa: F401  (installs the import hook)
from clausal.import_hook import _load_module
from clausal import Var, solve
from clausal.logic import solve as _solve_mod
from tests._suffix import SEAM


@pytest.fixture
def plus_ten_module(tmp_path):
    src = tmp_path / f"leakmod{SEAM}"
    src.write_text("plus_ten(X, Y) <- (Y == X + 10)\n")
    return _load_module("leakmod_regression", str(src))


def _solve_once(module, x):
    V = Var()
    for _ in solve(("plus_ten", x, V), module):
        return V.value
    return None


def test_distinct_int_args_not_pinned_to_first_query(plus_ten_module):
    """Reusing one module across queries with different ground ints is correct."""
    results = [_solve_once(plus_ten_module, x) for x in (1, 2, 5)]
    assert results == [11, 12, 15], (
        f"query cache leaked the first arg value across calls: got {results}"
    )


def test_interleaved_order_independent(plus_ten_module):
    """Result depends only on the argument, not on call order."""
    first = _solve_once(plus_ten_module, 7)
    second = _solve_once(plus_ten_module, 3)
    third = _solve_once(plus_ten_module, 7)
    assert (first, second, third) == (17, 13, 17)


def test_string_args_not_pinned(tmp_path):
    """Same leak guard for non-numeric ground args."""
    src = tmp_path / f"echomod{SEAM}"
    src.write_text("echo(X, X),\n")
    mod = _load_module("echomod_regression", str(src))

    def run(name):
        V = Var()
        for _ in solve(("echo", name, V), mod):
            return V.value
        return None

    assert [run("ann"), run("bob")] == ["ann", "bob"]


def test_cache_stays_bounded_and_correct(plus_ten_module, monkeypatch):
    """Many distinct ground values must not grow the cache without bound, and
    results stay correct across eviction."""
    monkeypatch.setattr(_solve_mod, "_QUERY_CACHE_MAX", 16)
    _solve_mod._query_cache.clear()
    n = 200
    results = [_solve_once(plus_ten_module, x) for x in range(n)]
    assert results == [x + 10 for x in range(n)]
    assert len(_solve_mod._query_cache) <= 16
