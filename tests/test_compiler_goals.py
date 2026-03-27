"""Tests for clausal.logic.compiler — Step 5: body goal compilation.

Tests cover:
  - term_to_ast_expr: Var, literals, list, Compound, functor dataclass
  - arith_to_ast_expr: scalars, arithmetic operators, Var deref
  - compile_goal: each goal type → correct statements / runtime behaviour
  - compile_body: flat conjunction with yield at leaf
  - Integration: full compile_predicate with real bodies running against Trail
"""

from __future__ import annotations

import ast
import dataclasses

import pytest

from clausal.logic.compiler import (
    compile_body,
    compile_goal,
    compile_predicate_trampoline as compile_predicate,
    term_to_ast_expr,
    arith_to_ast_expr,
)
from clausal.logic.database import Clause, Database
from clausal.logic.trampoline import StepGenerator, DONE
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import (
    And, Or, Not,
    Unify as Is, DoesNotUnify as IsNot, ArithEq, ArithNeq,
    Lt, LtE, Gt, GtE,
    in_, NotIn,
    Add, Sub, Mult, FloorDiv, Mod, Negate,
    Call, LoadName,
    Compound,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


def fresh_trail() -> Trail:
    return Trail()


@dataclasses.dataclass
class point:
    _x: object = None
    _y: object = None


@dataclasses.dataclass
class pair:
    left: object = None
    right: object = None


# ── term_to_ast_expr ───────────────────────────────────────────────────────────


class TestTermToAstExpr:
    """term_to_ast_expr returns an AST expression for various term types."""

    def test_known_var_gives_name(self):
        v = Var()
        vc = {v._id: "_vX"}
        expr = term_to_ast_expr(v, vc)
        assert isinstance(expr, ast.Name)
        assert expr.id == "_vX"

    def test_body_only_var_gives_walrus(self):
        v = Var()
        vc: dict[int, str] = {}
        expr = term_to_ast_expr(v, vc)
        assert isinstance(expr, ast.NamedExpr)
        # walrus target should be _v{id}
        assert expr.target.id == f"_v{v._id}"
        # right-hand side should be a Var() call
        assert isinstance(expr.value, ast.Call)
        assert isinstance(expr.value.func, ast.Name)
        assert expr.value.func.id == "Var"
        # var registered in context
        assert v._id in vc

    def test_body_only_var_same_name_on_second_call(self):
        v = Var()
        vc: dict[int, str] = {}
        term_to_ast_expr(v, vc)          # first call → walrus
        expr2 = term_to_ast_expr(v, vc)  # second call → plain Name
        assert isinstance(expr2, ast.Name)
        assert expr2.id == vc[v._id]

    def test_none_constant(self):
        expr = term_to_ast_expr(None, {})
        assert isinstance(expr, ast.Constant)
        assert expr.value is None

    def test_true_constant(self):
        expr = term_to_ast_expr(True, {})
        assert isinstance(expr, ast.Constant)
        assert expr.value is True

    def test_false_constant(self):
        expr = term_to_ast_expr(False, {})
        assert isinstance(expr, ast.Constant)
        assert expr.value is False

    def test_int_constant(self):
        expr = term_to_ast_expr(42, {})
        assert isinstance(expr, ast.Constant)
        assert expr.value == 42

    def test_str_constant(self):
        expr = term_to_ast_expr("hello", {})
        assert isinstance(expr, ast.Constant)
        assert expr.value == "hello"

    def test_float_constant(self):
        expr = term_to_ast_expr(3.14, {})
        assert isinstance(expr, ast.Constant)
        assert isinstance(expr.value, float)

    def test_list_gives_ast_list(self):
        expr = term_to_ast_expr([1, 2, 3], {})
        assert isinstance(expr, ast.List)
        assert len(expr.elts) == 3

    def test_list_recurses_into_elements(self):
        v = Var()
        vc: dict[int, str] = {}
        expr = term_to_ast_expr([v, 42], vc)
        assert isinstance(expr, ast.List)
        assert isinstance(expr.elts[0], ast.NamedExpr)   # body-only Var → walrus
        assert isinstance(expr.elts[1], ast.Constant)

    def test_compound_gives_call_to_compound(self):
        term = Compound("foo", (1, 2))
        expr = term_to_ast_expr(term, {})
        assert isinstance(expr, ast.Call)
        assert isinstance(expr.func, ast.Name)
        assert expr.func.id == "Compound"
        # first arg is the functor string constant
        assert isinstance(expr.args[0], ast.Constant)
        assert expr.args[0].value == "foo"
        # second arg is a Tuple of sub-expressions
        assert isinstance(expr.args[1], ast.Tuple)

    def test_dataclass_gives_call_to_cls(self):
        v = Var()
        vc: dict[int, str] = {}
        term = point(_x=v, _y=99)
        expr = term_to_ast_expr(term, vc)
        assert isinstance(expr, ast.Call)
        assert isinstance(expr.func, ast.Name)
        assert expr.func.id == "point"
        kw_names = [kw.arg for kw in expr.keywords]
        assert "_x" in kw_names
        assert "_y" in kw_names

    def test_unknown_type_raises(self):
        with pytest.raises(NotImplementedError):
            term_to_ast_expr(object(), {})


# ── arith_to_ast_expr ─────────────────────────────────────────────────────────


class TestArithToAstExpr:
    """arith_to_ast_expr produces Python arithmetic AST."""

    def test_int_gives_constant(self):
        expr = arith_to_ast_expr(7, {})
        assert isinstance(expr, ast.Constant)
        assert expr.value == 7

    def test_float_gives_constant(self):
        expr = arith_to_ast_expr(2.5, {})
        assert isinstance(expr, ast.Constant)

    def test_var_gives_deref_call(self):
        v = Var()
        vc = {v._id: "_vX"}
        expr = arith_to_ast_expr(v, vc)
        assert isinstance(expr, ast.Call)
        assert isinstance(expr.func, ast.Name)
        assert expr.func.id == "deref"

    def test_add_gives_binop_add(self):
        expr = arith_to_ast_expr(Add(left=1, right=2), {})
        assert isinstance(expr, ast.BinOp)
        assert isinstance(expr.op, ast.Add)
        assert isinstance(expr.left, ast.Constant)
        assert isinstance(expr.right, ast.Constant)

    def test_sub(self):
        expr = arith_to_ast_expr(Sub(left=5, right=3), {})
        assert isinstance(expr, ast.BinOp)
        assert isinstance(expr.op, ast.Sub)

    def test_mult(self):
        expr = arith_to_ast_expr(Mult(left=2, right=3), {})
        assert isinstance(expr, ast.BinOp)
        assert isinstance(expr.op, ast.Mult)

    def test_negate(self):
        expr = arith_to_ast_expr(Negate(operand=5), {})
        assert isinstance(expr, ast.UnaryOp)
        assert isinstance(expr.op, ast.USub)

    def test_nested_add(self):
        expr = arith_to_ast_expr(Add(left=Add(left=1, right=2), right=3), {})
        assert isinstance(expr, ast.BinOp)
        assert isinstance(expr.left, ast.BinOp)


# ── compile_goal — structural tests ───────────────────────────────────────────


class TestCompileGoalStructure:
    """compile_goal returns the right statement structure for each goal type."""

    def _db(self):
        return Database()

    def test_true_returns_k_stmts(self):
        sentinel = ast.Pass()
        stmts = compile_goal(True, self._db(), {}, "trail", [sentinel])
        assert stmts == [sentinel]

    def test_false_returns_empty(self):
        stmts = compile_goal(False, self._db(), {}, "trail", [ast.Pass()])
        assert stmts == []

    def test_is_gives_mark_if_undo(self):
        v = Var()
        vc = {v._id: "_vX"}
        stmts = compile_goal(Is(left=v, right=42), self._db(), vc, "trail", [ast.Pass()])
        # Should have: assign_mark, If(unify(...)), undo
        assert len(stmts) == 3
        assert isinstance(stmts[0], ast.Assign)     # _mN = trail.mark()
        assert isinstance(stmts[1], ast.If)          # if unify(...):
        assert isinstance(stmts[2], ast.Expr)        # trail.undo(_mN)

    def test_and_chains_goals(self):
        v = Var()
        vc = {v._id: "_vX"}
        # And(Is(v, 1), Is(v, 2)) — body won't succeed but structure is right
        stmts = compile_goal(
            And(left=Is(left=v, right=1), right=Is(left=v, right=2)),
            self._db(), vc, "trail", [ast.Pass()],
        )
        # Left goal wraps right goal as continuation: mark, if, undo
        assert len(stmts) == 3
        assert isinstance(stmts[0], ast.Assign)  # _m for left Is
        # The If body contains the right goal stmts (mark, if, undo)
        assert isinstance(stmts[1].body[0], ast.Assign)  # _m for right Is

    def test_or_gives_two_branches(self):
        v = Var()
        vc = {v._id: "_vX"}
        stmts = compile_goal(
            Or(left=Is(left=v, right=1), right=Is(left=v, right=2)),
            self._db(), vc, "trail", [ast.Pass()],
        )
        # mark, left stmts, undo, mark, right stmts, undo
        assert isinstance(stmts[0], ast.Assign)     # _m = trail.mark()
        assert isinstance(stmts[-1], ast.Expr)       # trail.undo(_m)

    def test_not_generates_nested_function(self):
        v = Var()
        vc = {v._id: "_vX"}
        stmts = compile_goal(
            Not(operand=Is(left=v, right=42)),
            self._db(), vc, "trail", [ast.Pass()],
        )
        # First stmt should be a FunctionDef (the NAF sub-generator)
        assert isinstance(stmts[0], ast.FunctionDef)

    def test_in_generates_for_loop(self):
        v = Var()
        vc = {v._id: "_vX"}
        coll = Var()
        cvc = {v._id: "_vX", coll._id: "_vC"}
        stmts = compile_goal(in_(left=v, right=coll), self._db(), cvc, "trail", [ast.Pass()])
        assert isinstance(stmts[0], ast.For)

    def test_not_in_generates_flag_and_for_loop(self):
        v = Var()
        coll = Var()
        vc = {v._id: "_vX", coll._id: "_vC"}
        stmts = compile_goal(NotIn(left=v, right=coll), self._db(), vc, "trail", [ast.Pass()])
        # flag assign, for loop, if check
        assert isinstance(stmts[0], ast.Assign)   # _found = False
        assert isinstance(stmts[1], ast.For)
        assert isinstance(stmts[2], ast.If)


    def test_unknown_goal_raises(self):
        with pytest.raises(NotImplementedError):
            compile_goal(object(), self._db(), {}, "trail", [ast.Pass()])


# ── compile_body ──────────────────────────────────────────────────────────────


class TestCompileBody:
    """compile_body builds a conjunction chain ending with yield None."""

    def _db(self):
        return Database()

    def test_empty_body_yields_none(self):
        stmts = compile_body([], self._db(), {}, "trail")
        assert len(stmts) == 1
        stmt = stmts[0]
        assert isinstance(stmt, ast.Expr)
        assert isinstance(stmt.value, ast.Yield)

    def test_single_goal_wraps_yield(self):
        v = Var()
        vc = {v._id: "_vX"}
        stmts = compile_body([Is(left=v, right=1)], self._db(), vc, "trail")
        # Should have: mark, If(unify ...: yield None), undo
        assert len(stmts) == 3
        assert isinstance(stmts[0], ast.Assign)  # _mN = trail.mark()
        assert isinstance(stmts[1], ast.If)       # if unify(...):
        # The If body should contain yield None
        if_body = stmts[1].body
        assert any(isinstance(s, ast.Expr) and isinstance(s.value, ast.Yield) for s in if_body)

    def test_two_goals_chains_correctly(self):
        v = Var()
        vc = {v._id: "_vX"}
        # Is(v, 1) then Is(v, 2) — two-goal conjunction
        stmts = compile_body([Is(left=v, right=1), Is(left=v, right=2)], self._db(), vc, "trail")
        # The outermost is the first goal (Is(v, 1)) wrapping the second
        assert len(stmts) == 3   # mark, if, undo for first Is
        assert isinstance(stmts[0], ast.Assign)   # _m = trail.mark()


# ── Integration: compile_predicate with real bodies ──────────────────────────


def _drive(fn, *args_and_trail):
    """Drive a trampoline-compiled fn, yielding None per solution."""
    root = StepGenerator(fn, None, *args_and_trail)
    gen, value = root.send(None)
    while True:
        if gen is None:
            if value is DONE:
                return
            yield None
            gen, value = root.send(None)
        else:
            gen, value = gen.send(value)


def _run(fn, *args):
    """Collect all solutions from a compiled predicate."""
    trail = fresh_trail()
    return list(_drive(fn, *args, trail))


def _run_and_deref(fn, var, *args):
    """Run predicate, collect deref'd values of var for each solution."""
    trail = fresh_trail()
    results = []
    for _ in _drive(fn, *args, trail):
        results.append(deref(var))
    return results


class TestIntegrationFacts:
    """Predicates with no body (facts) still work after Step 5."""

    def test_fact_matches_and_yields(self):
        db = Database()
        db.assertz(Clause(head=Compound("ok", (1,)), body=[]))
        clauses = db.clauses_for("ok", 1)
        fn = compile_predicate("ok", 1, clauses, db)
        assert _run(fn, 1) == [None]
        assert _run(fn, 2) == []


class TestIntegrationUnification:
    """Is goal: unify two terms."""

    def test_unify_var_with_literal(self):
        x = Var()
        db = Database()
        db.assertz(Clause(head=Compound("foo", (x,)), body=[Is(left=x, right=42)]))
        clauses = db.clauses_for("foo", 1)
        fn = compile_predicate("foo", 1, clauses, db)

        v = Var()
        results = _run_and_deref(fn, v, v)
        assert results == [42]

    def test_unify_both_vars(self):
        x, y = Var(), Var()
        db = Database()
        db.assertz(Clause(head=Compound("unify_xy", (x, y)), body=[Is(left=x, right=y)]))
        clauses = db.clauses_for("unify_xy", 2)
        fn = compile_predicate("unify_xy", 2, clauses, db)

        a, b = Var(), Var()
        trail = fresh_trail()
        unified_during = []
        for _ in _drive(fn, a, b, trail):
            # Check binding while generator is paused (before undo)
            unified_during.append(deref(a) is b or deref(b) is a)
        assert len(unified_during) == 1
        assert unified_during[0], "a and b should be unified while suspended"

    def test_unify_fails_mismatch(self):
        x = Var()
        db = Database()
        db.assertz(Clause(head=Compound("foo", (x,)), body=[Is(left=x, right=1)]))
        clauses = db.clauses_for("foo", 1)
        fn = compile_predicate("foo", 1, clauses, db)

        # Pass literal 2 — head matches (Var captures 2), then Is(2, 1) fails
        assert _run(fn, 2) == []

    def test_bindings_undone_after_exhaustion(self):
        x = Var()
        db = Database()
        db.assertz(Clause(head=Compound("foo", (x,)), body=[Is(left=x, right=99)]))
        clauses = db.clauses_for("foo", 1)
        fn = compile_predicate("foo", 1, clauses, db)

        v = Var()
        trail = fresh_trail()
        mark = trail.mark()
        list(_drive(fn, v, trail))  # run to exhaustion
        trail.undo(mark)          # undo to before the call
        assert is_var_unbound(v, trail)

    def test_conjunction_two_is_goals(self):
        x, y = Var(), Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("both", (x, y)),
            body=[Is(left=x, right=10), Is(left=y, right=20)],
        ))
        clauses = db.clauses_for("both", 2)
        fn = compile_predicate("both", 2, clauses, db)

        a, b = Var(), Var()
        trail = fresh_trail()
        results_during = []
        for _ in _drive(fn, a, b, trail):
            # Check bindings while suspended (before undo)
            results_during.append((deref(a), deref(b)))
        assert results_during == [(10, 20)]


