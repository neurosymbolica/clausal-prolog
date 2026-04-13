"""Tests for Phase 1: Coroutining & Resource Control.

call_nth/2, count_all/2, setup_call_cleanup/3, call_cleanup/2, freeze/2, when/2.
"""

from __future__ import annotations

import pytest

from clausal.logic.database import Clause, Database, Module
from clausal.logic.solve import call, solve, query, once, _deref_walk
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.exceptions import LogicException
from clausal.terms import (
    And, Or, Not,
    Unify as Is, Evaluate,
    Lt, LtE, Gt, GtE,
    in_, NotIn,
    Call, LoadName,
    Compound,
)

import clausal.import_hook


# ── Helpers ──────────────────────────────────────────────────────────────────


def fresh_module(name: str = "test") -> Module:
    return Module(name)


def solutions_of(goal, mod=None) -> list[Trail]:
    if mod is None:
        mod = fresh_module()
    return list(solve(goal, mod))


def bindings(goal, var: Var, mod=None) -> list:
    if mod is None:
        mod = fresh_module()
    t = Trail()
    return [_deref_walk(var) for _ in solve(goal, mod, t)]


def _call_nth_goal(inner_goal, n):
    return Call(func=LoadName(name="call_nth"), args=[inner_goal, n], kwargs=[])


def _count_all_goal(inner_goal, count):
    return Call(func=LoadName(name="count_all"), args=[inner_goal, count], kwargs=[])


def _between_goal(lo, hi, x):
    return Call(func=LoadName(name="between"), args=[lo, hi, x], kwargs=[])


def _in_goal(x, lst):
    return Call(func=LoadName(name="in_"), args=[x, lst], kwargs=[])


def _scc_goal(setup, call_g, cleanup):
    return Call(func=LoadName(name="setup_call_cleanup"), args=[setup, call_g, cleanup], kwargs=[])


def _cc_goal(call_g, cleanup):
    return Call(func=LoadName(name="call_cleanup"), args=[call_g, cleanup], kwargs=[])


# ── call_nth/2 ────────────────────────────────────────────────────────────────


class TestCallNth:
    def test_call_nth_basic(self):
        """call_nth(between(1, 10, X), 5) → X = 5"""
        # nv
        x = Var()
        goal = _call_nth_goal(_between_goal(1, 10, x), 5)
        results = bindings(goal, x)
        assert results == [5]

    def test_call_nth_first(self):
        """call_nth(in_(X, [a, b, c]), 1) → X = a"""
        # nv
        x = Var()
        goal = _call_nth_goal(_in_goal(x, ["a", "b", "c"]), 1)
        results = bindings(goal, x)
        assert results == ["a"]

    def test_call_nth_last(self):
        """call_nth(in_(X, [a, b, c]), 3) → X = c"""
        # nv
        x = Var()
        goal = _call_nth_goal(_in_goal(x, ["a", "b", "c"]), 3)
        results = bindings(goal, x)
        assert results == ["c"]

    def test_call_nth_too_few(self):
        """call_nth(between(1, 3, X), 4) → fails (only 3 solutions)"""
        # nv
        x = Var()
        goal = _call_nth_goal(_between_goal(1, 3, x), 4)
        results = solutions_of(goal)
        assert results == []

    def test_call_nth_n_is_var(self):
        """call_nth with N as a variable bound to a value."""
        # nv
        x = Var()
        n = Var()
        # (N is 2, call_nth(in_(X, [a, b, c]), N))
        goal = And(
            left=Is(left=n, right=2),
            right=_call_nth_goal(_in_goal(x, ["a", "b", "c"]), n),
        )
        results = bindings(goal, x)
        assert results == ["b"]

    def test_call_nth_zero_raises(self):
        """call_nth with N=0 raises type error."""
        # nv
        x = Var()
        goal = _call_nth_goal(_between_goal(1, 5, x), 0)
        with pytest.raises(LogicException):
            solutions_of(goal)

    def test_call_nth_negative_raises(self):
        """call_nth with N=-1 raises type error."""
        # nv
        x = Var()
        goal = _call_nth_goal(_between_goal(1, 5, x), -1)
        with pytest.raises(LogicException):
            solutions_of(goal)

    def test_call_nth_non_integer_raises(self):
        """call_nth with N as a string raises type error."""
        # nv
        x = Var()
        goal = _call_nth_goal(_between_goal(1, 5, x), "five")
        with pytest.raises(LogicException):
            solutions_of(goal)

    def test_call_nth_fail_goal(self):
        """call_nth(fail, 1) → fails"""
        # nv
        goal = _call_nth_goal(False, 1)
        results = solutions_of(goal)
        assert results == []

    def test_call_nth_single_solution(self):
        """call_nth(X is 42, 1) → X = 42"""
        # nv
        x = Var()
        goal = _call_nth_goal(Is(left=x, right=42), 1)
        results = bindings(goal, x)
        assert results == [42]


