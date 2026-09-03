"""Tests for the `_clausal_new` generated fast constructor (Phase 0, Task 1).

``PredicateMeta.__call__`` (the slow path) is unchanged.  ``_clausal_new`` is
an ADDITIVE, per-class, exec-generated classmethod: positional-only, no
missing-field backfill, no arity checking.  It exists so a later compiler
task can emit it for statically-saturated construction.
"""

import ast

import pytest

from clausal.logic.predicate import make_predicate
from clausal.logic.compiler.terms_to_ast import term_to_ast_expr
from clausal.logic.compiler import (
    compile_predicate_trampoline,
    compile_predicate_trampoline_ast,
)
from clausal.logic.database import Clause, Database
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.terms import Compound, Unify as Is
from clausal.pythonic_ast.nodes import BinOp


class TestFastConstructorBasics:
    def test_fast_new_matches_slow_path(self):
        # nv
        foo = make_predicate("foo", ["x", "y"])
        fast = foo._clausal_new(1, 2)
        slow = foo(1, 2)
        assert type(fast) is foo
        assert fast.x == 1
        assert fast.y == 2
        assert fast == slow
        assert fast is not slow

    def test_fast_new_single_field(self):
        # nv
        bar = make_predicate("bar", ["a"])
        fast = bar._clausal_new(42)
        assert fast.a == 42
        assert fast == bar(42)


class TestAtomsGetNoFastConstructor:
    def test_atom_class_has_no_clausal_new(self):
        # nv
        red = make_predicate("red", [])
        assert "_clausal_new" not in vars(red)


class TestFieldNamedClausalNew:
    def test_field_named_clausal_new_uses_slow_path_only(self):
        # nv
        weird = make_predicate("weird", ["_clausal_new"])
        # class creation must not raise, and the slow path still works
        t = weird(_clausal_new=5)
        assert t._clausal_new == 5

    def test_field_named_clausal_new_gets_no_fast_constructor(self):
        # nv
        weird = make_predicate("weird2", ["_clausal_new"])
        # "_clausal_new" is a field name here, so __slots__ owns the class
        # attribute (a member descriptor) at that name. The fast-new factory
        # must not clobber it with a classmethod.
        assert "_clausal_new" in weird.__slots__
        assert not isinstance(vars(weird)["_clausal_new"], classmethod)


class TestCacheShareByFieldTuple:
    def test_two_same_named_classes_each_get_working_fast_new(self):
        # nv
        foo1 = make_predicate("foo", ["x"])
        foo2 = make_predicate("foo", ["x"])
        assert foo1 is not foo2
        f1 = foo1._clausal_new(10)
        f2 = foo2._clausal_new(20)
        assert type(f1) is foo1
        assert type(f2) is foo2
        assert f1.x == 10
        assert f2.x == 20


class TestStructuralParity:
    def test_fast_path_instances_unhashable(self):
        # nv
        baz = make_predicate("baz", ["x"])
        fast = baz._clausal_new(1)
        assert baz.__hash__ is None
        with pytest.raises(TypeError):
            hash(fast)

    def test_fast_path_equal_to_slow_path(self):
        # nv
        qux = make_predicate("qux", ["x", "y"])
        fast = qux._clausal_new(1, 2)
        slow = qux(x=1, y=2)
        assert fast == slow
        assert slow == fast

    def test_fast_path_match_args_pattern_matching(self):
        # nv
        quux = make_predicate("quux", ["x", "y"])
        fast = quux._clausal_new(1, 2)
        match fast:
            case quux(x=vx, y=vy):
                assert vx == 1
                assert vy == 2
            case _:
                pytest.fail("pattern match against fast-path instance failed")