def is_var_unbound(v, trail) -> bool:
    """True if v is still unbound."""
    from clausal.logic.variables import is_var
    return is_var(deref(v))


class TestIntegrationComparisons:
    """Arithmetic and structural comparison goals."""

    def _make_gt_pred(self, threshold):
        x = Var()
        db = Database()
        db.assertz(Clause(head=Compound("big", (x,)), body=[Gt(left=x, right=threshold)]))
        clauses = db.clauses_for("big", 1)
        return compile_predicate("big", 1, clauses, db)

    def test_gt_succeeds(self):
        fn = self._make_gt_pred(0)
        assert _run(fn, 5) == [None]
        assert _run(fn, 1) == [None]

    def test_gt_fails(self):
        fn = self._make_gt_pred(0)
        assert _run(fn, 0) == []
        assert _run(fn, -1) == []

    def test_lt_succeeds(self):
        x = Var()
        db = Database()
        db.assertz(Clause(head=Compound("small", (x,)), body=[Lt(left=x, right=10)]))
        clauses = db.clauses_for("small", 1)
        fn = compile_predicate("small", 1, clauses, db)
        assert _run(fn, 5) == [None]
        assert _run(fn, 9) == [None]
        assert _run(fn, 10) == []

    def test_eq_structural(self):
        # Use two separate Vars in head; body checks eq between them after Is unification
        x, y = Var(), Var()
        db = Database()
        # same(X, Y) <- X is Y, X == Y  (unify then check structural eq)
        db.assertz(Clause(
            head=Compound("same", (x, y)),
            body=[Is(left=x, right=y), ArithEq(left=x, right=y)],
        ))
        clauses = db.clauses_for("same", 2)
        fn = compile_predicate("same", 2, clauses, db)
        # same(1, V) unifies V→1 then checks 1==1 → succeeds
        v = Var()
        trail = fresh_trail()
        results = list(_drive(fn, 1, v, trail))
        assert len(results) == 1

    def test_lte_boundary(self):
        x = Var()
        db = Database()
        db.assertz(Clause(head=Compound("lte10", (x,)), body=[LtE(left=x, right=10)]))
        clauses = db.clauses_for("lte10", 1)
        fn = compile_predicate("lte10", 1, clauses, db)
        assert _run(fn, 10) == [None]
        assert _run(fn, 11) == []


