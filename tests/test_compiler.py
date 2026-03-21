"""Tests for clausal.logic.compiler — Step 4.

Tests cover:
  - head_to_match_pattern: all term types → correct ast.pattern
  - compile_head_to_match_case: structure of generated match_case arm
  - compile_predicate: dispatch function correctness and dispatch fn wiring
"""

from __future__ import annotations

import ast
import dataclasses

import pytest

from clausal.logic.compiler import (
    head_to_match_pattern,
    compile_head_to_match_case,
    compile_predicate_trampoline as compile_predicate,
    _head_list_unify_input,
    _head_list_unify_output,
)
from clausal.logic.database import Clause, Database
from clausal.logic.trampoline import StepGenerator, DONE
from clausal.logic.solve import call
from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.pythonic_ast.nodes import StarUnpack
from clausal.terms import Compound


# ── Trampoline dispatch driver ────────────────────────────────────────────────


def _run_dispatch(fn, *args_and_trail):
    """Drive a trampoline-protocol fn, yield per solution."""
    root = StepGenerator(fn, None, *args_and_trail)
    gen, value = root.send(None)
    while True:
        if gen is None:
            if value is DONE:
                return
            yield value
            gen, value = root.send(None)
        else:
            gen, value = gen.send(value)


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

    def test_empty_list_gives_wildcard_capture(self):
        list_guards: list = []
        p = head_to_match_pattern([], {}, list_guards=list_guards)
        # Lists now compile as wildcard captures + list_guards
        assert isinstance(p, ast.MatchAs)
        assert p.name.startswith("_lcap")
        assert len(list_guards) == 1

    def test_list_registers_vars_in_context(self):
        v = Var()
        ctx: dict[int, str] = {}
        list_guards: list = []
        p = head_to_match_pattern([1, v, "x"], ctx, list_guards=list_guards)
        # Lists compile as wildcard captures
        assert isinstance(p, ast.MatchAs)
        assert v._id in ctx
        assert len(list_guards) == 1

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
        assert list(_run_dispatch(fn, 1, 2, _trail())) == []

    def test_no_clauses_is_generator(self):
        db = Database()
        fn = compile_predicate("foo", 0, [], db)
        import types
        gen = StepGenerator(fn, None, _trail())
        assert hasattr(gen, 'send')

    def test_no_clauses_installs_dispatch_fn(self):
        db = Database()
        fn = compile_predicate("foo", 2, [], db)
        assert db.get_dispatch("foo", 2) is fn

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
        assert list(_run_dispatch(fn, 1, 2, _trail())) == [None]

    def test_literal_head_fails_wrong_arg(self):
        head = point(_x=1, _y=2)
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("point", 2)
        fn = compile_predicate("point", 2, clauses, db, globals_={"point": point})
        assert list(_run_dispatch(fn, 1, 99, _trail())) == []

    def test_singleton_head_none(self):
        head = Compound("nil", ())
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("nil", 0)
        fn = compile_predicate("nil", 0, clauses, db)
        assert list(_run_dispatch(fn, _trail())) == [None]

    # ── Var head matching ──

    def test_var_head_matches_any_value(self):
        v = Var()
        head = point(_x=v, _y=42)
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("point", 2)
        fn = compile_predicate("point", 2, clauses, db, globals_={"point": point})
        for val in ["hello", 0, True, None, object()]:
            assert list(_run_dispatch(fn, val, 42, _trail())) == [None]

    def test_var_head_fails_wrong_literal(self):
        v = Var()
        head = point(_x=v, _y=42)
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("point", 2)
        fn = compile_predicate("point", 2, clauses, db, globals_={"point": point})
        assert list(_run_dispatch(fn, "anything", 99, _trail())) == []

    # ── Compound head matching ──

    def test_compound_head_matches_compound_term(self):
        v = Var()
        head = Compound("edge", (v, 42))
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("edge", 2)
        fn = compile_predicate("edge", 2, clauses, db)
        assert list(_run_dispatch(fn, "from", 42, _trail())) == [None]

    def test_compound_head_fails_wrong_second_arg(self):
        v = Var()
        head = Compound("edge", (v, 42))
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("edge", 2)
        fn = compile_predicate("edge", 2, clauses, db)
        assert list(_run_dispatch(fn, "from", 99, _trail())) == []

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
        assert list(_run_dispatch(fn, inner, "done", _trail())) == [None]

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
        assert list(_run_dispatch(fn, inner, "done", _trail())) == []

    # ── Multi-clause predicate ──

    def test_multi_clause_each_can_match(self):
        """Multiple clauses: each matching arg routes to the correct clause."""
        db = Database()
        for color_name in ("red", "green", "blue"):
            db.assertz(Clause(head=Compound("color", (color_name,)), body=[]))
        clauses = db.clauses_for("color", 1)
        fn = compile_predicate("color", 1, clauses, db)
        t = _trail()
        assert list(_run_dispatch(fn, "red", t)) == [None]
        assert list(_run_dispatch(fn, "green", t)) == [None]
        assert list(_run_dispatch(fn, "blue", t)) == [None]
        assert list(_run_dispatch(fn, "purple", t)) == []

    def test_multi_clause_no_double_yield(self):
        """A specific arg matches exactly one literal clause, not multiple."""
        db = Database()
        db.assertz(Clause(head=Compound("x", (1,)), body=[]))
        db.assertz(Clause(head=Compound("x", (2,)), body=[]))
        clauses = db.clauses_for("x", 1)
        fn = compile_predicate("x", 1, clauses, db)
        assert list(_run_dispatch(fn, 1, _trail())) == [None]   # matches clause 1 only

    # ── Database dispatch wiring ──

    def test_installs_dispatch_fn_on_table(self):
        head = point(_x=1, _y=2)
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("point", 2)
        fn = compile_predicate("point", 2, clauses, db, globals_={"point": point})
        assert db.get_dispatch("point", 2) is fn

    def test_get_dispatch_works_after_compile(self):
        head = point(_x=1, _y=2)
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("point", 2)
        compile_predicate("point", 2, clauses, db, globals_={"point": point})
        fn = db.get_dispatch("point", 2)
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
            # Trampoline protocol: yield (_tramp_parent, None)
            return [ast.Expr(value=ast.Yield(value=ast.Tuple(
                elts=[ast.Name(id="_tramp_parent", ctx=ast.Load()),
                      ast.Constant(value=None)],
                ctx=ast.Load(),
            )))]

        compile_predicate("a", 1, clauses, db, body_compiler=recorder)
        assert len(call_log) == 2

    def test_custom_body_compiler_can_yield_multiple(self):
        """A body_compiler that yields twice gives 2 results per clause match."""
        db = _make_db_with_clause(Compound("multi", ()))

        def double_yield(clause, var_context):
            # Trampoline protocol: yield (_tramp_parent, value)
            def _make_yield(val):
                return ast.Expr(value=ast.Yield(value=ast.Tuple(
                    elts=[ast.Name(id="_tramp_parent", ctx=ast.Load()),
                          ast.Constant(value=val)],
                    ctx=ast.Load(),
                )))
            return [_make_yield(1), _make_yield(2)]

        clauses = db.clauses_for("multi", 0)
        fn = compile_predicate("multi", 0, clauses, db, body_compiler=double_yield)
        assert list(_run_dispatch(fn, _trail())) == [1, 2]

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

        list(_run_dispatch(fn, 1, FakeTrail()))

        assert len(mark_calls) == 1
        assert len(undo_calls) == 1
        assert undo_calls[0] == mark_calls[0] - 1  # undo gets the returned mark value

    def test_trail_undo_called_after_solutions_exhausted(self):
        """Trail.undo is called after head matches and solutions are exhausted."""
        undo_calls = []

        class FakeTrail:
            def mark(self):
                return 0
            def undo(self, mark):
                undo_calls.append(mark)

        head = Compound("u", (1,))
        db = _make_db_with_clause(head)
        clauses = db.clauses_for("u", 1)

        fn = compile_predicate("u", 1, clauses, db)
        list(_run_dispatch(fn, 1, FakeTrail()))
        assert len(undo_calls) >= 1


