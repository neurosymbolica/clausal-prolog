"""Tests for V2-14: throw/catch exception handling."""

from __future__ import annotations

import os
import sys

import pytest

from clausal.logic.compiler import (
    compile_predicate_shallow as compile_predicate,
    compile_predicate_trampoline,
)
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
from clausal.import_hook import _load_module


# ── Helpers ────────────────────────────────────────────────────────────────────


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


_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


# ── LogicException class ─────────────────────────────────────────────────────


class TestLogicException:
    def test_is_exception(self):
        exc = LogicException("oops")
        assert isinstance(exc, Exception)

    def test_carries_term(self):
        exc = LogicException(Compound("error", ("type_error", "foo")))
        assert exc.term == Compound("error", ("type_error", "foo"))

    def test_str(self):
        exc = LogicException("oops")
        assert "oops" in str(exc)


# ── throw/1 ──────────────────────────────────────────────────────────────────


class TestThrow:
    def test_throw_raises_logic_exception(self):
        """throw(Term) raises LogicException with the term."""
        goal = Call(func=LoadName(name="throw"), args=["oops"], kwargs=[])
        with pytest.raises(LogicException) as exc_info:
            solutions_of(goal)
        assert exc_info.value.term == "oops"

    def test_throw_with_compound_term(self):
        """throw(error(type_error, foo)) raises with compound term."""
        term = Compound("error", ("type_error", "foo"))
        goal = Call(func=LoadName(name="throw"), args=[term], kwargs=[])
        with pytest.raises(LogicException) as exc_info:
            solutions_of(goal)
        assert exc_info.value.term.functor == "error"

    def test_throw_with_integer(self):
        """throw(42) raises with integer term."""
        goal = Call(func=LoadName(name="throw"), args=[42], kwargs=[])
        with pytest.raises(LogicException) as exc_info:
            solutions_of(goal)
        assert exc_info.value.term == 42

    def test_throw_with_string_var(self):
        """throw(X) where X is bound via And raises LogicException."""
        # Use catch to capture the thrown term while bindings are still live
        x = Var()
        e = Var()
        result = Var()
        goal = Call(func=LoadName(name="catch"), args=[
            And(
                left=Is(left=x, right=99),
                right=Call(func=LoadName(name="throw"), args=[x], kwargs=[]),
            ),
            e,
            Is(left=result, right="caught"),
        ], kwargs=[])
        results = bindings(goal, result)
        assert results == ["caught"]


# ── catch/3 ──────────────────────────────────────────────────────────────────


