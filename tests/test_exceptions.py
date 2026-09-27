"""Tests for V2-14: throw/catch exception handling."""

from __future__ import annotations

import os

import pytest

from clausal.logic.atoms import mint
from clausal.logic.compiler import (
    compile_predicate_shallow as compile_predicate,
    compile_predicate_trampoline,
)
from clausal.logic.database import Clause, Module
from clausal.logic.solve import solve, _deref_walk
from clausal.logic.variables import Var, Trail, deref
from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException, error_context_text
from clausal.terms import And, Call, LoadName, Compound, Unify as Is, in_


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
        # nv
        exc = LogicException("oops")
        assert isinstance(exc, Exception)

    def test_carries_term(self):
        # nv
        exc = LogicException(Compound("error", ("type_error", "foo")))
        assert exc.term == Compound("error", ("type_error", "foo"))

    def test_str(self):
        # nv
        exc = LogicException("oops")
        assert "oops" in str(exc)


# ── throw/1 ──────────────────────────────────────────────────────────────────


class TestThrow:
    def test_throw_raises_logic_exception(self):
        """throw(Term) raises LogicException with the term."""
        # nv
        goal = Call(func=LoadName(name="throw"), args=["oops"], kwargs=[])
        with pytest.raises(LogicException) as exc_info:
            solutions_of(goal)
        assert exc_info.value.term == "oops"

    def test_throw_with_compound_term(self):
        """throw(error(type_error, foo)) raises with compound term."""
        # nv
        term = Compound("error", ("type_error", "foo"))
        goal = Call(func=LoadName(name="throw"), args=[term], kwargs=[])
        with pytest.raises(LogicException) as exc_info:
            solutions_of(goal)
        assert exc_info.value.term.functor == "error"

    def test_throw_with_integer(self):
        """throw(42) raises with integer term."""
        # nv
        goal = Call(func=LoadName(name="throw"), args=[42], kwargs=[])
        with pytest.raises(LogicException) as exc_info:
            solutions_of(goal)
        assert exc_info.value.term == 42

    def test_throw_with_string_var(self):
        """throw(X) where X is bound via And raises LogicException."""
        # Use catch to capture the thrown term while bindings are still live
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
        goal = Call(func=LoadName(name="halt"), args=[], kwargs=[])
        with pytest.raises(SystemExit) as exc_info:
            solutions_of(goal)
        assert exc_info.value.code == 0

    def test_halt_1(self):
        """halt(1) raises SystemExit(1)."""
        # nv
        goal = Call(func=LoadName(name="halt"), args=[1], kwargs=[])
        with pytest.raises(SystemExit) as exc_info:
            solutions_of(goal)
        assert exc_info.value.code == 1


# ── Python interop ──────────────────────────────────────────────────────────


class TestPythonInterop:
    def test_python_catches_logic_exception(self):
        """Python try/except catches LogicException from throw/1."""
        # nv
        goal = Call(func=LoadName(name="throw"), args=["from_logic"], kwargs=[])
        try:
            solutions_of(goal)
            assert False, "should have raised"
        except LogicException as e:
            assert e.term == "from_logic"

    def test_logic_exception_is_exception_subclass(self):
        """LogicException is catchable as a plain Exception."""
        # nv
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
        # nv
        from clausal.logic.exceptions import type_error
        t = type_error("integer", "foo", "bar/1")
        assert cell_functor(t) == "error"
        assert cell_functor(cell_args(t)[0]) == "type_error"
        # The TYPE name is an atom; the culprit and the CONTEXT are as the
        # caller passed them — here plain Python strings (spec §6.4).
        assert cell_args(cell_args(t)[0]) == (mint("integer"), "foo")
        assert error_context_text(t) == "bar/1"

    def test_instantiation_error_helper(self):
        # nv
        from clausal.logic.exceptions import instantiation_error
        t = instantiation_error("is/2")
        assert cell_functor(t) == "error"
        assert cell_args(t)[0] == mint("instantiation_error")
        assert error_context_text(t) == "(is)/2"

    def test_existence_error_helper(self):
        # nv
        from clausal.logic.exceptions import existence_error
        t = existence_error("procedure", "foo/2")
        assert cell_functor(t) == "error"
        assert cell_functor(cell_args(t)[0]) == "existence_error"

    def test_permission_error_helper(self):
        # nv
        from clausal.logic.exceptions import permission_error
        t = permission_error("modify", "static_procedure", "foo/2")
        assert cell_functor(t) == "error"
        assert cell_functor(cell_args(t)[0]) == "permission_error"


# ── .clausal integration tests ──────────────────────────────────────────────


# ── TestClausalIntegration removed ─────────────────────────────────────────
# Clausal-surface integration tests migrated to tests/fixtures/catch_test.clausal.


# ── throw inside findall ─────────────────────────────────────────────────────


class TestThrowInFindAll:
    def test_throw_inside_findall_propagates(self):
        """throw inside findall propagates out (not isolated)."""
        # nv
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
        # nv
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


# ── Raising well-formedness guards for library code ──────────────────────────
#
# A .clausal library predicate can RAISE on malformed input instead of failing
# logically and collapsing silently inside a findall.  This is the pattern vocab
# authors reach for so a bad argument (wrong shape / unbound / wrong type)
# lands on the loud RAISED diagnostic channel rather than turning a findall
# into an indistinguishable empty result.  The mechanism is just throw/1 with a
# structured error term; nothing new is needed.  These tests pin that the raise
# actually propagates out of a findall to the test runner's RAISED path, which
# nothing previously covered end-to-end at the .clausal surface.
#
# See docs/exceptions.md ("Raising well-formedness guards in library code") and
# the fixture tests/fixtures/raising_guard_lib.clausal.


