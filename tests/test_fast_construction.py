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