# ── head_to_match_pattern: list + star patterns ──────────────────────────────


class TestHeadListPatterns:
    """Tests for list patterns [HEAD, *TAIL] in clause heads."""

    # ── head_to_match_pattern with StarUnpack ──

    def test_star_list_produces_wildcard_capture(self):
        h, t = Var(), Var()
        ctx: dict[int, str] = {}
        list_guards: list = []
        p = head_to_match_pattern([h, StarUnpack(value=t)], ctx, list_guards=list_guards)
        assert isinstance(p, ast.MatchAs)
        assert p.name.startswith("_lcap")

    def test_star_list_registers_both_vars(self):
        h, t = Var(), Var()
        ctx: dict[int, str] = {}
        list_guards: list = []
        head_to_match_pattern([h, StarUnpack(value=t)], ctx, list_guards=list_guards)
        assert h._id in ctx
        assert t._id in ctx

    def test_star_list_records_list_guard(self):
        h, t = Var(), Var()
        ctx: dict[int, str] = {}
        list_guards: list = []
        head_to_match_pattern([h, StarUnpack(value=t)], ctx, list_guards=list_guards)
        assert len(list_guards) == 1
        cap_name, before, star, after, vc = list_guards[0]
        assert cap_name == "_lcap0"
        assert len(before) == 1  # [HEAD]
        assert is_var(before[0])
        assert is_var(star)      # *TAIL
        assert after == []

    def test_star_middle_pattern(self):
        """[A, *MID, Z] records before=[A], star=MID, after=[Z]."""
        a, mid, z = Var(), Var(), Var()
        ctx: dict[int, str] = {}
        list_guards: list = []
        head_to_match_pattern(
            [a, StarUnpack(value=mid), z], ctx, list_guards=list_guards
        )
        assert len(list_guards) == 1
        _, before, star, after, _ = list_guards[0]
        assert len(before) == 1 and is_var(before[0])
        assert is_var(star)
        assert len(after) == 1 and is_var(after[0])

    def test_no_star_list_still_records_guard(self):
        """A plain list [X, 42] also uses list guard (no MatchSequence)."""
        x = Var()
        ctx: dict[int, str] = {}
        list_guards: list = []
        head_to_match_pattern([x, 42], ctx, list_guards=list_guards)
        assert len(list_guards) == 1
        _, before, star, after, _ = list_guards[0]
        assert len(before) == 2
        assert star is None
        assert after == []

    # ── Repeated vars in head patterns ──

    def test_repeated_var_produces_dup_guard(self):
        v = Var()
        ctx: dict[int, str] = {}
        dup_guards: list = []
        # First occurrence → normal capture
        p1 = head_to_match_pattern(v, ctx, dup_guards=dup_guards)
        assert isinstance(p1, ast.MatchAs)
        orig_name = p1.name
        # Second occurrence → dup capture
        p2 = head_to_match_pattern(v, ctx, dup_guards=dup_guards)
        assert isinstance(p2, ast.MatchAs)
        assert p2.name != orig_name
        assert "__dup" in p2.name
        assert len(dup_guards) == 1
        assert dup_guards[0] == (orig_name, p2.name)

    def test_repeated_var_across_list_patterns(self):
        """HEAD in [HEAD, *TAIL] and [HEAD, *RESULT] — same var_context entry, two list guards."""
        h, t, r = Var(), Var(), Var()
        ctx: dict[int, str] = {}
        list_guards: list = []
        head_to_match_pattern([h, StarUnpack(value=t)], ctx, list_guards=list_guards)
        head_to_match_pattern([h, StarUnpack(value=r)], ctx, list_guards=list_guards)
        assert len(list_guards) == 2
        # Both guards reference the same HEAD var
        _, before1, _, _, vc1 = list_guards[0]
        _, before2, _, _, vc2 = list_guards[1]
        assert vc1[h._id] == vc2[h._id]  # same python name


