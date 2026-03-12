"""Tests for Step 7 — clausal.logic.solve query API.

Covers: call, solve, query, once, Module.solve
"""

from __future__ import annotations

import pytest

from clausal.logic.compiler import compile_predicate_trampoline
from clausal.logic.database import Clause, Database, Module
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.solve import call, solve, query, once, _deref_walk
from clausal.terms import (
    And, Or, Not,
    Unify as Is, StructuralEq, Lt,
    In,
    Call, LoadName,
    Compound,
)


# ── Shared fixtures ────────────────────────────────────────────────────────────


def _make_edge_module() -> Module:
    """Build a Module with edge/2 facts and path/2 transitive closure.

    Graph: a→b, b→c, c→d, b→d.
    """
    mod = Module("test_edges")
    db = mod.db

    # edge facts: literal source, Var destination with Is body
    for src, dst in [("a", "b"), ("b", "c"), ("c", "d"), ("b", "d")]:
        dv = Var()
        db.assertz(Clause(
            head=Compound("edge", (src, dv)),
            body=[Is(left=dv, right=dst)],
        ))
    compile_predicate_trampoline("edge", 2, db.clauses_for("edge", 2), db)

    # path(X, Y) :- edge(X, Y).
    px, py = Var(), Var()
    db.assertz(Clause(
        head=Compound("path", (px, py)),
        body=[Call(func=LoadName(name="edge"), args=[px, py], kwargs=[])],
    ))

    # path(X, Y) :- edge(X, Z), path(Z, Y).
    rx, ry, rz = Var(), Var(), Var()
    db.assertz(Clause(
        head=Compound("path", (rx, ry)),
        body=[
            Call(func=LoadName(name="edge"), args=[rx, rz], kwargs=[]),
            Call(func=LoadName(name="path"), args=[rz, ry], kwargs=[]),
        ],
    ))
    compile_predicate_trampoline("path", 2, db.clauses_for("path", 2), db)

    return mod


def _make_member_module() -> Module:
    """Module with member/2: member(X, [X|_]) and member(X, [_|T]) :- member(X, T)."""
    mod = Module("test_member")
    db = mod.db

    # member(X, [X | _Rest]) :- true.
    x1, rest1 = Var(), Var()
    db.assertz(Clause(
        head=Compound("member", (x1, [x1, rest1])),
        body=[],
    ))

    # Use In/2 (simpler for testing without list patterns)
    # Actually let's use a simpler approach: member via In
    # member(X, L) :- X in L
    x2, l2 = Var(), Var()
    db.assertz(Clause(
        head=Compound("member2", (x2, l2)),
        body=[In(left=x2, right=l2)],
    ))
    compile_predicate_trampoline("member2", 2, db.clauses_for("member2", 2), db)

    return mod


def _make_arith_module() -> Module:
    """Module with lt_check/2: lt_check(X, Y) :- X < Y."""
    mod = Module("test_arith")
    db = mod.db

    x, y = Var(), Var()
    db.assertz(Clause(
        head=Compound("lt_check", (x, y)),
        body=[Lt(left=x, right=y)],
    ))
    compile_predicate_trampoline("lt_check", 2, db.clauses_for("lt_check", 2), db)

    return mod


# ── call() tests ───────────────────────────────────────────────────────────────