class TestCatch:
    def test_catch_no_exception(self):
        """catch(true, E, fail) succeeds normally when goal doesn't throw."""
        result = Var()
        goal = Call(func=LoadName(name="catch"), args=[
            Is(left=result, right="ok"),
            Var(),
            False,
        ], kwargs=[])
        results = bindings(goal, result)
        assert results == ["ok"]

    def test_catch_catches_throw(self):
        """catch(throw(oops), E, Result is E) catches and runs recovery."""
        e = Var()
        result = Var()
        goal = Call(func=LoadName(name="catch"), args=[
            Call(func=LoadName(name="throw"), args=["oops"], kwargs=[]),
            e,
            Is(left=result, right=e),
        ], kwargs=[])
        results = bindings(goal, result)
        assert results == ["oops"]

    def test_catch_specific_catcher(self):
        """catch(throw(oops), 'oops', Result is caught) matches specific term."""
        result = Var()
        goal = Call(func=LoadName(name="catch"), args=[
            Call(func=LoadName(name="throw"), args=["oops"], kwargs=[]),
            "oops",
            Is(left=result, right="caught"),
        ], kwargs=[])
        results = bindings(goal, result)
        assert results == ["caught"]

    def test_catch_mismatch_reraises(self):
        """catch(throw(oops), 'other', recovery) re-raises when catcher doesn't match."""
        result = Var()
        goal = Call(func=LoadName(name="catch"), args=[
            Call(func=LoadName(name="throw"), args=["oops"], kwargs=[]),
            "other",
            Is(left=result, right="caught"),
        ], kwargs=[])
        with pytest.raises(LogicException) as exc_info:
            solutions_of(goal)
        assert exc_info.value.term == "oops"

    def test_catch_variable_catcher(self):
        """catch(throw(42), E, Result is E) — variable catcher catches anything."""
        e = Var()
        result = Var()
        goal = Call(func=LoadName(name="catch"), args=[
            Call(func=LoadName(name="throw"), args=[42], kwargs=[]),
            e,
            Is(left=result, right=e),
        ], kwargs=[])
        results = bindings(goal, result)
        assert results == [42]

    def test_nested_catch_inner_catches(self):
        """Inner catch handles the exception; outer catch is not triggered."""
        result = Var()
        inner = Call(func=LoadName(name="catch"), args=[
            Call(func=LoadName(name="throw"), args=["inner_err"], kwargs=[]),
            "inner_err",
            Is(left=result, right="inner_caught"),
        ], kwargs=[])
        outer = Call(func=LoadName(name="catch"), args=[
            inner,
            Var(),
            Is(left=result, right="outer_caught"),
        ], kwargs=[])
        results = bindings(outer, result)
        assert results == ["inner_caught"]

    def test_nested_catch_inner_misses(self):
        """Inner catch doesn't match; outer catches instead."""
        e = Var()
        result = Var()
        inner = Call(func=LoadName(name="catch"), args=[
            Call(func=LoadName(name="throw"), args=["outer_err"], kwargs=[]),
            "inner_only",
            Is(left=result, right="inner_caught"),
        ], kwargs=[])
        outer = Call(func=LoadName(name="catch"), args=[
            inner,
            e,
            Is(left=result, right=e),
        ], kwargs=[])
        results = bindings(outer, result)
        assert results == ["outer_err"]

    def test_trail_cleanup_on_catch(self):
        """Bindings from the failing goal are undone before recovery runs."""
        x = Var()
        result = Var()
        # Goal binds x to 1, then throws. After catch, x should be unbound.
        failing_goal = And(
            left=Is(left=x, right=1),
            right=Call(func=LoadName(name="throw"), args=["err"], kwargs=[]),
        )
        goal = Call(func=LoadName(name="catch"), args=[
            failing_goal,
            "err",
            Is(left=result, right="recovered"),
        ], kwargs=[])
        t = Trail()
        for _ in solve(goal, fresh_module(), t):
            assert deref(result) == "recovered"
            # x should be unbound (trail was undone)
            assert deref(x) is x

    def test_throw_inside_deeply_nested(self):
        """throw deep inside predicate calls propagates up to catch."""
        mod = fresh_module()
        db = mod.db

        # a(X) :- b(X).
        # b(X) :- throw(deep_error).
        x_a, x_b = Var(), Var()
        compile_predicate_trampoline("a", 1, [
            Clause(
                head=Compound("a", (x_a,)),
                body=[Call(func=LoadName(name="b"), args=[x_a], kwargs=[])],
            ),
        ], db)
        compile_predicate_trampoline("b", 1, [
            Clause(
                head=Compound("b", (x_b,)),
                body=[Call(func=LoadName(name="throw"), args=["deep_error"], kwargs=[])],
            ),
        ], db)

        e = Var()
        result = Var()
        goal = Call(func=LoadName(name="catch"), args=[
            Call(func=LoadName(name="a"), args=[Var()], kwargs=[]),
            e,
            Is(left=result, right=e),
        ], kwargs=[])
        results = bindings(goal, result, mod)
        assert results == ["deep_error"]

    def test_catch_goal_succeeds_multiple_solutions(self):
        """catch with goal that has multiple solutions — all yielded."""
        x = Var()
        result = Var()
        goal = Call(func=LoadName(name="catch"), args=[
            And(
                left=in_(left=x, right=[1, 2, 3]),
                right=Is(left=result, right=x),
            ),
            Var(),
            False,
        ], kwargs=[])
        results = bindings(goal, result)
        assert results == [1, 2, 3]


# ── halt/0, halt/1 ──────────────────────────────────────────────────────────


class TestHalt:
    def test_halt_0(self):
        """halt/0 raises SystemExit(0)."""
        goal = Call(func=LoadName(name="halt"), args=[], kwargs=[])
        with pytest.raises(SystemExit) as exc_info:
            solutions_of(goal)
        assert exc_info.value.code == 0

    def test_halt_1(self):
        """halt(1) raises SystemExit(1)."""
        goal = Call(func=LoadName(name="halt"), args=[1], kwargs=[])
        with pytest.raises(SystemExit) as exc_info:
            solutions_of(goal)
        assert exc_info.value.code == 1


# ── Python interop ──────────────────────────────────────────────────────────