class TestNestedStarListPatterns:
    """Tests for nested star-list patterns like [[HEAD, *TAIL], *ROWS]."""

    def test_nested_star_flattens_to_proxy_var(self):
        """[[HEAD, *TAIL], *ROWS] → outer guard with proxy + inner sub-guard."""
        head, tail, rows = Var(), Var(), Var()
        ctx: dict[int, str] = {}
        list_guards: list = []
        p = head_to_match_pattern(
            [
                [head, StarUnpack(value=tail)],
                StarUnpack(value=rows),
            ],
            ctx,
            list_guards=list_guards,
        )
        assert isinstance(p, ast.MatchAs)
        # Should produce 2 guards: outer + inner sub-guard
        assert len(list_guards) == 2
        # Outer guard: proxy var + *ROWS
        _, outer_before, outer_star, outer_after, _ = list_guards[0]
        assert len(outer_before) == 1
        proxy = outer_before[0]
        assert is_var(proxy)         # fresh proxy, not HEAD
        assert proxy._id != head._id
        assert is_var(outer_star)    # ROWS
        # Inner guard: HEAD + *TAIL, target is the proxy
        inner_cap, inner_before, inner_star, inner_after, _ = list_guards[1]
        assert inner_cap == ctx[proxy._id]  # target is proxy's python name
        assert len(inner_before) == 1
        assert inner_before[0] is head
        assert inner_star is tail
        assert inner_after == []

    def test_nested_star_registers_all_vars(self):
        """All vars (HEAD, TAIL, ROWS, proxy) are registered in var_context."""
        head, tail, rows = Var(), Var(), Var()
        ctx: dict[int, str] = {}
        list_guards: list = []
        head_to_match_pattern(
            [[head, StarUnpack(value=tail)], StarUnpack(value=rows)],
            ctx,
            list_guards=list_guards,
        )
        assert head._id in ctx
        assert tail._id in ctx
        assert rows._id in ctx

    def test_double_nested_star(self):
        """[[[X, *Y], *Z], *W] produces 3 guards."""
        x, y, z, w = Var(), Var(), Var(), Var()
        ctx: dict[int, str] = {}
        list_guards: list = []
        head_to_match_pattern(
            [
                [[x, StarUnpack(value=y)], StarUnpack(value=z)],
                StarUnpack(value=w),
            ],
            ctx,
            list_guards=list_guards,
        )
        assert len(list_guards) == 3
        # All vars registered
        assert x._id in ctx
        assert y._id in ctx
        assert z._id in ctx
        assert w._id in ctx

    def test_nested_star_no_star_in_inner(self):
        """[[A, B], *REST] — inner list has no star, no sub-guard needed."""
        a, b, rest = Var(), Var(), Var()
        ctx: dict[int, str] = {}
        list_guards: list = []
        head_to_match_pattern(
            [[a, b], StarUnpack(value=rest)],
            ctx,
            list_guards=list_guards,
        )
        # Only 1 guard — the inner [A, B] is a plain list (no star), not flattened
        assert len(list_guards) == 1