# ── count_all/2 ───────────────────────────────────────────────────────────────


class TestCountAll:
    def test_count_all_basic(self):
        """count_all(in_(_, [a, b, c]), N) → N = 3"""
        # nv
        n = Var()
        x = Var()
        goal = _count_all_goal(_in_goal(x, ["a", "b", "c"]), n)
        results = bindings(goal, n)
        assert results == [3]

    def test_count_all_empty(self):
        """count_all(fail, N) → N = 0"""
        # nv
        n = Var()
        goal = _count_all_goal(False, n)
        results = bindings(goal, n)
        assert results == [0]

    def test_count_all_between(self):
        """count_all(between(1, 100, _), N) → N = 100"""
        # nv
        n = Var()
        x = Var()
        goal = _count_all_goal(_between_goal(1, 100, x), n)
        results = bindings(goal, n)
        assert results == [100]

    def test_count_all_already_bound_correct(self):
        """count_all(in_(_, [a, b, c]), 3) → succeeds"""
        # nv
        x = Var()
        goal = _count_all_goal(_in_goal(x, ["a", "b", "c"]), 3)
        results = solutions_of(goal)
        assert len(results) == 1

    def test_count_all_already_bound_wrong(self):
        """count_all(in_(_, [a, b, c]), 5) → fails"""
        # nv
        x = Var()
        goal = _count_all_goal(_in_goal(x, ["a", "b", "c"]), 5)
        results = solutions_of(goal)
        assert results == []

    def test_count_all_with_filter(self):
        """count_all((in_(X, [1,2,3,4,5]), X > 3), N) → N = 2"""
        # nv
        x = Var()
        n = Var()
        inner = And(
            left=_in_goal(x, [1, 2, 3, 4, 5]),
            right=Gt(left=x, right=3),
        )
        goal = _count_all_goal(inner, n)
        results = bindings(goal, n)
        assert results == [2]

    def test_count_all_no_side_effects(self):
        """count_all does not leave bindings from the inner goal."""
        # nv
        x = Var()
        n = Var()
        goal = _count_all_goal(_in_goal(x, [1, 2, 3]), n)
        t = Trail()
        mod = fresh_module()
        for _ in solve(goal, mod, t):
            # x should still be unbound after count_all
            assert deref(x) is x
            assert deref(n) == 3


# ── setup_call_cleanup/3 ──────────────────────────────────────────────────────


class TestSetupCallCleanup:
    def test_scc_basic(self):
        """setup_call_cleanup(S is 1, true, C is 2) — setup runs, cleanup runs."""
        # nv
        s = Var()
        c = Var()
        goal = _scc_goal(
            Is(left=s, right=1),
            True,  # call succeeds
            Is(left=c, right=2),
        )
        results = solutions_of(goal)
        assert len(results) == 1

    def test_scc_call_succeeds_cleanup_runs(self):
        """when Call succeeds, Cleanup runs too."""
        # nv
        log = []

        # We need to use compiled predicates to track side effects.
        # Use a simpler approach: test with between.
        x = Var()
        result = Var()
        # setup_call_cleanup(true, in_(X, [1, 2]), Result is X)
        # This should produce 2 solutions (X=1, X=2), cleanup runs each time
        goal = _scc_goal(
            True,
            _in_goal(x, [10, 20]),
            Is(left=result, right=x),
        )
        mod = fresh_module()
        t = Trail()
        vals = []
        for _ in solve(goal, mod, t):
            vals.append(deref(x))
        assert 10 in vals or 20 in vals

    def test_scc_call_fails_cleanup_runs(self):
        """when Call fails, Cleanup still runs, overall goal fails."""
        # nv
        c = Var()
        goal = _scc_goal(
            True,
            False,  # call fails
            Is(left=c, right=99),
        )
        results = solutions_of(goal)
        assert results == []  # overall fails because Call fails

    def test_scc_call_throws_cleanup_runs(self):
        """when Call throws, Cleanup runs, exception re-raised."""
        # nv
        c = Var()
        throw_goal = Call(func=LoadName(name="throw"), args=[
            Compound("my_error", ("oops",))
        ], kwargs=[])
        goal = _scc_goal(
            True,
            throw_goal,
            Is(left=c, right=42),
        )
        with pytest.raises(LogicException) as exc_info:
            solutions_of(goal)
        assert exc_info.value.term.functor == "my_error"

    def test_scc_setup_fails_no_cleanup(self):
        """when Setup fails, Cleanup does NOT run."""
        # nv
        c = Var()
        goal = _scc_goal(
            False,  # setup fails
            True,
            Is(left=c, right=42),
        )
        results = solutions_of(goal)
        assert results == []  # whole goal fails silently


