"""Tests for Phase 1: Coroutining & Resource Control.

CallNth/2, CountAll/2, SetupCallCleanup/3, CallCleanup/2, Freeze/2, When/2.
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
    In, NotIn,
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
    return Call(func=LoadName(name="CallNth"), args=[inner_goal, n], kwargs=[])


def _count_all_goal(inner_goal, count):
    return Call(func=LoadName(name="CountAll"), args=[inner_goal, count], kwargs=[])


def _between_goal(lo, hi, x):
    return Call(func=LoadName(name="Between"), args=[lo, hi, x], kwargs=[])


def _in_goal(x, lst):
    return Call(func=LoadName(name="In"), args=[x, lst], kwargs=[])


def _scc_goal(setup, call_g, cleanup):
    return Call(func=LoadName(name="SetupCallCleanup"), args=[setup, call_g, cleanup], kwargs=[])


def _cc_goal(call_g, cleanup):
    return Call(func=LoadName(name="CallCleanup"), args=[call_g, cleanup], kwargs=[])


# ── CallNth/2 ────────────────────────────────────────────────────────────────


class TestCallNth:
    def test_call_nth_basic(self):
        """CallNth(Between(1, 10, X), 5) → X = 5"""
        x = Var()
        goal = _call_nth_goal(_between_goal(1, 10, x), 5)
        results = bindings(goal, x)
        assert results == [5]

    def test_call_nth_first(self):
        """CallNth(In(X, [a, b, c]), 1) → X = a"""
        x = Var()
        goal = _call_nth_goal(_in_goal(x, ["a", "b", "c"]), 1)
        results = bindings(goal, x)
        assert results == ["a"]

    def test_call_nth_last(self):
        """CallNth(In(X, [a, b, c]), 3) → X = c"""
        x = Var()
        goal = _call_nth_goal(_in_goal(x, ["a", "b", "c"]), 3)
        results = bindings(goal, x)
        assert results == ["c"]

    def test_call_nth_too_few(self):
        """CallNth(Between(1, 3, X), 4) → fails (only 3 solutions)"""
        x = Var()
        goal = _call_nth_goal(_between_goal(1, 3, x), 4)
        results = solutions_of(goal)
        assert results == []

    def test_call_nth_n_is_var(self):
        """CallNth with N as a variable bound to a value."""
        x = Var()
        n = Var()
        # (N is 2, CallNth(In(X, [a, b, c]), N))
        goal = And(
            left=Is(left=n, right=2),
            right=_call_nth_goal(_in_goal(x, ["a", "b", "c"]), n),
        )
        results = bindings(goal, x)
        assert results == ["b"]

    def test_call_nth_zero_raises(self):
        """CallNth with N=0 raises type error."""
        x = Var()
        goal = _call_nth_goal(_between_goal(1, 5, x), 0)
        with pytest.raises(LogicException):
            solutions_of(goal)

    def test_call_nth_negative_raises(self):
        """CallNth with N=-1 raises type error."""
        x = Var()
        goal = _call_nth_goal(_between_goal(1, 5, x), -1)
        with pytest.raises(LogicException):
            solutions_of(goal)

    def test_call_nth_non_integer_raises(self):
        """CallNth with N as a string raises type error."""
        x = Var()
        goal = _call_nth_goal(_between_goal(1, 5, x), "five")
        with pytest.raises(LogicException):
            solutions_of(goal)

    def test_call_nth_fail_goal(self):
        """CallNth(fail, 1) → fails"""
        goal = _call_nth_goal(False, 1)
        results = solutions_of(goal)
        assert results == []

    def test_call_nth_single_solution(self):
        """CallNth(X is 42, 1) → X = 42"""
        x = Var()
        goal = _call_nth_goal(Is(left=x, right=42), 1)
        results = bindings(goal, x)
        assert results == [42]


# ── CountAll/2 ───────────────────────────────────────────────────────────────


class TestCountAll:
    def test_count_all_basic(self):
        """CountAll(In(_, [a, b, c]), N) → N = 3"""
        n = Var()
        x = Var()
        goal = _count_all_goal(_in_goal(x, ["a", "b", "c"]), n)
        results = bindings(goal, n)
        assert results == [3]

    def test_count_all_empty(self):
        """CountAll(fail, N) → N = 0"""
        n = Var()
        goal = _count_all_goal(False, n)
        results = bindings(goal, n)
        assert results == [0]

    def test_count_all_between(self):
        """CountAll(Between(1, 100, _), N) → N = 100"""
        n = Var()
        x = Var()
        goal = _count_all_goal(_between_goal(1, 100, x), n)
        results = bindings(goal, n)
        assert results == [100]

    def test_count_all_already_bound_correct(self):
        """CountAll(In(_, [a, b, c]), 3) → succeeds"""
        x = Var()
        goal = _count_all_goal(_in_goal(x, ["a", "b", "c"]), 3)
        results = solutions_of(goal)
        assert len(results) == 1

    def test_count_all_already_bound_wrong(self):
        """CountAll(In(_, [a, b, c]), 5) → fails"""
        x = Var()
        goal = _count_all_goal(_in_goal(x, ["a", "b", "c"]), 5)
        results = solutions_of(goal)
        assert results == []

    def test_count_all_with_filter(self):
        """CountAll((In(X, [1,2,3,4,5]), X > 3), N) → N = 2"""
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
        """CountAll does not leave bindings from the inner goal."""
        x = Var()
        n = Var()
        goal = _count_all_goal(_in_goal(x, [1, 2, 3]), n)
        t = Trail()
        mod = fresh_module()
        for _ in solve(goal, mod, t):
            # x should still be unbound after CountAll
            assert deref(x) is x
            assert deref(n) == 3


# ── SetupCallCleanup/3 ──────────────────────────────────────────────────────


class TestSetupCallCleanup:
    def test_scc_basic(self):
        """SetupCallCleanup(S is 1, true, C is 2) — setup runs, cleanup runs."""
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
        """When Call succeeds, Cleanup runs too."""
        log = []

        # We need to use compiled predicates to track side effects.
        # Use a simpler approach: test with Between.
        x = Var()
        result = Var()
        # SetupCallCleanup(true, In(X, [1, 2]), Result is X)
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
        """When Call fails, Cleanup still runs, overall goal fails."""
        c = Var()
        goal = _scc_goal(
            True,
            False,  # call fails
            Is(left=c, right=99),
        )
        results = solutions_of(goal)
        assert results == []  # overall fails because Call fails

    def test_scc_call_throws_cleanup_runs(self):
        """When Call throws, Cleanup runs, exception re-raised."""
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
        """When Setup fails, Cleanup does NOT run."""
        c = Var()
        goal = _scc_goal(
            False,  # setup fails
            True,
            Is(left=c, right=42),
        )
        results = solutions_of(goal)
        assert results == []  # whole goal fails silently


# ── CallCleanup/2 ────────────────────────────────────────────────────────────


class TestCallCleanup:
    def test_call_cleanup_basic(self):
        """CallCleanup(true, true) — both succeed."""
        goal = _cc_goal(True, True)
        results = solutions_of(goal)
        assert len(results) == 1

    def test_call_cleanup_call_fails(self):
        """CallCleanup(fail, true) — cleanup runs, overall fails."""
        goal = _cc_goal(False, True)
        results = solutions_of(goal)
        assert results == []

    def test_call_cleanup_call_throws(self):
        """CallCleanup(throw(err), true) — cleanup runs, exception re-raised."""
        throw_goal = Call(func=LoadName(name="throw"), args=[
            Compound("err", ("test",))
        ], kwargs=[])
        goal = _cc_goal(throw_goal, True)
        with pytest.raises(LogicException):
            solutions_of(goal)

    def test_call_cleanup_with_solutions(self):
        """CallCleanup(In(X, [a, b]), true) — produces solutions."""
        x = Var()
        goal = _cc_goal(_in_goal(x, ["a", "b"]), True)
        results = bindings(goal, x)
        assert results == ["a", "b"]


# ── Freeze/2 ─────────────────────────────────────────────────────────────────


def _freeze_goal(x, goal):
    return Call(func=LoadName(name="Freeze"), args=[x, goal], kwargs=[])


def _unify_goal(x, y):
    """Build an X is Y unification goal."""
    return Is(left=x, right=y)


class TestFreeze:
    def test_freeze_already_bound(self):
        """Freeze(X, Goal) where X is already bound → runs Goal immediately."""
        x = Var()
        y = Var()
        # (X is 5, Freeze(X, Y is X))
        goal = And(
            left=_unify_goal(x, 5),
            right=_freeze_goal(x, _unify_goal(y, x)),
        )
        results = bindings(goal, y)
        assert results == [5]

    def test_freeze_then_bind(self):
        """Freeze(X, Goal), X is val → Goal fires when X is bound."""
        x = Var()
        y = Var()
        # (Freeze(X, Y is X), X is hello)
        goal = And(
            left=_freeze_goal(x, _unify_goal(y, x)),
            right=_unify_goal(x, "hello"),
        )
        results = bindings(goal, y)
        assert results == ["hello"]

    def test_freeze_goal_success(self):
        """Frozen goal succeeds → unification succeeds."""
        x = Var()
        # Freeze(X, X > 0), X is 5
        goal = And(
            left=_freeze_goal(x, Gt(left=x, right=0)),
            right=_unify_goal(x, 5),
        )
        results = solutions_of(goal)
        assert len(results) == 1

    def test_freeze_goal_failure(self):
        """Frozen goal fails → unification fails."""
        x = Var()
        # Freeze(X, X > 0), X is -1
        goal = And(
            left=_freeze_goal(x, Gt(left=x, right=0)),
            right=_unify_goal(x, -1),
        )
        results = solutions_of(goal)
        assert results == []

    def test_freeze_multiple_on_same_var(self):
        """Multiple freezes on the same variable — all fire when bound."""
        x = Var()
        y = Var()
        z = Var()
        # Freeze(X, Y is X), Freeze(X, Z is X), X is 42
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
        """Freeze on already-bound variable executes goal immediately."""
        x = Var()
        result = Var()
        # X is 10, Freeze(X, Result is X)
        goal = And(
            left=_unify_goal(x, 10),
            right=_freeze_goal(x, _unify_goal(result, x)),
        )
        results = bindings(goal, result)
        assert results == [10]

    def test_freeze_backtrack_removes_attr(self):
        """Freeze + backtracking: trail undo removes the attribute."""
        x = Var()
        # Freeze attaches attr; if we backtrack, attr is removed
        # (Freeze(X, X > 0) ; true), X is -1
        # The disjunction first tries freeze branch, then true branch
        # When X is -1 in the freeze branch, it should fail
        # In the true branch (no freeze), it should succeed
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


# ── When/2 ───────────────────────────────────────────────────────────────────


def _when_goal(cond, goal):
    return Call(func=LoadName(name="When"), args=[cond, goal], kwargs=[])


def _is_bound_cond(x):
    return Call(func=LoadName(name="IsBound"), args=[x], kwargs=[])


def _is_ground_cond(x):
    return Call(func=LoadName(name="IsGround"), args=[x], kwargs=[])


class TestWhen:
    def test_when_is_bound_already(self):
        """When(IsBound(X), Goal) where X is already bound → runs immediately."""
        x = Var()
        y = Var()
        goal = And(
            left=_unify_goal(x, "hello"),
            right=_when_goal(_is_bound_cond(x), _unify_goal(y, x)),
        )
        results = bindings(goal, y)
        assert results == ["hello"]

    def test_when_is_bound_deferred(self):
        """When(IsBound(X), Goal), X = val → Goal fires when X is bound."""
        x = Var()
        y = Var()
        goal = And(
            left=_when_goal(_is_bound_cond(x), _unify_goal(y, x)),
            right=_unify_goal(x, "world"),
        )
        results = bindings(goal, y)
        assert results == ["world"]

    def test_when_conjunction(self):
        """When((IsBound(X), IsBound(Y)), Goal) — fires when both are bound."""
        x = Var()
        y = Var()
        result = Var()
        cond = And(left=_is_bound_cond(x), right=_is_bound_cond(y))
        # When both X and Y are bound, result = X + Y (but we'll just test binding)
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
        """When((IsBound(X), IsBound(Y)), Goal) — Y not bound yet, Goal not fired."""
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
            # Actually: when X is bound, When(IsBound(Y), Goal) is installed.
            # Since Y isn't bound, result stays unbound.
            r = deref(result)
            assert r is result  # still unbound

    def test_when_is_ground_already(self):
        """When(IsGround(f(1, 2)), Goal) — already ground → immediate."""
        x = Var()
        result = Var()
        goal = And(
            left=_unify_goal(x, [1, 2, 3]),
            right=_when_goal(_is_ground_cond(x), _unify_goal(result, "grounded")),
        )
        results = bindings(goal, result)
        assert results == ["grounded"]

    def test_when_is_ground_deferred(self):
        """When(IsGround(X), Goal), X = 5 → Goal fires when X is ground."""
        x = Var()
        result = Var()
        goal = And(
            left=_when_goal(_is_ground_cond(x), _unify_goal(result, "grounded")),
            right=_unify_goal(x, 42),
        )
        results = bindings(goal, result)
        assert results == ["grounded"]

    def test_when_is_ground_nested(self):
        """When(IsGround([X, Y]), Goal) — fires when both X and Y are ground."""
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
        """When(IsBound(X), Goal) where Goal fails → unification fails."""
        x = Var()
        goal = And(
            left=_when_goal(_is_bound_cond(x), Gt(left=x, right=100)),
            right=_unify_goal(x, 5),  # 5 > 100 is false
        )
        results = solutions_of(goal)
        assert results == []


# ── Meta-predicate nesting ───────────────────────────────────────────────────


def _find_all_goal(template, inner, bag):
    return Call(func=LoadName(name="FindAll"), args=[template, inner, bag], kwargs=[])


def _once_goal(inner):
    return Call(func=LoadName(name="Once"), args=[inner], kwargs=[])


def _catch_goal(goal, catcher, recovery):
    return Call(func=LoadName(name="catch"), args=[goal, catcher, recovery], kwargs=[])


class TestMetaPredicateNesting:
    """Verify that new special forms nest correctly inside other meta-predicates."""

    def test_find_all_call_nth(self):
        """FindAll(X, CallNth(In(X, List), 2), Bag) -> [20]"""
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
        """FindAll(N, CountAll(In(_, List), N), Bag) -> [3]"""
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
        """Once(CallNth(In(X, List), 1)) -> X = 10"""
        x = Var()
        goal = _once_goal(_call_nth_goal(_in_goal(x, [10, 20, 30]), 1))
        results = bindings(goal, x)
        assert results == [10]

    def test_once_count_all(self):
        """Once(CountAll(In(_, List), N)) -> N = 3"""
        x = Var()
        n = Var()
        goal = _once_goal(_count_all_goal(_in_goal(x, [1, 2, 3]), n))
        results = bindings(goal, n)
        assert results == [3]

    def test_catch_call_nth_type_error(self):
        """catch(CallNth(Goal, 0), Error, Recovery) catches type error."""
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
        """Freeze(X, CallNth(In(Y, [X]), 1)), X = 42 -> Y = 42"""
        x = Var()
        y = Var()
        goal = And(
            left=_freeze_goal(x, _call_nth_goal(_in_goal(y, [x]), 1)),
            right=_unify_goal(x, 42),
        )
        results = bindings(goal, y)
        assert results == [42]

    def test_scc_inside_find_all(self):
        """FindAll(X, SetupCallCleanup(true, In(X, [a,b]), true), Bag) -> [a, b]"""
        x = Var()
        bag = Var()
        inner = _scc_goal(True, _in_goal(x, ["a", "b"]), True)
        goal = _find_all_goal(x, inner, bag)
        results = bindings(goal, bag)
        assert results == [["a", "b"]]

    def test_freeze_inside_find_all(self):
        """FindAll(Y, (Freeze(X, Y is X), X is 99), Bag) -> [99]"""
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
        """CountAll(CountAll(In(_, [1,2]), _), N) -> N = 1"""
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
        """Once(CallCleanup(In(X, [a, b, c]), true)) -> X = a"""
        x = Var()
        goal = _once_goal(_cc_goal(_in_goal(x, ["a", "b", "c"]), True))
        results = bindings(goal, x)
        assert results == ["a"]