# ── Integration tests: nested star patterns via .clausal loading ─────────────


class TestNestedStarIntegration:
    """End-to-end tests for nested star-list patterns loaded from .clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request, tmp_path_factory):
        from clausal.import_hook import _load_module
        tmp = tmp_path_factory.mktemp("nested_star")
        p = tmp / "nested_star.clausal"
        p.write_text(
            "Extract([[HEAD, *TAIL], *ROWS], HEAD, TAIL, ROWS),\n"
            "\n"
            "First([HEAD, *_REST], HEAD),\n"
            "\n"
            "Deep([[[X, *Y], *Z], *W], X, Y, Z, W),\n"
            "\n"
            "Transpose([], []),\n"
            "Transpose([[], *_MORE], []),\n"
            "Transpose(MATRIX, [HEADS, *REST_COLS]) <- (\n"
            "    ExtractColumn(MATRIX, HEADS, TAILS),\n"
            "    Transpose(TAILS, REST_COLS)\n"
            ")\n"
            "ExtractColumn([], [], []),\n"
            "ExtractColumn([[HEAD, *TAIL], *ROWS], [HEAD, *REST_HEADS], [TAIL, *REST_TAILS]) <- (\n"
            "    ExtractColumn(ROWS, REST_HEADS, REST_TAILS)\n"
            ")\n"
        )
        mod = _load_module("nested_star", str(p))
        request.cls.module = mod.__dict__["$module"]

    def _succeeds(self, functor, *args):
        for _ in call(functor, *args, module=self.module):
            return True
        return False

    def _first(self, functor, *args, out_indices=None):
        """Call with Vars at out_indices, return first deref'd results."""
        if out_indices is None:
            out_indices = [-1]
        full = list(args)
        out_vars = []
        for idx in out_indices:
            v = Var()
            out_vars.append(v)
            if idx == -1:
                full.append(v)
            else:
                full.insert(idx, v)
        for _ in call(functor, *full, module=self.module):
            return tuple(deref(v) for v in out_vars)
        return None

    def test_extract_head_tail_rows(self):
        h, t, r = Var(), Var(), Var()
        for _ in call("Extract", [[10, 20, 30], [40, 50]], h, t, r, module=self.module):
            assert deref(h) == 10
            assert deref(t) == [20, 30]
            assert deref(r) == [[40, 50]]
            return
        pytest.fail("Extract did not match")

    def test_extract_single_element_inner(self):
        h, t, r = Var(), Var(), Var()
        for _ in call("Extract", [[42], [1, 2]], h, t, r, module=self.module):
            assert deref(h) == 42
            assert deref(t) == []
            assert deref(r) == [[1, 2]]
            return
        pytest.fail("Extract did not match")

    def test_extract_single_row(self):
        h, t, r = Var(), Var(), Var()
        for _ in call("Extract", [[5, 6, 7]], h, t, r, module=self.module):
            assert deref(h) == 5
            assert deref(t) == [6, 7]
            assert deref(r) == []
            return
        pytest.fail("Extract did not match")

    def test_first(self):
        f = Var()
        for _ in call("First", [7, 8, 9], f, module=self.module):
            assert deref(f) == 7
            return
        pytest.fail("First did not match")

    def test_deep_triple_nesting(self):
        x, y, z, w = Var(), Var(), Var(), Var()
        for _ in call("Deep", [[[1, 2, 3], [4, 5]], [6, 7]], x, y, z, w, module=self.module):
            assert deref(x) == 1
            assert deref(y) == [2, 3]
            assert deref(z) == [[4, 5]]
            assert deref(w) == [[6, 7]]
            return
        pytest.fail("Deep did not match")

    def test_transpose_2x3(self):
        r = Var()
        for _ in call("Transpose", [[1, 2, 3], [4, 5, 6]], r, module=self.module):
            assert deref(r) == [[1, 4], [2, 5], [3, 6]]
            return
        pytest.fail("Transpose did not match")

    def test_transpose_3x2(self):
        r = Var()
        for _ in call("Transpose", [[1, 2], [3, 4], [5, 6]], r, module=self.module):
            assert deref(r) == [[1, 3, 5], [2, 4, 6]]
            return
        pytest.fail("Transpose did not match")

    def test_transpose_empty_rows(self):
        assert self._succeeds("Transpose", [[], []], [])

    def test_transpose_empty_matrix(self):
        assert self._succeeds("Transpose", [], [])