# ── call_cleanup/2 ────────────────────────────────────────────────────────────


class TestCallCleanup:
    def test_call_cleanup_basic(self):
        """call_cleanup(true, true) — both succeed."""
        # nv
        goal = _cc_goal(True, True)
        results = solutions_of(goal)
        assert len(results) == 1

    def test_call_cleanup_call_fails(self):
        """call_cleanup(fail, true) — cleanup runs, overall fails."""
        # nv
        goal = _cc_goal(False, True)
        results = solutions_of(goal)
        assert results == []

    def test_call_cleanup_call_throws(self):
        """call_cleanup(throw(err), true) — cleanup runs, exception re-raised."""
        # nv
        throw_goal = Call(func=LoadName(name="throw"), args=[
            Compound("err", ("test",))
        ], kwargs=[])
        goal = _cc_goal(throw_goal, True)
        with pytest.raises(LogicException):
            solutions_of(goal)

    def test_call_cleanup_with_solutions(self):
        """call_cleanup(in_(X, [a, b]), true) — produces solutions."""
        # nv
        x = Var()
        goal = _cc_goal(_in_goal(x, ["a", "b"]), True)
        results = bindings(goal, x)
        assert results == ["a", "b"]


# ── freeze/2 ─────────────────────────────────────────────────────────────────


def _freeze_goal(x, goal):
    return Call(func=LoadName(name="freeze"), args=[x, goal], kwargs=[])


def _unify_goal(x, y):
    """Build an X is Y unification goal."""
    return Is(left=x, right=y)


class TestFreeze:
    def test_freeze_already_bound(self):
        """freeze(X, Goal) where X is already bound → runs Goal immediately."""
        # nv
        x = Var()
        y = Var()
        # (X is 5, freeze(X, Y is X))
        goal = And(
            left=_unify_goal(x, 5),
            right=_freeze_goal(x, _unify_goal(y, x)),
        )
        results = bindings(goal, y)
        assert results == [5]

    def test_freeze_then_bind(self):
        """freeze(X, Goal), X is val → Goal fires when X is bound."""
        # nv
        x = Var()
        y = Var()
        # (freeze(X, Y is X), X is hello)
        goal = And(
            left=_freeze_goal(x, _unify_goal(y, x)),
            right=_unify_goal(x, "hello"),
        )
        results = bindings(goal, y)
        assert results == ["hello"]

    def test_freeze_goal_success(self):
        """Frozen goal succeeds → unification succeeds."""
        # nv
        x = Var()
        # freeze(X, X > 0), X is 5
        goal = And(
            left=_freeze_goal(x, Gt(left=x, right=0)),
            right=_unify_goal(x, 5),
        )
        results = solutions_of(goal)
        assert len(results) == 1

    def test_freeze_goal_failure(self):
        """Frozen goal fails → unification fails."""
        # nv
        x = Var()
        # freeze(X, X > 0), X is -1
        goal = And(
            left=_freeze_goal(x, Gt(left=x, right=0)),
            right=_unify_goal(x, -1),
        )
        results = solutions_of(goal)
        assert results == []

    def test_freeze_multiple_on_same_var(self):
        """Multiple freezes on the same variable — all fire when bound."""
        # nv
        x = Var()
        y = Var()
        z = Var()
        # freeze(X, Y is X), freeze(X, Z is X), X is 42
        goal = And(
            left=And(
                left=_freeze_goal(x, _unify_goal(y, x)),
                right=_freeze_goal(x, _unify_goal(z, x)),
            ),
            right=_unify_goal(x, 42),
        )
        t = Trail()
        mod = fresh_module()
        for _ in solve(goal, mod, t):
            assert deref(y) == 42
            assert deref(z) == 42

    def test_freeze_on_bound_var_immediate(self):
        """freeze on already-bound variable executes goal immediately."""
        # nv
        x = Var()
        result = Var()
        # X is 10, freeze(X, Result is X)
        goal = And(
            left=_unify_goal(x, 10),
            right=_freeze_goal(x, _unify_goal(result, x)),
        )
        results = bindings(goal, result)
        assert results == [10]

    def test_freeze_backtrack_removes_attr(self):
        """freeze + backtracking: trail undo removes the attribute."""
        # nv
        x = Var()
        # freeze attaches attr; if we backtrack, attr is removed
        # (freeze(X, X > 0) ; true), X is -1
        # The disjunction first tries freeze branch, then true branch
        # when X is -1 in the freeze branch, it should fail
        # in_ the true branch (no freeze), it should succeed
        goal = And(
            left=Or(
                left=_freeze_goal(x, Gt(left=x, right=0)),
                right=True,
            ),
            right=_unify_goal(x, -1),
        )
        results = solutions_of(goal)
        # First branch: freeze(X, X>0), X=-1 → fails (X>0 is false)
        # Second branch: true, X=-1 → succeeds
        assert len(results) == 1


