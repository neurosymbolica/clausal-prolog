"""Class B: top-level ground arguments of a predicate-call query are
parameterized (bound at runtime) rather than baked into the compiled code as
literals, so distinct argument values reuse one compiled query instead of
recompiling per value.

This keeps the value-keyed cache from the leak fix correct *and* makes the
common harness pattern — querying one loaded module with many different ground
values — compile once instead of once-per-value.

See class B in ``todo/fix-audit-2026-06-24.md``.
"""

from __future__ import annotations

import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal import Var, solve
from clausal.logic import solve as _solve_mod


def _load(tmp_path, name, text):
    src = tmp_path / f"{name}.clausal"
    src.write_text(text)
    return _load_module(name, str(src))


def test_distinct_int_args_reuse_one_compiled_query(tmp_path):
    mod = _load(tmp_path, "paramint", "plus_ten(X, Y) <- (Y == X + 10)\n")
    _solve_mod._query_cache.clear()

    def run(x):
        V = Var()
        for _ in solve(mod.plus_ten(x, V), mod):
            return V.value
        return None

    results = [run(i) for i in range(50)]
    assert results == [i + 10 for i in range(50)]
    # All 50 distinct-valued calls must share ONE compiled query (arg is
    # parameterized, not baked), not 50 separate cache entries.
    assert len(_solve_mod._query_cache) == 1


def test_string_args_reuse_one_compiled_query(tmp_path):
    """String scalar args are parameterized just like numbers."""
    mod = _load(tmp_path, "paramstr", "echo(X, X),\n")
    _solve_mod._query_cache.clear()

    def run(name):
        V = Var()
        for _ in solve(mod.echo(name, V), mod):
            return V.value
        return None

    assert [run("ann"), run("bob"), run("cat")] == ["ann", "bob", "cat"]
    assert len(_solve_mod._query_cache) == 1


def test_all_ground_query_reuse(tmp_path):
    mod = _load(tmp_path, "paramground", "edge(1, 2),\nedge(2, 3),\nedge(1, 3),\n")
    _solve_mod._query_cache.clear()

    def holds(a, b):
        for _ in solve(mod.edge(a, b), mod):
            return True
        return False

    assert holds(1, 2) is True
    assert holds(2, 3) is True
    assert holds(9, 9) is False
    assert len(_solve_mod._query_cache) == 1


def test_parameterized_arg_multi_solution_and_interleaved(tmp_path):
    """A parameterized ground arg must survive internal backtracking (multi
    solution) and stay isolated across interleaved different-valued queries."""
    mod = _load(tmp_path, "parammulti", "edge(1, 2),\nedge(1, 3),\nedge(2, 4),\n")
    _solve_mod._query_cache.clear()

    def succs(a):
        Y = Var()
        return sorted(Y.value for _ in solve(mod.edge(a, Y), mod))

    assert succs(1) == [2, 3]
    assert succs(2) == [4]
    assert succs(1) == [2, 3]          # not pinned to the earlier query
    assert len(_solve_mod._query_cache) == 1