class TestPythonInterop:
    def test_python_catches_logic_exception(self):
        """Python try/except catches LogicException from throw/1."""
        goal = Call(func=LoadName(name="throw"), args=["from_logic"], kwargs=[])
        try:
            solutions_of(goal)
            assert False, "should have raised"
        except LogicException as e:
            assert e.term == "from_logic"

    def test_logic_exception_is_exception_subclass(self):
        """LogicException is catchable as a plain Exception."""
        goal = Call(func=LoadName(name="throw"), args=["test"], kwargs=[])
        try:
            solutions_of(goal)
            assert False, "should have raised"
        except Exception as e:
            assert isinstance(e, LogicException)
            assert e.term == "test"


# ── Structured error terms ──────────────────────────────────────────────────


class TestStructuredErrors:
    def test_type_error_helper(self):
        from clausal.logic.exceptions import type_error
        t = type_error("integer", "foo", "bar/1")
        assert t.functor == "error"
        assert t.args[0].functor == "type_error"
        assert t.args[0].args == ("integer", "foo")
        assert t.args[1] == "bar/1"

    def test_instantiation_error_helper(self):
        from clausal.logic.exceptions import instantiation_error
        t = instantiation_error("is/2")
        assert t.functor == "error"
        assert t.args[0] == "instantiation_error"
        assert t.args[1] == "is/2"

    def test_existence_error_helper(self):
        from clausal.logic.exceptions import existence_error
        t = existence_error("procedure", "foo/2")
        assert t.functor == "error"
        assert t.args[0].functor == "existence_error"

    def test_permission_error_helper(self):
        from clausal.logic.exceptions import permission_error
        t = permission_error("modify", "static_procedure", "foo/2")
        assert t.functor == "error"
        assert t.args[0].functor == "permission_error"


# ── .clausal integration tests ──────────────────────────────────────────────


class TestClausalIntegration:
    def test_catch_all(self):
        """CatchAll catches any thrown term."""
        mod = _load_module("catch_test", os.path.join(_FIXTURE_DIR, "catch_test.clausal"))
        logic_mod = mod.__dict__["$module"]
        result = Var()
        results = [_deref_walk(result) for _ in call("CatchAll", result, module=logic_mod)]
        assert results == [42]

    def test_catch_neg_positive(self):
        """CatchNeg with positive value succeeds normally."""
        mod = _load_module("catch_test", os.path.join(_FIXTURE_DIR, "catch_test.clausal"))
        logic_mod = mod.__dict__["$module"]
        result = Var()
        results = [_deref_walk(result) for _ in call("CatchNeg", 5, result, module=logic_mod)]
        assert results == ["ok"]

    def test_catch_neg_negative(self):
        """CatchNeg with negative value catches the throw."""
        mod = _load_module("catch_test", os.path.join(_FIXTURE_DIR, "catch_test.clausal"))
        logic_mod = mod.__dict__["$module"]
        result = Var()
        results = [_deref_walk(result) for _ in call("CatchNeg", -3, result, module=logic_mod)]
        assert results == ["caught_negative"]

    def test_nested_catch(self):
        """NestedCatch: inner catch misses, outer catches."""
        mod = _load_module("catch_test", os.path.join(_FIXTURE_DIR, "catch_test.clausal"))
        logic_mod = mod.__dict__["$module"]
        result = Var()
        results = [_deref_walk(result) for _ in call("NestedCatch", result, module=logic_mod)]
        assert results == ["outer_error"]


# ── throw inside findall ─────────────────────────────────────────────────────


class TestThrowInFindAll:
    def test_throw_inside_findall_propagates(self):
        """throw inside findall propagates out (not isolated)."""
        x = Var()
        bag = Var()
        inner = And(
            left=in_(left=x, right=[1, 2, 3]),
            right=Call(func=LoadName(name="throw"), args=["findall_err"], kwargs=[]),
        )
        goal = Call(func=LoadName(name="findall"), args=[x, inner, bag], kwargs=[])
        with pytest.raises(LogicException) as exc_info:
            solutions_of(goal)
        assert exc_info.value.term == "findall_err"

    def test_catch_around_findall(self):
        """catch around findall catches throw from inside findall."""
        x = Var()
        bag = Var()
        result = Var()
        e = Var()
        inner = And(
            left=in_(left=x, right=[1, 2, 3]),
            right=Call(func=LoadName(name="throw"), args=["fa_err"], kwargs=[]),
        )
        findall = Call(func=LoadName(name="findall"), args=[x, inner, bag], kwargs=[])
        goal = Call(func=LoadName(name="catch"), args=[
            findall,
            e,
            Is(left=result, right=e),
        ], kwargs=[])
        results = bindings(goal, result)
        assert results == ["fa_err"]
