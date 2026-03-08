"""Tests for clausal.logic.compiler — Step 4.

Tests cover:
  - head_to_match_pattern: all term types → correct ast.pattern
  - compile_head_to_match_case: structure of generated match_case arm
  - compile_predicate: dispatch function correctness and PredicateTable wiring
"""

from __future__ import annotations

import ast
import dataclasses

import pytest

from clausal.logic.compiler import (
    head_to_match_pattern,
    compile_head_to_match_case,
    compile_predicate,
)
from clausal.logic.database import Clause, Database
from clausal.logic.variables import Var, Trail
from clausal.terms import Compound


# ── Synthetic functor dataclasses ─────────────────────────────────────────────


@dataclasses.dataclass
class point:
    _x: object = None
    _y: object = None


@dataclasses.dataclass
class pair:
    left: object = None
    right: object = None


@dataclasses.dataclass
class wrapped:
    inner: object = None


# ── head_to_match_pattern ─────────────────────────────────────────────────────


class TestHeadToMatchPattern:
    """Unit tests for head_to_match_pattern."""

    # ── Var ──

    def test_unbound_var_gives_match_as(self):
        v = Var()
        ctx: dict[int, str] = {}
        p = head_to_match_pattern(v, ctx)
        assert isinstance(p, ast.MatchAs)
        assert p.name == f"_v{v._id}"
        assert p.pattern is None  # bare capture, no sub-pattern

    def test_var_registers_in_context(self):
        v = Var()
        ctx: dict[int, str] = {}
        head_to_match_pattern(v, ctx)
        assert v._id in ctx
        assert ctx[v._id] == f"_v{v._id}"

    def test_two_different_vars_different_names(self):
        v1, v2 = Var(), Var()
        ctx: dict[int, str] = {}
        p1 = head_to_match_pattern(v1, ctx)
        p2 = head_to_match_pattern(v2, ctx)
        assert p1.name != p2.name
        assert len(ctx) == 2

    # ── Singletons ──

    def test_none_gives_match_singleton(self):
        p = head_to_match_pattern(None, {})
        assert isinstance(p, ast.MatchSingleton)
        assert p.value is None

    def test_true_gives_match_singleton(self):
        p = head_to_match_pattern(True, {})
        assert isinstance(p, ast.MatchSingleton)
        assert p.value is True

    def test_false_gives_match_singleton(self):
        p = head_to_match_pattern(False, {})
        assert isinstance(p, ast.MatchSingleton)
        assert p.value is False

    # ── Scalar literals ──

    def test_int_gives_match_value(self):
        p = head_to_match_pattern(42, {})
        assert isinstance(p, ast.MatchValue)
        assert isinstance(p.value, ast.Constant)
        assert p.value.value == 42

    def test_float_gives_match_value(self):
        p = head_to_match_pattern(3.14, {})
        assert isinstance(p, ast.MatchValue)
        assert p.value.value == pytest.approx(3.14)

    def test_str_gives_match_value(self):
        p = head_to_match_pattern("hello", {})
        assert isinstance(p, ast.MatchValue)
        assert p.value.value == "hello"

    def test_bytes_gives_match_value(self):
        p = head_to_match_pattern(b"hi", {})
        assert isinstance(p, ast.MatchValue)
        assert p.value.value == b"hi"

    # ── Python list ──

    def test_empty_list_gives_empty_sequence(self):
        p = head_to_match_pattern([], {})
        assert isinstance(p, ast.MatchSequence)
        assert p.patterns == []

    def test_list_recurses_into_elements(self):
        v = Var()
        ctx: dict[int, str] = {}
        p = head_to_match_pattern([1, v, "x"], ctx)
        assert isinstance(p, ast.MatchSequence)
        assert len(p.patterns) == 3
        assert isinstance(p.patterns[0], ast.MatchValue)  # 1
        assert isinstance(p.patterns[1], ast.MatchAs)     # Var
        assert isinstance(p.patterns[2], ast.MatchValue)  # "x"
        assert v._id in ctx

    # ── Compound ──

    def test_compound_gives_match_class_on_compound(self):
        v = Var()
        ctx: dict[int, str] = {}
        term = Compound("foo", (v, 42))
        p = head_to_match_pattern(term, ctx)
        assert isinstance(p, ast.MatchClass)
        assert isinstance(p.cls, ast.Name)
        assert p.cls.id == "Compound"
        assert p.kwd_attrs == ["functor", "args"]
        assert len(p.kwd_patterns) == 2
        # functor pattern
        functor_pat = p.kwd_patterns[0]
        assert isinstance(functor_pat, ast.MatchValue)
        assert functor_pat.value.value == "foo"
        # args pattern: MatchSequence([MatchAs, MatchValue(42)])
        args_pat = p.kwd_patterns[1]
        assert isinstance(args_pat, ast.MatchSequence)
        assert len(args_pat.patterns) == 2
        assert isinstance(args_pat.patterns[0], ast.MatchAs)   # v
        assert isinstance(args_pat.patterns[1], ast.MatchValue)  # 42
        assert v._id in ctx

    def test_compound_with_var_functor_gives_wildcard(self):
        v_functor = Var()
        term = Compound(v_functor, (1, 2))
        p = head_to_match_pattern(term, {})
        assert isinstance(p, ast.MatchAs)
        assert p.name is None  # wildcard

    # ── Functor dataclass ──

    def test_dataclass_gives_match_class_on_its_type(self):
        v = Var()
        ctx: dict[int, str] = {}
        term = point(_x=v, _y=99)
        p = head_to_match_pattern(term, ctx)
        assert isinstance(p, ast.MatchClass)
        assert isinstance(p.cls, ast.Name)
        assert p.cls.id == "point"
        assert p.kwd_attrs == ["_x", "_y"]
        assert len(p.kwd_patterns) == 2
        assert isinstance(p.kwd_patterns[0], ast.MatchAs)    # _x = Var
        assert isinstance(p.kwd_patterns[1], ast.MatchValue) # _y = 99
        assert v._id in ctx

    def test_dataclass_all_literals(self):
        ctx: dict[int, str] = {}
        term = point(_x=1, _y=2)
        p = head_to_match_pattern(term, ctx)
        assert isinstance(p, ast.MatchClass)
        assert ctx == {}  # no vars
        assert all(isinstance(kp, ast.MatchValue) for kp in p.kwd_patterns)

    def test_nested_dataclass(self):
        v = Var()
        ctx: dict[int, str] = {}
        inner = point(_x=v, _y=0)
        outer = pair(left=inner, right="done")
        p = head_to_match_pattern(outer, ctx)
        assert isinstance(p, ast.MatchClass)
        assert p.cls.id == "pair"
        # left → nested MatchClass
        left_pat = p.kwd_patterns[0]
        assert isinstance(left_pat, ast.MatchClass)
        assert left_pat.cls.id == "point"
        # right → MatchValue
        assert isinstance(p.kwd_patterns[1], ast.MatchValue)
        assert v._id in ctx

    # ── Unknown term → wildcard ──

    def test_unknown_term_gives_wildcard(self):
        p = head_to_match_pattern(object(), {})
        assert isinstance(p, ast.MatchAs)
        assert p.name is None