# ── Task 2: the emitter uses the fast path for saturated construction ───────
#
# ``term_to_ast_expr``'s ``is_term_instance`` branch emits
# ``Cls._clausal_new(v0, .., vn)`` (positional, no keywords) instead of
# ``Cls(name=v0, ...)`` when: the term's class is a PredicateMeta class, that
# class carries a generated ``_clausal_new`` (own ``vars(cls)``, not
# inherited), and none of its fields are named ``position``/``_position``
# (the pre-existing skip-filter — those classes must keep today's behaviour
# byte-identical). Everything else — pythonic_ast dataclass nodes, and any
# position-field class — keeps the keyword-call emission unchanged.


class TestEmitterFastPathUnit:
    def test_plain_predicate_meta_term_emits_clausal_new(self):
        # nv
        foo = make_predicate("emit_foo", ["x", "y"])
        term = foo(x=1, y=2)
        expr = term_to_ast_expr(term, {})
        src = ast.unparse(expr)
        assert "_clausal_new" in src
        assert isinstance(expr, ast.Call)
        assert isinstance(expr.func, ast.Attribute)
        assert expr.func.attr == "_clausal_new"
        assert isinstance(expr.func.value, ast.Name)
        assert expr.func.value.id == "emit_foo"
        assert expr.keywords == []
        assert [type(a) for a in expr.args] == [ast.Constant, ast.Constant]

    def test_dataclass_node_never_takes_fast_path(self):
        # nv — pythonic_ast dataclass nodes must never take the fast path:
        # their __init__ has defaults/validation that _clausal_new skips.
        term = BinOp(left=1, right=2)
        expr = term_to_ast_expr(term, {})
        src = ast.unparse(expr)
        assert "_clausal_new" not in src
        assert isinstance(expr, ast.Call)
        assert isinstance(expr.func, ast.Name)
        assert expr.func.id == "BinOp"
        assert expr.keywords != []

    def test_position_field_class_keeps_keyword_emission(self):
        # nv — a PredicateMeta class with a field literally named "position"
        # hits the pre-existing skip-filter and must NOT take the fast path,
        # even though it has a working _clausal_new.
        posy = make_predicate("emit_posy", ["position"])
        assert "_clausal_new" in vars(posy)  # sanity: otherwise eligible
        term = posy(position=1)
        expr = term_to_ast_expr(term, {})
        src = ast.unparse(expr)
        assert "_clausal_new" not in src
        assert isinstance(expr.func, ast.Name)
        assert expr.func.id == "emit_posy"
        # the "position" field itself is filtered out of the keyword emission
        assert expr.keywords == []

    def test_underscore_position_field_class_keeps_keyword_emission(self):
        # nv
        posy2 = make_predicate("emit_posy2", ["_position"])
        term = posy2(_position=1)
        expr = term_to_ast_expr(term, {})
        assert "_clausal_new" not in ast.unparse(expr)
        assert isinstance(expr.func, ast.Name)

    def test_field_named_clausal_new_keeps_keyword_emission(self):
        # nv — regression test for the emitter gate reading
        # ``"_clausal_new" in vars(cls)``: that's True for a class whose
        # FIELD happens to be named "_clausal_new" too, because __slots__
        # puts a member_descriptor at that class attribute (see
        # TestFieldNamedClausalNew in this file — the class-creation guard
        # skips attaching the generated classmethod there). The old gate
        # emitted ``weird_pred._clausal_new(5)``, which raises
        # ``TypeError: 'member_descriptor' object is not callable`` at
        # runtime since ``_clausal_new`` on this class is the slot
        # descriptor, not the fast constructor. The gate must ask whether
        # ``vars(cls)["_clausal_new"]`` IS a classmethod, not whether the
        # name is merely present, so this must keep the keyword-call
        # (slow-path) emission.
        weird = make_predicate("weird_pred", ["_clausal_new"])
        assert "_clausal_new" in vars(weird)  # present ...
        assert not isinstance(vars(weird)["_clausal_new"], classmethod)  # ... but not a classmethod
        term = weird(_clausal_new=5)
        expr = term_to_ast_expr(term, {})
        src = ast.unparse(expr)
        assert "._clausal_new(" not in src
        assert isinstance(expr, ast.Call)
        assert isinstance(expr.func, ast.Name)
        assert expr.func.id == "weird_pred"
        assert len(expr.keywords) == 1
        assert expr.keywords[0].arg == "_clausal_new"
        # The emitted expression, evaluated, behaves exactly like the old
        # keyword-construction path: weird_pred(_clausal_new=5).
        ns = {"weird_pred": weird}
        expr_ast = ast.fix_missing_locations(ast.Expression(body=expr))
        rebuilt = eval(compile(expr_ast, "<test>", "eval"), ns)  # noqa: S307
        assert rebuilt == term
        assert rebuilt._clausal_new == 5