class TestRaisingGuardThroughFindAll:
    _GUARD_FIXTURE = os.path.join(_FIXTURE_DIR, "raising_guard_lib.clausal")

    def _run(self, description):
        from clausal.testing import load_clausal_module, run_test
        mod = load_clausal_module(self._GUARD_FIXTURE)
        return run_test(mod, description, path=self._GUARD_FIXTURE, diagnose=True)

    def test_guard_raise_propagates_out_of_findall(self):
        """A throw in a guard called inside findall reaches the RAISED path.

        Not swallowed as a logical failure that collapses the findall to []:
        the test runner records the exception on the result and the diagnostic
        walks to the *raising* conjunct (the findall), rendering it on the
        "raised" branch — the same loud channel as a Python-side exception.
        """
        result = self._run("guard raises through findall on malformed REF_YMD")
        assert not result.passed
        # The raise reached run_test's handler rather than being converted to a
        # silent empty findall (which would make the test *fail* with no error).
        assert isinstance(result.error, LogicException)
        # The thrown term carries the message and the offending culprit term.
        # P3-2 Task 2 (THE FLIP, R6): a functor declared in ``-private`` is a
        # DATA functor, so it throws as a CELL -- slot 0 the functor, the
        # declared fields positionally after it.  (Was a term-class instance
        # read through ``term_field_names``.)
        term = result.error.term
        assert term[0] == "wf_bad_shape"
        assert list(term[1:]) == [
            mint("window_days_used: REF_YMD must be [Y,M,D]"),
            mint("2020-01-01")]
        # The RAISED diagnostic path is taken (verb == "raised"), and it names
        # the findall goal the throw escaped from.
        diag = result.diagnostic
        assert diag is not None and diag.raised is not None
        report = "\n".join(diag.lines())
        assert "raised:" in report
        assert "findall(" in report
        assert "wf_bad_shape" in report

    def test_wellformed_input_does_not_raise(self):
        """The control: well-formed input flows through findall with no raise."""
        result = self._run("wellformed REF_YMD does not raise")
        assert result.passed
        assert result.error is None


class TestAssertzAgainstADataFunctor:
    """P3-2 Task 2 (THE FLIP): ``assertz`` to a declared-with-fields,
    clause-free, non-``-dynamic`` functor.

    Its terms are CELLS now (R6), so what reaches ``assertz/1`` is a plain
    tuple, and nothing downstream reads one as a clause head — ``head_key``
    used to surface that as an internal
    ``TypeError: Cannot extract (functor, arity) from head term: ('f', 7)``,
    which names neither the mistake nor its remedy.  Pre-flip the same
    program raised ``permission_error(modify, static_procedure, f/1)``,
    because the head was an instance of a clause-free class.  The ISO error
    is restored, and it now names ``-dynamic`` as the fix.

    (Making the assert SUCCEED — general cell-head assertz support — is
    P3-3's scope, deliberately not this task's.  This pins the diagnostic.)
    """

    _SRC = (
        "-module(azdf, [f(A), go(X)])\n"
        "go(X) <- assertz(f(X))\n"
    )

    def _module(self, tmp_path):
        from clausal.import_hook import _load_module

        path = tmp_path / "azdf.clausal"
        path.write_text(self._SRC)
        return _load_module("azdf", str(path))

    def test_raises_a_catchable_logic_exception_not_a_typeerror(self, tmp_path):
        from clausal.logic.exceptions import LogicException
        from clausal.logic.solve import call

        mod = self._module(tmp_path)
        with pytest.raises(LogicException) as excinfo:
            list(call("go", 7, module=mod.__dict__["$module"]))
        assert not isinstance(excinfo.value, TypeError)

    def test_the_term_is_the_iso_permission_error_naming_functor_and_arity(
            self, tmp_path):
        from clausal.logic.exceptions import LogicException
        from clausal.logic.solve import call

        mod = self._module(tmp_path)
        with pytest.raises(LogicException) as excinfo:
            list(call("go", 7, module=mod.__dict__["$module"]))
        term = excinfo.value.term
        assert cell_functor(term) == "error"
        inner = cell_args(term)[0]
        assert cell_functor(inner) == "permission_error"
        assert cell_args(inner)[0] == mint("modify")
        assert cell_args(inner)[1] == mint("static_procedure")
        indicator = cell_args(inner)[2]
        assert cell_functor(indicator) == "/"
        # The indicator the engine builds holds the SPELLING (a str) and the
        # arity, as it always has.
        assert cell_args(indicator) == ("f", 1)

    def test_the_message_points_at_dynamic(self, tmp_path):
        from clausal.logic.exceptions import LogicException
        from clausal.logic.solve import call

        mod = self._module(tmp_path)
        with pytest.raises(LogicException) as excinfo:
            list(call("go", 7, module=mod.__dict__["$module"]))
        context = error_context_text(excinfo.value.term)
        assert "assertz/1" in context
        assert "-dynamic" in context
        assert "data functor" in context

    def test_a_dynamic_declaration_makes_the_assert_work(self, tmp_path):
        """The remedy the message names actually works: ``-dynamic`` keeps
        the functor a predicate class, so the assert lands."""
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        from clausal.logic.variables import Var, deref

        path = tmp_path / "azdyn.clausal"
        path.write_text(
            "-module(azdyn, [f(A), go(X)])\n"
            "-dynamic(f/1)\n"
            "go(X) <- assertz(f(X))\n"
        )
        mod = _load_module("azdyn", str(path))
        lm = mod.__dict__["$module"]
        assert len(list(call("go", 7, module=lm))) == 1
        out = Var()
        assert [deref(out) for _ in call("f", out, module=lm)] == [7]