class TestIntegrationDisjunction:
    """Or goal: both branches tried."""

    def test_or_both_branches_explored(self):
        x = Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("either", (x,)),
            body=[Or(left=Is(left=x, right=1), right=Is(left=x, right=2))],
        ))
        clauses = db.clauses_for("either", 1)
        fn = compile_predicate("either", 1, clauses, db)

        v = Var()
        trail = fresh_trail()
        results = []
        for _ in _drive(fn, v, trail):
            results.append(deref(v))
        assert results == [1, 2]

    def test_or_left_fails_right_succeeds(self):
        x = Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("d", (x,)),
            body=[Or(left=Is(left=x, right="nope"), right=Is(left=x, right="yes"))],
        ))
        clauses = db.clauses_for("d", 1)
        fn = compile_predicate("d", 1, clauses, db)

        v = Var()
        trail = fresh_trail()
        results = []
        for _ in _drive(fn, v, trail):
            results.append(deref(v))
        # Is(v, "nope") then check "nope"≠"yes": left passes (binds v), yields 1
        # Then Is(v, "yes") where v may or may not be bound — depends on undo
        # Actually: after left branch undos, right branch: Is(v, "yes") binds v="yes", yields
        assert "yes" in results


class TestIntegrationNegation:
    """Not (negation-as-failure) goal."""

    def test_naf_succeeds_when_goal_fails(self):
        # no_such(X) <- X is None  (fails for non-None)
        # naf_test(X) <- not no_such(X)
        db = Database()
        no_v = Var()
        db.assertz(Clause(head=Compound("no_such", (no_v,)), body=[Is(left=no_v, right=None)]))
        compile_predicate("no_such", 1, db.clauses_for("no_such", 1), db)

        x = Var()
        db.assertz(Clause(
            head=Compound("naf_test", (x,)),
            body=[Not(operand=Call(func=LoadName(name="no_such"), args=[x], kwargs=[]))],
        ))
        fn = compile_predicate("naf_test", 1, db.clauses_for("naf_test", 1), db)
        # no_such(42) fails → NAF succeeds
        assert _run(fn, 42) == [None]
        # no_such(None) succeeds → NAF fails
        assert _run(fn, None) == []

    def test_naf_fails_when_goal_succeeds(self):
        db = Database()
        any_v = Var()
        db.assertz(Clause(head=Compound("always_ok", (any_v,)), body=[]))
        compile_predicate("always_ok", 1, db.clauses_for("always_ok", 1), db)

        x = Var()
        db.assertz(Clause(
            head=Compound("naf_test2", (x,)),
            body=[Not(operand=Call(func=LoadName(name="always_ok"), args=[x], kwargs=[]))],
        ))
        fn = compile_predicate("naf_test2", 1, db.clauses_for("naf_test2", 1), db)
        # always_ok succeeds → NAF fails → no yield
        assert _run(fn, 42) == []