class TestEmitterFastPathIntegration:
    def test_compiled_body_construction_parity_with_slow_path(self):
        # nv — a clause body that constructs a saturated compound as data
        # (``R is pt(X, Y)``): the compiled source takes the fast path, and
        # the answer it produces is the SAME as one built via the slow path.
        pt = make_predicate("emit_pt", ["x", "y"])
        assert "_clausal_new" in vars(pt)  # sanity: fast-path eligible

        hx, hy, hr = Var(), Var(), Var()
        head = Compound("emit_mk", (hx, hy, hr))
        body = [Is(left=hr, right=pt(x=hx, y=hy))]
        clause = Clause(head=head, body=body)

        db = Database()
        db.assertz(clause)
        clauses = db.clauses_for("emit_mk", 3)

        # The generated source actually took the fast path.
        func_def = compile_predicate_trampoline_ast("emit_mk", 3, clauses, db)
        assert "_clausal_new" in ast.unparse(func_def)

        fn = compile_predicate_trampoline("emit_mk", 3, clauses, db)
        a, b, r = 1, 2, Var()
        trail = Trail()
        sg = StepGenerator(fn, None, None, None, a, b, r, trail)
        results = solutions(sg, lambda: deref(r))

        assert results == [pt(x=1, y=2)]
        # Parity with a term built entirely via the slow path.
        assert results[0] == pt(1, 2)


# ── Task 1: the walk/copy rebuilders adopt the fast path ────────────────────
#
# ``_deref_walk_py`` (clausal/logic/solve.py) and ``_copy_term_py``
# (clausal/logic/builtins/inspection.py) both walk every field of a term
# instance to build the reconstructed/copied result — construction is always
# saturated at these sites. They adopt the same gate as the emitter: when
# ``type(term)``'s OWN dict has ``_clausal_new`` bound to a classmethod, call
# it positionally with the walked field values (in ``_fields`` order);
# otherwise keep today's ``cls(**kwargs)`` slow path byte-identical.