class TestCall:
    def test_call_edge_direct(self):
        mod = _make_edge_module()
        x = Var()
        results = [deref(x) for _ in call("edge", "a", x, module=mod)]
        assert results == ["b"]

    def test_call_edge_multiple_sources(self):
        mod = _make_edge_module()
        x = Var()
        results = [deref(x) for _ in call("edge", "b", x, module=mod)]
        assert set(results) == {"c", "d"}

    def test_call_path_reachable_from_a(self):
        mod = _make_edge_module()
        y = Var()
        results = [deref(y) for _ in call("path", "a", y, module=mod)]
        assert set(results) == {"b", "c", "d"}

    def test_call_path_ground_success(self):
        mod = _make_edge_module()
        results = list(call("path", "a", "d", module=mod))
        assert len(results) >= 1  # multiple paths a→d

    def test_call_path_ground_failure(self):
        mod = _make_edge_module()
        results = list(call("path", "d", "a", module=mod))  # no back-edge
        assert results == []

    def test_call_unknown_predicate_raises(self):
        mod = _make_edge_module()
        with pytest.raises(KeyError):
            list(call("unknown", "x", module=mod))

    def test_call_yields_trail(self):
        mod = _make_edge_module()
        x = Var()
        trails = list(call("edge", "a", x, module=mod))
        assert len(trails) == 1
        assert isinstance(trails[0], Trail)

    def test_call_uses_provided_trail(self):
        """Bindings are live inside the iterator (try/finally undoes on exit)."""
        mod = _make_edge_module()
        x = Var()
        t = Trail()
        seen = []
        for _ in call("edge", "a", x, module=mod, trail=t):
            seen.append(deref(x))
        assert seen == ["b"]

    def test_call_member2_via_in(self):
        mod = _make_member_module()
        x = Var()
        results = [deref(x) for _ in call("member2", x, [1, 2, 3], module=mod)]
        assert results == [1, 2, 3]

    def test_call_lt_check_pass(self):
        mod = _make_arith_module()
        results = list(call("lt_check", 3, 5, module=mod))
        assert len(results) == 1

    def test_call_lt_check_fail(self):
        mod = _make_arith_module()
        results = list(call("lt_check", 5, 3, module=mod))
        assert results == []


# ── solve() tests ─────────────────────────────────────────────────────────────


class TestSolve:
    def test_solve_call_goal(self):
        mod = _make_edge_module()
        x = Var()
        goal = Call(func=LoadName(name="edge"), args=["a", x], kwargs=[])
        results = [deref(x) for _ in solve(goal, mod)]
        assert results == ["b"]

    def test_solve_and_goal(self):
        mod = _make_edge_module()
        x, y = Var(), Var()
        goal = And(
            left=Call(func=LoadName(name="edge"), args=["a", x], kwargs=[]),
            right=Call(func=LoadName(name="edge"), args=[x, y], kwargs=[]),
        )
        results = [(deref(x), deref(y)) for _ in solve(goal, mod)]
        # a→b, b→c and b→d
        assert set(results) == {("b", "c"), ("b", "d")}

    def test_solve_true_goal(self):
        mod = _make_edge_module()
        results = list(solve(True, mod))
        assert len(results) == 1

    def test_solve_false_goal(self):
        mod = _make_edge_module()
        results = list(solve(False, mod))
        assert results == []

    def test_solve_is_goal(self):
        mod = _make_edge_module()
        x = Var()
        goal = Is(left=x, right=42)
        results = [deref(x) for _ in solve(goal, mod)]
        assert results == [42]

    def test_solve_or_goal(self):
        mod = _make_edge_module()
        x = Var()
        goal = Or(
            left=Is(left=x, right="hello"),
            right=Is(left=x, right="world"),
        )
        results = [deref(x) for _ in solve(goal, mod)]
        assert results == ["hello", "world"]

    def test_solve_not_goal_success(self):
        mod = _make_edge_module()
        # not(False) → succeed once
        results = list(solve(Not(operand=False), mod))
        assert len(results) == 1

    def test_solve_not_goal_failure(self):
        mod = _make_edge_module()
        # not(True) → fail
        results = list(solve(Not(operand=True), mod))
        assert results == []

    def test_solve_yields_trail(self):
        mod = _make_edge_module()
        x = Var()
        goal = Is(left=x, right=99)
        trails = list(solve(goal, mod))
        assert len(trails) == 1
        assert isinstance(trails[0], Trail)

    def test_solve_multiple_solutions_backtrack(self):
        mod = _make_edge_module()
        x = Var()
        goal = Call(func=LoadName(name="path"), args=["a", x], kwargs=[])
        results = [deref(x) for _ in solve(goal, mod)]
        assert set(results) == {"b", "c", "d"}

    def test_module_solve_method(self):
        """Module.solve delegates to solve()."""
        mod = _make_edge_module()
        x = Var()
        goal = Call(func=LoadName(name="edge"), args=["a", x], kwargs=[])
        results = [deref(x) for _ in mod.solve(goal)]
        assert results == ["b"]


# ── query() tests ─────────────────────────────────────────────────────────────