# ── compile_head_to_match_case ────────────────────────────────────────────────


class TestCompileHeadToMatchCase:
    """Unit tests for compile_head_to_match_case."""

    def test_returns_match_case(self):
        head = point(_x=1, _y=2)
        case_arm = compile_head_to_match_case(
            head=head,
            body_stmts=[ast.Pass()],
            var_context={},
            arity=2,
        )
        assert isinstance(case_arm, ast.match_case)

    def test_outer_pattern_is_match_sequence(self):
        head = point(_x=1, _y=2)
        case_arm = compile_head_to_match_case(
            head=head,
            body_stmts=[ast.Pass()],
            var_context={},
            arity=2,
        )
        assert isinstance(case_arm.pattern, ast.MatchSequence)
        assert len(case_arm.pattern.patterns) == 2

    def test_body_starts_with_trail_mark(self):
        head = point(_x=1, _y=2)
        case_arm = compile_head_to_match_case(
            head=head,
            body_stmts=[ast.Pass()],
            var_context={},
            arity=2,
        )
        first_stmt = case_arm.body[0]
        assert isinstance(first_stmt, ast.Assign)
        # targets[0] should be "_mark"
        assert isinstance(first_stmt.targets[0], ast.Name)
        assert first_stmt.targets[0].id == "_mark"

    def test_body_has_try_finally_with_undo(self):
        head = point(_x=1, _y=2)
        case_arm = compile_head_to_match_case(
            head=head,
            body_stmts=[ast.Pass()],
            var_context={},
            arity=2,
        )
        # Second statement is Try with finalbody containing undo call
        try_stmt = case_arm.body[1]
        assert isinstance(try_stmt, ast.Try)
        assert len(try_stmt.finalbody) == 1
        undo = try_stmt.finalbody[0]
        assert isinstance(undo, ast.Expr)
        call = undo.value
        assert isinstance(call, ast.Call)
        assert isinstance(call.func, ast.Attribute)
        assert call.func.attr == "undo"

    def test_var_context_populated_from_head(self):
        v = Var()
        head = point(_x=v, _y=42)
        var_context: dict[int, str] = {}
        compile_head_to_match_case(
            head=head,
            body_stmts=[ast.Pass()],
            var_context=var_context,
            arity=2,
        )
        assert v._id in var_context

    def test_body_stmts_in_try_block(self):
        head = point(_x=1, _y=2)
        sentinel = ast.Pass()
        case_arm = compile_head_to_match_case(
            head=head,
            body_stmts=[sentinel],
            var_context={},
            arity=2,
        )
        try_stmt = case_arm.body[1]
        assert sentinel in try_stmt.body