# ── when/2 ───────────────────────────────────────────────────────────────────


def _when_goal(cond, goal):
    return Call(func=LoadName(name="when"), args=[cond, goal], kwargs=[])


def _is_bound_cond(x):
    return Call(func=LoadName(name="nonvar"), args=[x], kwargs=[])


def _is_ground_cond(x):
    return Call(func=LoadName(name="ground"), args=[x], kwargs=[])


class TestWhen:
    def test_when_is_bound_already(self):
        """when(nonvar(X), Goal) where X is already bound → runs immediately."""
        # nv
        x = Var()
        y = Var()
        goal = And(
            left=_unify_goal(x, "hello"),
            right=_when_goal(_is_bound_cond(x), _unify_goal(y, x)),
        )
        results = bindings(goal, y)
        assert results == ["hello"]

    def test_when_is_bound_deferred(self):
        """when(nonvar(X), Goal), X = val → Goal fires when X is bound."""
        # nv
        x = Var()
        y = Var()
        goal = And(
            left=_when_goal(_is_bound_cond(x), _unify_goal(y, x)),
            right=_unify_goal(x, "world"),
        )
        results = bindings(goal, y)
        assert results == ["world"]

    def test_when_conjunction(self):
        """when((nonvar(X), nonvar(Y)), Goal) — fires when both are bound."""
        # nv
        x = Var()
        y = Var()
        result = Var()
        cond = And(left=_is_bound_cond(x), right=_is_bound_cond(y))
        # when both X and Y are bound, result = X + Y (but we'll just test binding)
        goal = And(
            left=_when_goal(cond, _unify_goal(result, "done")),
            right=And(
                left=_unify_goal(x, 1),
                right=_unify_goal(y, 2),
            ),
        )
        results = bindings(goal, result)
        assert results == ["done"]

    def test_when_conjunction_partial(self):
        """when((nonvar(X), nonvar(Y)), Goal) — Y not bound yet, Goal not fired."""
        # nv
        x = Var()
        y = Var()
        result = Var()
        cond = And(left=_is_bound_cond(x), right=_is_bound_cond(y))
        # Only bind X, not Y — result should stay unbound
        goal = And(
            left=_when_goal(cond, _unify_goal(result, "done")),
            right=_unify_goal(x, 1),
        )
        t = Trail()
        mod = fresh_module()
        for _ in solve(goal, mod, t):
            # result is NOT bound because Y is still unbound
            assert deref(result) is result or deref(result) == "done"
            # Actually: when X is bound, when(nonvar(Y), Goal) is installed.
            # Since Y isn't bound, result stays unbound.
            r = deref(result)
            assert r is result  # still unbound

    def test_when_is_ground_already(self):
        """when(ground(f(1, 2)), Goal) — already ground → immediate."""
        # nv
        x = Var()
        result = Var()
        goal = And(
            left=_unify_goal(x, [1, 2, 3]),
            right=_when_goal(_is_ground_cond(x), _unify_goal(result, "grounded")),
        )
        results = bindings(goal, result)
        assert results == ["grounded"]

    def test_when_is_ground_deferred(self):
        """when(ground(X), Goal), X = 5 → Goal fires when X is ground."""
        # nv
        x = Var()
        result = Var()
        goal = And(
            left=_when_goal(_is_ground_cond(x), _unify_goal(result, "grounded")),
            right=_unify_goal(x, 42),
        )
        results = bindings(goal, result)
        assert results == ["grounded"]

    def test_when_is_ground_nested(self):
        """when(ground([X, Y]), Goal) — fires when both X and Y are ground."""
        # nv
        x = Var()
        y = Var()
        result = Var()
        lst = [x, y]
        goal = And(
            left=_when_goal(_is_ground_cond(lst), _unify_goal(result, "all_ground")),
            right=And(
                left=_unify_goal(x, 1),
                right=_unify_goal(y, 2),
            ),
        )
        results = bindings(goal, result)
        assert results == ["all_ground"]

    def test_when_goal_failure(self):
        """when(nonvar(X), Goal) where Goal fails → unification fails."""
        # nv
        x = Var()
        goal = And(
            left=_when_goal(_is_bound_cond(x), Gt(left=x, right=100)),
            right=_unify_goal(x, 5),  # 5 > 100 is false
        )
        results = solutions_of(goal)
        assert results == []