class TestQuery:
    def test_query_single_var(self):
        mod = _make_edge_module()
        x = Var()
        goal = Call(func=LoadName(name="edge"), args=["a", x], kwargs=[])
        results = list(query(goal, {"X": x}, mod))
        assert results == [{"X": "b"}]

    def test_query_multiple_solutions(self):
        mod = _make_edge_module()
        x = Var()
        goal = Call(func=LoadName(name="edge"), args=["b", x], kwargs=[])
        results = list(query(goal, {"X": x}, mod))
        assert {r["X"] for r in results} == {"c", "d"}

    def test_query_two_vars(self):
        mod = _make_edge_module()
        x, y = Var(), Var()
        goal = And(
            left=Call(func=LoadName(name="edge"), args=["a", x], kwargs=[]),
            right=Call(func=LoadName(name="edge"), args=[x, y], kwargs=[]),
        )
        results = list(query(goal, {"X": x, "Y": y}, mod))
        xy = {(r["X"], r["Y"]) for r in results}
        assert xy == {("b", "c"), ("b", "d")}

    def test_query_failure_yields_nothing(self):
        mod = _make_edge_module()
        x = Var()
        goal = Call(func=LoadName(name="edge"), args=["z", x], kwargs=[])
        results = list(query(goal, {"X": x}, mod))
        assert results == []

    def test_query_unbound_var_stays_var(self):
        """An unbound Var in variables dict appears as a Var in the result."""
        mod = _make_edge_module()
        x, y = Var(), Var()
        # Only bind x; y stays unbound
        goal = Is(left=x, right="hello")
        results = list(query(goal, {"X": x, "Y": y}, mod))
        assert len(results) == 1
        assert results[0]["X"] == "hello"
        from clausal.logic.variables import is_var
        assert is_var(results[0]["Y"])


# ── once() tests ──────────────────────────────────────────────────────────────


class TestOnce:
    def test_once_success(self):
        """once returns the Trail (bindings undone after generator exits, but
        the Trail object itself is returned so the caller has a reference)."""
        mod = _make_edge_module()
        x = Var()
        goal = Call(func=LoadName(name="edge"), args=["a", x], kwargs=[])
        trail = once(goal, mod)
        assert trail is not None
        assert isinstance(trail, Trail)

    def test_once_failure_returns_none(self):
        mod = _make_edge_module()
        x = Var()
        goal = Call(func=LoadName(name="edge"), args=["z", x], kwargs=[])
        result = once(goal, mod)
        assert result is None

    def test_once_only_first_solution(self):
        """once returns non-None on success (b has two outgoing edges but only first fires)."""
        mod = _make_edge_module()
        x = Var()
        goal = Call(func=LoadName(name="edge"), args=["b", x], kwargs=[])
        trail = once(goal, mod)
        # Bindings are live only inside the generator (try/finally undoes them on exit).
        # once() returning non-None confirms there was at least one solution.
        assert trail is not None

    def test_once_true_succeeds(self):
        mod = _make_edge_module()
        result = once(True, mod)
        assert result is not None

    def test_once_false_fails(self):
        mod = _make_edge_module()
        result = once(False, mod)
        assert result is None


# ── _deref_walk() tests ───────────────────────────────────────────────────────


class TestDerefWalk:
    def test_scalar(self):
        assert _deref_walk(42) == 42
        assert _deref_walk("hello") == "hello"
        assert _deref_walk(None) is None
        assert _deref_walk(True) is True

    def test_unbound_var(self):
        v = Var()
        result = _deref_walk(v)
        from clausal.logic.variables import is_var
        assert is_var(result)

    def test_bound_var(self):
        v = Var()
        t = Trail()
        from clausal.logic.variables import unify
        unify(v, 42, t)
        assert _deref_walk(v) == 42

    def test_list(self):
        v = Var()
        t = Trail()
        from clausal.logic.variables import unify
        unify(v, "x", t)
        assert _deref_walk([1, v, 3]) == [1, "x", 3]

    def test_compound(self):
        v = Var()
        t = Trail()
        from clausal.logic.variables import unify
        unify(v, 99, t)
        c = Compound("foo", (1, v, "bar"))
        result = _deref_walk(c)
        assert result == Compound("foo", (1, 99, "bar"))

    def test_nested(self):
        v = Var()
        t = Trail()
        from clausal.logic.variables import unify
        unify(v, [1, 2, 3], t)
        result = _deref_walk(v)
        assert result == [1, 2, 3]