# ── compile_predicate ─────────────────────────────────────────────────────────


def _trail():
    return Trail()


def _make_db_with_clause(head, body=None):
    db = Database()
    db.assertz(Clause(head=head, body=body or []))
    return db


class TestCompilePredicate:
    """Tests for compile_predicate — dispatch function generation."""

    # ── No clauses → always fail ──

    def test_no_clauses_always_fails(self):
        db = Database()
        fn = compile_predicate("foo", 2, [], db)
        assert list(fn(1, 2, _trail(), None)) == []

    def test_no_clauses_is_generator(self):
        db = Database()
        fn = compile_predicate("foo", 0, [], db)
        import types
        gen = fn(_trail(), None)
        assert isinstance(gen, types.GeneratorType)

    def test_no_clauses_installs_dispatch_fn(self):
        db = Database()
        # We need a PredicateTable to install onto; assertz first creates it
        db.assertz(Clause(head=Compound("foo", (1, 2)), body=[]))
        db.retract(Compound("foo", (1, 2)))  # remove the clause but keep the table
        fn = compile_predicate("foo", 2, [], db)
        assert db.table_for("foo", 2).dispatch_fn is fn

    # ── Function naming ──

    def test_function_name_includes_functor_and_arity(self):
        db = _make_db_with_clause(point(_x=1, _y=2))
        clauses = db.clauses_for("point", 2)
        fn = compile_predicate("point", 2, clauses, db, globals_={"point": point})
        assert fn.__name__ == "point__2"

    def test_arity_zero_function_name(self):
        db = _make_db_with_clause(Compound("truth", ()))
        clauses = db.clauses_for("truth", 0)
        fn = compile_predicate("truth", 0, clauses, db)
        assert fn.__name__ == "truth__0"

    # ── Literal head matching ──

    def test_literal_head_matches_exact_args(self):
        head = point(_x=1, _y=2)
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("point", 2)
        fn = compile_predicate("point", 2, clauses, db, globals_={"point": point})
        assert list(fn(1, 2, _trail(), None)) == [None]

    def test_literal_head_fails_wrong_arg(self):
        head = point(_x=1, _y=2)
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("point", 2)
        fn = compile_predicate("point", 2, clauses, db, globals_={"point": point})
        assert list(fn(1, 99, _trail(), None)) == []

    def test_singleton_head_none(self):
        head = Compound("nil", ())
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("nil", 0)
        fn = compile_predicate("nil", 0, clauses, db)
        assert list(fn(_trail(), None)) == [None]

    # ── Var head matching ──

    def test_var_head_matches_any_value(self):
        v = Var()
        head = point(_x=v, _y=42)
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("point", 2)
        fn = compile_predicate("point", 2, clauses, db, globals_={"point": point})
        for val in ["hello", 0, True, None, object()]:
            assert list(fn(val, 42, _trail(), None)) == [None]

    def test_var_head_fails_wrong_literal(self):
        v = Var()
        head = point(_x=v, _y=42)
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("point", 2)
        fn = compile_predicate("point", 2, clauses, db, globals_={"point": point})
        assert list(fn("anything", 99, _trail(), None)) == []

    # ── Compound head matching ──

    def test_compound_head_matches_compound_term(self):
        v = Var()
        head = Compound("edge", (v, 42))
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("edge", 2)
        fn = compile_predicate("edge", 2, clauses, db)
        assert list(fn("from", 42, _trail(), None)) == [None]

    def test_compound_head_fails_wrong_second_arg(self):
        v = Var()
        head = Compound("edge", (v, 42))
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("edge", 2)
        fn = compile_predicate("edge", 2, clauses, db)
        assert list(fn("from", 99, _trail(), None)) == []

    # ── Nested dataclass head ──

    def test_nested_dataclass_head_matches(self):
        v = Var()
        head = pair(left=point(_x=v, _y=0), right="done")
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("pair", 2)
        fn = compile_predicate(
            "pair", 2, clauses, db, globals_={"pair": pair, "point": point}
        )
        inner = point(_x="anything", _y=0)
        assert list(fn(inner, "done", _trail(), None)) == [None]

    def test_nested_dataclass_fails_wrong_inner(self):
        v = Var()
        head = pair(left=point(_x=v, _y=0), right="done")
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("pair", 2)
        fn = compile_predicate(
            "pair", 2, clauses, db, globals_={"pair": pair, "point": point}
        )
        # inner has wrong _y
        inner = point(_x="anything", _y=99)
        assert list(fn(inner, "done", _trail(), None)) == []

    # ── Multi-clause predicate ──

    def test_multi_clause_each_can_match(self):
        """Multiple clauses: each matching arg routes to the correct clause."""
        db = Database()
        for color_name in ("red", "green", "blue"):
            db.assertz(Clause(head=Compound("color", (color_name,)), body=[]))
        clauses = db.clauses_for("color", 1)
        fn = compile_predicate("color", 1, clauses, db)
        t = _trail()
        assert list(fn("red", t, None)) == [None]
        assert list(fn("green", t, None)) == [None]
        assert list(fn("blue", t, None)) == [None]
        assert list(fn("purple", t, None)) == []

    def test_multi_clause_no_double_yield(self):
        """A specific arg matches exactly one literal clause, not multiple."""
        db = Database()
        db.assertz(Clause(head=Compound("x", (1,)), body=[]))
        db.assertz(Clause(head=Compound("x", (2,)), body=[]))
        clauses = db.clauses_for("x", 1)
        fn = compile_predicate("x", 1, clauses, db)
        assert list(fn(1, _trail(), None)) == [None]   # matches clause 1 only

    # ── PredicateTable wiring ──

    def test_installs_dispatch_fn_on_table(self):
        head = point(_x=1, _y=2)
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("point", 2)
        fn = compile_predicate("point", 2, clauses, db, globals_={"point": point})
        table = db.table_for("point", 2)
        assert table is not None
        assert table.dispatch_fn is fn

    def test_get_dispatch_works_after_compile(self):
        head = point(_x=1, _y=2)
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("point", 2)
        compile_predicate("point", 2, clauses, db, globals_={"point": point})
        fn = db.table_for("point", 2).get_dispatch()
        assert callable(fn)

    # ── custom body_compiler ──

    def test_custom_body_compiler_called_per_clause(self):
        """body_compiler is called once per clause with (clause, var_context)."""
        db = Database()
        db.assertz(Clause(head=Compound("a", (1,)), body=[]))
        db.assertz(Clause(head=Compound("a", (2,)), body=[]))
        clauses = db.clauses_for("a", 1)

        call_log = []

        def recorder(clause, var_context):
            call_log.append(clause)
            return [ast.Expr(value=ast.Yield(value=ast.Constant(value=None)))]

        compile_predicate("a", 1, clauses, db, body_compiler=recorder)
        assert len(call_log) == 2

    def test_custom_body_compiler_can_yield_multiple(self):
        """A body_compiler that yields twice gives 2 results per clause match."""
        db = _make_db_with_clause(Compound("multi", ()))

        def double_yield(clause, var_context):
            return [
                ast.Expr(value=ast.Yield(value=ast.Constant(value=1))),
                ast.Expr(value=ast.Yield(value=ast.Constant(value=2))),
            ]

        clauses = db.clauses_for("multi", 0)
        fn = compile_predicate("multi", 0, clauses, db, body_compiler=double_yield)
        assert list(fn(_trail(), None)) == [1, 2]

    # ── Trail mark/undo in case arm ──

    def test_trail_mark_and_undo_called_around_body(self):
        """Verify that trail.mark() and trail.undo() are called."""
        mark_calls = []
        undo_calls = []

        class FakeTrail:
            def mark(self):
                mark_calls.append(1)
                return len(mark_calls) - 1

            def undo(self, mark):
                undo_calls.append(mark)

        head = Compound("t", (1,))
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("t", 1)
        fn = compile_predicate("t", 1, clauses, db)

        list(fn(1, FakeTrail(), None))

        assert len(mark_calls) == 1
        assert len(undo_calls) == 1
        assert undo_calls[0] == mark_calls[0] - 1  # undo gets the returned mark value

    def test_trail_undo_called_even_if_body_empty(self):
        """Undo is called even when body yields nothing (head matched, body fails)."""
        undo_calls = []

        class FakeTrail:
            def mark(self):
                return 0
            def undo(self, mark):
                undo_calls.append(mark)

        head = Compound("u", (1,))
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("u", 1)

        def always_fail_body(clause, var_ctx):
            return [ast.Return(value=ast.Constant(value=None)),
                    ast.Expr(value=ast.Yield(value=ast.Constant(value=None)))]

        fn = compile_predicate("u", 1, clauses, db, body_compiler=always_fail_body)
        list(fn(1, FakeTrail(), None))
        assert len(undo_calls) == 1