# ── _head_list_unify_input / _head_list_unify_output ─────────────────────────


class TestHeadListUnify:
    """Unit tests for the bidirectional list unification runtime helpers."""

    # ── Input mode (destructuring) ──

    def test_input_simple_list(self):
        trail = Trail()
        v0, v1 = Var(), Var()
        result = _head_list_unify_input([10, 20], [v0, v1], None, [], trail)
        assert result is True
        assert deref(v0) == 10
        assert deref(v1) == 20

    def test_input_star_list(self):
        trail = Trail()
        h, t = Var(), Var()
        result = _head_list_unify_input([1, 2, 3], [h], t, [], trail)
        assert result is True
        assert deref(h) == 1
        assert deref(t) == [2, 3]

    def test_input_star_middle(self):
        trail = Trail()
        a, mid, z = Var(), Var(), Var()
        result = _head_list_unify_input([1, 2, 3, 4], [a], mid, [z], trail)
        assert result is True
        assert deref(a) == 1
        assert deref(mid) == [2, 3]
        assert deref(z) == 4

    def test_input_empty_star(self):
        trail = Trail()
        h, t = Var(), Var()
        result = _head_list_unify_input([1], [h], t, [], trail)
        assert result is True
        assert deref(h) == 1
        assert deref(t) == []

    def test_input_too_short_fails(self):
        trail = Trail()
        h, t = Var(), Var()
        result = _head_list_unify_input([], [h], t, [], trail)
        assert result is False

    def test_input_no_star_wrong_length_fails(self):
        trail = Trail()
        v0 = Var()
        result = _head_list_unify_input([1, 2], [v0], None, [], trail)
        assert result is False

    def test_input_non_list_fails(self):
        trail = Trail()
        v = Var()
        result = _head_list_unify_input(42, [v], None, [], trail)
        assert result is False

    # ── Deferred mode (target is unbound Var) ──

    def test_input_var_defers(self):
        trail = Trail()
        target = Var()
        v = Var()
        result = _head_list_unify_input(target, [v], None, [], trail)
        assert result is None

    # ── Output mode (construction) ──

    def test_output_constructs_list(self):
        trail = Trail()
        target = Var()
        h, t = Var(), Var()
        unify(h, 1, trail)
        unify(t, [2, 3], trail)
        result = _head_list_unify_output(target, [h], t, [], trail)
        assert result is True
        assert deref(target) == [1, 2, 3]

    def test_output_with_after(self):
        trail = Trail()
        target = Var()
        a, mid, z = Var(), Var(), Var()
        unify(a, 1, trail)
        unify(mid, [2, 3], trail)
        unify(z, 4, trail)
        result = _head_list_unify_output(target, [a], mid, [z], trail)
        assert result is True
        assert deref(target) == [1, 2, 3, 4]

    def test_output_empty_star(self):
        trail = Trail()
        target = Var()
        h = Var()
        star = Var()
        unify(h, 42, trail)
        unify(star, [], trail)
        result = _head_list_unify_output(target, [h], star, [], trail)
        assert result is True
        assert deref(target) == [42]

    def test_output_unbound_star_fails(self):
        """Can't construct when star var is still unbound."""
        trail = Trail()
        target = Var()
        h = Var()
        star = Var()
        unify(h, 1, trail)
        # star is still unbound
        result = _head_list_unify_output(target, [h], star, [], trail)
        assert result is False

    def test_output_already_bound_switches_to_input(self):
        """If target was bound by the body, output falls back to input mode."""
        trail = Trail()
        target = Var()
        unify(target, [1, 2, 3], trail)
        h, t = Var(), Var()
        result = _head_list_unify_output(target, [h], t, [], trail)
        assert result is True
        assert deref(h) == 1
        assert deref(t) == [2, 3]