class TestDerefWalkFastPath:
    def test_fast_new_used_for_nested_predicate_meta_term(self):
        # nv — instrument ``_clausal_new`` with a call-recording wrapper and
        # confirm both that it fires AND that the result matches the
        # pre-change (``cls(**walked)``) semantics: a fresh, fully-deref'd
        # object equal to the manually-reconstructed one.
        from clausal.logic.solve import _deref_walk_py
        from clausal.logic.variables import Var, Trail, unify

        inner = make_predicate("dw_inner", ["a", "b"])
        outer = make_predicate("dw_outer", ["p", "q"])

        calls = []
        real_fast_new = inner.__dict__["_clausal_new"]

        def recording(cls, *args):
            calls.append(args)
            return real_fast_new.__func__(cls, *args)

        inner._clausal_new = classmethod(recording)
        try:
            v = Var()
            trail = Trail()
            unify(v, 99, trail)
            term = outer(p=inner(a=1, b=v), q="tail")

            result = _deref_walk_py(term)

            assert calls, "expected _clausal_new to be invoked for the inner term"
            expected = outer(
                p=inner(a=1, b=99),
                q="tail",
            )
            assert result == expected
            assert result is not term
            assert result.p is not term.p
            assert result.p.b == 99
        finally:
            del inner._clausal_new
            inner._clausal_new = real_fast_new

    def test_dataclass_node_slow_path_unchanged(self):
        # nv — a pythonic_ast dataclass node has no ``_clausal_new`` in its
        # own ``vars()``, so it must keep going through the kwargs slow path.
        from clausal.logic.solve import _deref_walk_py

        node = BinOp(left=1, right=2)
        result = _deref_walk_py(node)
        assert result == node
        assert result is not node
        assert "_clausal_new" not in vars(type(node))

    def test_field_named_clausal_new_walks_via_slow_path(self):
        # nv — a class whose FIELD is literally named ``_clausal_new`` has a
        # member descriptor (not a classmethod) at that key in its own
        # ``vars()``; the gate must reject it and fall back to kwargs.
        from clausal.logic.solve import _deref_walk_py

        weird = make_predicate("dw_weird", ["_clausal_new"])
        term = weird(_clausal_new=7)
        result = _deref_walk_py(term)
        assert result == term
        assert result._clausal_new == 7

    def test_field_order_non_alphabetical(self):
        # nv — ``make_predicate`` field order need not be alphabetical;
        # ``term_field_names`` must drive positional assignment correctly.
        from clausal.logic.solve import _deref_walk_py

        p = make_predicate("dw_p", ["b", "a"])
        assert p._fields == ("b", "a")
        term = p(b=1, a=2)
        result = _deref_walk_py(term)
        assert result.b == 1
        assert result.a == 2


class TestCopyTermFastPath:
    def test_fast_new_used_for_nested_predicate_meta_term(self):
        # nv — same instrumentation approach as the deref-walk test, applied
        # to ``_copy_term_py``: fresh Vars substituted per ``var_map``,
        # structure preserved, and the fast constructor actually fires.
        from clausal.logic.builtins.inspection import _copy_term_py
        from clausal.logic.variables import Var, is_var

        inner = make_predicate("ct_inner", ["a", "b"])
        outer = make_predicate("ct_outer", ["p", "q"])

        calls = []
        real_fast_new = inner.__dict__["_clausal_new"]

        def recording(cls, *args):
            calls.append(args)
            return real_fast_new.__func__(cls, *args)

        inner._clausal_new = classmethod(recording)
        try:
            v = Var()
            term = outer(p=inner(a=1, b=v), q="tail")

            var_map = {}
            result = _copy_term_py(term, var_map)

            assert calls, "expected _clausal_new to be invoked for the inner term"
            assert result is not term
            assert result.p is not term.p
            assert result.p.a == 1
            assert is_var(result.p.b)
            assert result.p.b is not v
            assert var_map[id(v)] is result.p.b
            assert result.q == "tail"
        finally:
            del inner._clausal_new
            inner._clausal_new = real_fast_new

    def test_dataclass_node_slow_path_unchanged(self):
        # nv
        from clausal.logic.builtins.inspection import _copy_term_py

        node = BinOp(left=1, right=2)
        result = _copy_term_py(node, {})
        assert result == node
        assert result is not node
        assert "_clausal_new" not in vars(type(node))

    def test_field_named_clausal_new_copies_via_slow_path(self):
        # nv
        from clausal.logic.builtins.inspection import _copy_term_py

        weird = make_predicate("ct_weird", ["_clausal_new"])
        term = weird(_clausal_new=7)
        result = _copy_term_py(term, {})
        assert result == term
        assert result._clausal_new == 7

    def test_field_order_non_alphabetical(self):
        # nv
        from clausal.logic.builtins.inspection import _copy_term_py

        p = make_predicate("ct_p", ["b", "a"])
        assert p._fields == ("b", "a")
        term = p(b=1, a=2)
        result = _copy_term_py(term, {})
        assert result.b == 1
        assert result.a == 2