class TestIntegrationMembership:
    """in_ goal: enumerate members of a list."""

    def test_in_finds_all_members(self):
        x = Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("member", (x,)),
            body=[in_(left=x, right=[1, 2, 3])],
        ))
        clauses = db.clauses_for("member", 1)
        fn = compile_predicate("member", 1, clauses, db)

        v = Var()
        trail = fresh_trail()
        results = []
        for _ in _drive(fn, v, trail):
            results.append(deref(v))
        assert results == [1, 2, 3]

    def test_in_with_ground_checks_membership(self):
        x = Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("mem", (x,)),
            body=[in_(left=x, right=[10, 20, 30])],
        ))
        clauses = db.clauses_for("mem", 1)
        fn = compile_predicate("mem", 1, clauses, db)

        assert _run(fn, 10) == [None]
        assert _run(fn, 20) == [None]
        assert _run(fn, 99) == []

    def test_not_in_succeeds_when_absent(self):
        x = Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("absent", (x,)),
            body=[NotIn(left=x, right=[1, 2, 3])],
        ))
        clauses = db.clauses_for("absent", 1)
        fn = compile_predicate("absent", 1, clauses, db)

        assert _run(fn, 99) == [None]
        assert _run(fn, 1) == []


class TestIntegrationPredicateCall:
    """Compile a body goal that calls another predicate."""

    def test_call_chain(self):
        """foo(X) calls bar(X); bar(X) unifies X with 7."""
        db = Database()

        bar_x = Var()
        db.assertz(Clause(head=Compound("bar", (bar_x,)), body=[Is(left=bar_x, right=7)]))
        compile_predicate("bar", 1, db.clauses_for("bar", 1), db)

        foo_x = Var()
        db.assertz(Clause(
            head=Compound("foo", (foo_x,)),
            body=[Call(func=LoadName(name="bar"), args=[foo_x], kwargs=[])],
        ))
        fn = compile_predicate("foo", 1, db.clauses_for("foo", 1), db)

        v = Var()
        results = _run_and_deref(fn, v, v)
        assert results == [7]

    def test_multi_clause_predicate(self):
        """color/1 has three clauses; querying with a Var enumerates all."""
        db = Database()
        for col in ("red", "green", "blue"):
            db.assertz(Clause(head=Compound("color", (col,)), body=[]))
        fn = compile_predicate("color", 1, db.clauses_for("color", 1), db)

        # Calling with a ground arg matches the appropriate clause
        assert _run(fn, "red") == [None]
        assert _run(fn, "purple") == []

    def test_recursive_predicate(self):
        """nat/1: nat(0). nat(s(X)) <- nat(X).  Count solutions for s(s(0))."""
        db = Database()

        @dataclasses.dataclass
        class s:
            _n: object = None

        # nat(0) <- True
        db.assertz(Clause(head=Compound("nat", (0,)), body=[]))
        # nat(s(X)) <- nat(X)
        inner_x = Var()
        db.assertz(Clause(
            head=Compound("nat", (Compound("s", (inner_x,)),)),
            body=[Call(func=LoadName(name="nat"), args=[inner_x], kwargs=[])],
        ))
        clauses = db.clauses_for("nat", 1)
        fn = compile_predicate("nat", 1, clauses, db)

        assert _run(fn, 0) == [None]
        assert _run(fn, Compound("s", (0,))) == [None]
        assert _run(fn, Compound("s", (Compound("s", (0,)),))) == [None]
        assert _run(fn, Compound("s", (1,))) == []   # 1 is not nat


class TestIntegrationArithmetic:
    """Arithmetic expressions inside comparison goals."""

    def test_add_in_gt(self):
        x = Var()
        db = Database()
        # big_enough(X) <- X + 1 > 5  (i.e. X > 4)
        db.assertz(Clause(
            head=Compound("big_enough", (x,)),
            body=[Gt(left=Add(left=x, right=1), right=5)],
        ))
        clauses = db.clauses_for("big_enough", 1)
        fn = compile_predicate("big_enough", 1, clauses, db)

        assert _run(fn, 5) == [None]   # 5+1=6 > 5 ✓
        assert _run(fn, 4) == []       # 4+1=5, 5>5 is False ✗
        assert _run(fn, 3) == []       # 3+1=4, 4>5 is False ✗