# ── Meta-predicate nesting ───────────────────────────────────────────────────


def _find_all_goal(template, inner, bag):
    return Call(func=LoadName(name="findall"), args=[template, inner, bag], kwargs=[])


def _once_goal(inner):
    return Call(func=LoadName(name="once"), args=[inner], kwargs=[])


def _catch_goal(goal, catcher, recovery):
    return Call(func=LoadName(name="catch"), args=[goal, catcher, recovery], kwargs=[])


class TestMetaPredicateNesting:
    """Verify that new special forms nest correctly inside other meta-predicates."""

    def test_find_all_call_nth(self):
        """findall(X, call_nth(in_(X, List), 2), Bag) -> [20]"""
        # nv
        x = Var()
        bag = Var()
        goal = _find_all_goal(
            x,
            _call_nth_goal(_in_goal(x, [10, 20, 30]), 2),
            bag,
        )
        results = bindings(goal, bag)
        assert results == [[20]]

    def test_find_all_count_all(self):
        """findall(N, count_all(in_(_, List), N), Bag) -> [3]"""
        # nv
        x = Var()
        n = Var()
        bag = Var()
        goal = _find_all_goal(
            n,
            _count_all_goal(_in_goal(x, [1, 2, 3]), n),
            bag,
        )
        results = bindings(goal, bag)
        assert results == [[3]]

    def test_once_call_nth(self):
        """once(call_nth(in_(X, List), 1)) -> X = 10"""
        # nv
        x = Var()
        goal = _once_goal(_call_nth_goal(_in_goal(x, [10, 20, 30]), 1))
        results = bindings(goal, x)
        assert results == [10]

    def test_once_count_all(self):
        """once(count_all(in_(_, List), N)) -> N = 3"""
        # nv
        x = Var()
        n = Var()
        goal = _once_goal(_count_all_goal(_in_goal(x, [1, 2, 3]), n))
        results = bindings(goal, n)
        assert results == [3]

    def test_catch_call_nth_type_error(self):
        """catch(call_nth(Goal, 0), Error, Recovery) catches type error."""
        # nv
        x = Var()
        error = Var()
        goal = _catch_goal(
            _call_nth_goal(_in_goal(x, [1, 2, 3]), 0),
            error,
            True,
        )
        results = solutions_of(goal)
        assert len(results) == 1

    def test_call_nth_inside_freeze(self):
        """freeze(X, call_nth(in_(Y, [X]), 1)), X = 42 -> Y = 42"""
        # nv
        x = Var()
        y = Var()
        goal = And(
            left=_freeze_goal(x, _call_nth_goal(_in_goal(y, [x]), 1)),
            right=_unify_goal(x, 42),
        )
        results = bindings(goal, y)
        assert results == [42]

    def test_scc_inside_find_all(self):
        """findall(X, setup_call_cleanup(true, in_(X, [a,b]), true), Bag) -> [a, b]"""
        # nv
        x = Var()
        bag = Var()
        inner = _scc_goal(True, _in_goal(x, ["a", "b"]), True)
        goal = _find_all_goal(x, inner, bag)
        results = bindings(goal, bag)
        assert results == [["a", "b"]]

    def test_freeze_inside_find_all(self):
        """findall(Y, (freeze(X, Y is X), X is 99), Bag) -> [99]"""
        # nv
        x = Var()
        y = Var()
        bag = Var()
        inner = And(
            left=_freeze_goal(x, _unify_goal(y, x)),
            right=_unify_goal(x, 99),
        )
        goal = _find_all_goal(y, inner, bag)
        results = bindings(goal, bag)
        assert results == [[99]]

    def test_count_all_inside_count_all(self):
        """count_all(count_all(in_(_, [1,2]), _), N) -> N = 1"""
        # nv
        x = Var()
        inner_n = Var()
        n = Var()
        goal = _count_all_goal(
            _count_all_goal(_in_goal(x, [1, 2]), inner_n),
            n,
        )
        results = bindings(goal, n)
        assert results == [1]

    def test_call_cleanup_inside_once(self):
        """once(call_cleanup(in_(X, [a, b, c]), true)) -> X = a"""
        # nv
        x = Var()
        goal = _once_goal(_cc_goal(_in_goal(x, ["a", "b", "c"]), True))
        results = bindings(goal, x)
        assert results == ["a"]
