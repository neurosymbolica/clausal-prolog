"""Tests for the `_clausal_new` generated fast constructor (Phase 0, Task 1).

P2 (2026-09-20): a class applied to arguments builds the functor-first CELL, so
a term needs no constructor at all and the fast path is unreachable for one —
the compiler emits a cell literal instead.  It survives for the classes still
flagged ``instances=True`` (the reflection vocabulary, clpb, term-expansion
state), which is why every class here is built that way: the subject is
unchanged, the population is now named.  ``_clausal_new`` retires with the
class in P4, and this file with it.

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
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.terms import Compound, Unify as Is
from clausal.pythonic_ast.nodes import BinOp


class TestFastConstructorBasics:
    def test_fast_new_matches_slow_path(self):
        # nv
        foo = make_predicate("foo", ["x", "y"], instances=True)
        fast = foo._clausal_new(1, 2)
        slow = foo(1, 2)
        assert type(fast) is foo
        assert fast.x == 1
        assert fast.y == 2
        assert fast == slow
        assert fast is not slow

    def test_fast_new_single_field(self):
        # nv
        bar = make_predicate("bar", ["a"], instances=True)
        fast = bar._clausal_new(42)
        assert fast.a == 42
        assert fast == bar(42)


class TestAtomsGetNoFastConstructor:
    def test_atom_class_has_no_clausal_new(self):
        # nv
        red = make_predicate("red", [], instances=True)
        assert "_clausal_new" not in vars(red)


class TestFieldNamedClausalNew:
    def test_field_named_clausal_new_uses_slow_path_only(self):
        # nv
        weird = make_predicate("weird", ["_clausal_new"], instances=True)
        # class creation must not raise, and the slow path still works
        t = weird(_clausal_new=5)
        assert t._clausal_new == 5

    def test_field_named_clausal_new_gets_no_fast_constructor(self):
        # nv
        weird = make_predicate("weird2", ["_clausal_new"], instances=True)
        # "_clausal_new" is a field name here, so __slots__ owns the class
        # attribute (a member descriptor) at that name. The fast-new factory
        # must not clobber it with a classmethod.
        assert "_clausal_new" in weird.__slots__
        assert not isinstance(vars(weird)["_clausal_new"], classmethod)


class TestCacheShareByFieldTuple:
    def test_two_same_named_classes_each_get_working_fast_new(self):
        # nv
        foo1 = make_predicate("foo", ["x"], instances=True)
        foo2 = make_predicate("foo", ["x"], instances=True)
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
        baz = make_predicate("baz", ["x"], instances=True)
        fast = baz._clausal_new(1)
        assert baz.__hash__ is None
        with pytest.raises(TypeError):
            hash(fast)

    def test_fast_path_equal_to_slow_path(self):
        # nv
        qux = make_predicate("qux", ["x", "y"], instances=True)
        fast = qux._clausal_new(1, 2)
        slow = qux(x=1, y=2)
        assert fast == slow
        assert slow == fast

    def test_fast_path_match_args_pattern_matching(self):
        # nv
        quux = make_predicate("quux", ["x", "y"], instances=True)
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
        foo = make_predicate("emit_foo", ["x", "y"], instances=True)
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
        assert expr.func.id == "$BinOp"
        assert expr.keywords != []

    def test_position_field_class_keeps_keyword_emission(self):
        # nv — a PredicateMeta class with a field literally named "position"
        # hits the pre-existing skip-filter and must NOT take the fast path,
        # even though it has a working _clausal_new.
        posy = make_predicate("emit_posy", ["position"], instances=True)
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
        posy2 = make_predicate("emit_posy2", ["_position"], instances=True)
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
        weird = make_predicate("weird_pred", ["_clausal_new"], instances=True)
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
        pt = make_predicate("emit_pt", ["x", "y"], instances=True)
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

        inner = make_predicate("dw_inner", ["a", "b"], instances=True)
        outer = make_predicate("dw_outer", ["p", "q"], instances=True)

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

        weird = make_predicate("dw_weird", ["_clausal_new"], instances=True)
        term = weird(_clausal_new=7)
        result = _deref_walk_py(term)
        assert result == term
        assert result._clausal_new == 7

    def test_field_order_non_alphabetical(self):
        # nv — ``make_predicate`` field order need not be alphabetical;
        # ``term_field_names`` must drive positional assignment correctly.
        from clausal.logic.solve import _deref_walk_py

        p = make_predicate("dw_p", ["b", "a"], instances=True)
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

        inner = make_predicate("ct_inner", ["a", "b"], instances=True)
        outer = make_predicate("ct_outer", ["p", "q"], instances=True)

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

        weird = make_predicate("ct_weird", ["_clausal_new"], instances=True)
        term = weird(_clausal_new=7)
        result = _copy_term_py(term, {})
        assert result == term
        assert result._clausal_new == 7

    def test_field_order_non_alphabetical(self):
        # nv
        from clausal.logic.builtins.inspection import _copy_term_py

        p = make_predicate("ct_p", ["b", "a"], instances=True)
        assert p._fields == ("b", "a")
        term = p(b=1, a=2)
        result = _copy_term_py(term, {})
        assert result.b == 1
        assert result.a == 2


# ── Task 2: the C walker twins adopt the same gate ──────────────────────────
#
# ``do_walk``'s term-instance arm (clausal/logic/variables/_variables.c) and
# ``do_deref_walk``'s term-instance arm (clausal/logic/_tabling_core.c) must
# make the SAME fast/slow decision as ``_deref_walk_py`` on the same terms —
# "KEEP THE THREE WALKERS IN SYNC" (solve.py's ``_deref_walk_py`` comment):
# ``_deref_walk_py``, ``_deref_walk`` (the C twin exposed by
# ``clausal.logic._tabling_core``), and ``walk()`` (``clausal.logic.variables``)
# must all agree.
#
# ``clausal.logic._tabling_core`` is an OPTIONAL accelerator — solve.py:100-104
# wraps its import in ``try/except ImportError`` and falls back to
# ``_deref_walk_py`` when it is absent. A module-scope ``importorskip`` on it
# would therefore skip this ENTIRE test module — including the pure-Python
# gate tests above (TestFastConstructorBasics, TestDerefWalkFastPath,
# TestCopyTermFastPath) — on exactly the build configuration where those
# tests matter most. So only the C-specific test classes below are
# skip-guarded (via ``pytest.mark.skipif`` on ``_HAVE_TABLING_CORE``); every
# class above this section always runs.
#
# ``clausal.logic.variables._variables`` is NOT optional the same way: the
# package's own ``__init__.py`` imports it unconditionally (and this file's
# own ``from clausal.logic.variables import ...`` at the top would already
# have failed if it were missing) — so no skip guard is needed for it.

try:
    from clausal.logic import _tabling_core

    _HAVE_TABLING_CORE = True
except ImportError:
    _tabling_core = None
    _HAVE_TABLING_CORE = False

from clausal.logic.variables import _variables as _variables_c

_needs_tabling_core = pytest.mark.skipif(
    not _HAVE_TABLING_CORE,
    reason="C extension not built — the C-walker parity corpus needs the C twins",
)


def _c_walker_corpus():
    """One corpus, shared by every C-walker parity test in this section.

    Shapes: a nested PredicateMeta term with both a bound and an unbound Var
    (the everyday tabling/findall snapshot shape), a dataclass node (must take
    the slow path in all three walkers), a class with a field literally named
    ``_clausal_new`` (member descriptor, not a classmethod — slow path), and a
    term with a ``position``-named field (fast-path eligible at the class
    level, but exercises the "position" name that the *emitter*'s separate
    skip-filter cares about — the walkers have no such filter, so this must
    still take the fast path here).
    """
    inner = make_predicate("cw_inner", ["a", "b"], instances=True)
    outer = make_predicate("cw_outer", ["p", "q"], instances=True)
    v_bound = Var()
    v_unbound = Var()
    trail = Trail()
    unify(v_bound, 42, trail)
    nested = outer(p=inner(a=1, b=v_bound), q=[v_unbound, "x"])

    node = BinOp(left=1, right=2)

    weird = make_predicate("cw_weird", ["_clausal_new"], instances=True)
    weird_term = weird(_clausal_new=7)

    posy = make_predicate("cw_posy", ["position"], instances=True)
    posy_term = posy(position=v_bound)

    return [nested, node, weird_term, posy_term]


@_needs_tabling_core
class TestCWalkerFastPathParity:
    def test_deref_walk_py_matches_deref_walk_c(self):
        # nv
        from clausal.logic.solve import _deref_walk_py

        for term in _c_walker_corpus():
            assert _deref_walk_py(term) == _tabling_core._deref_walk(term)

    def test_walk_matches_deref_walk_py(self):
        # nv — walk() has no separate Python twin of its own; solve.py's
        # comment names it as one of the three walkers _deref_walk_py must
        # stay in sync with, so it is the reference here too.
        from clausal.logic.solve import _deref_walk_py

        for term in _c_walker_corpus():
            assert _variables_c.walk(term) == _deref_walk_py(term)

    def test_deref_walk_c_produces_fresh_fully_derefed_object(self):
        # nv — parity of VALUES isn't enough on its own (a bug that always
        # took the slow path would still pass the ``==`` checks above); pin
        # down the identity/freshness properties the fast path must preserve.
        inner = make_predicate("cw_fresh_inner", ["a", "b"], instances=True)
        outer = make_predicate("cw_fresh_outer", ["p", "q"], instances=True)
        v = Var()
        trail = Trail()
        unify(v, 7, trail)
        term = outer(p=inner(a=1, b=v), q="tail")

        result = _tabling_core._deref_walk(term)
        assert result == outer(p=inner(a=1, b=7), q="tail")
        assert result is not term
        assert result.p is not term.p

    def test_walk_produces_fresh_fully_derefed_object(self):
        # nv
        inner = make_predicate("cw_fresh2_inner", ["a", "b"], instances=True)
        outer = make_predicate("cw_fresh2_outer", ["p", "q"], instances=True)
        v = Var()
        trail = Trail()
        unify(v, 7, trail)
        term = outer(p=inner(a=1, b=v), q="tail")

        result = _variables_c.walk(term)
        assert result == outer(p=inner(a=1, b=7), q="tail")
        assert result is not term
        assert result.p is not term.p

    def test_field_order_non_alphabetical(self):
        # nv — pins the C fast path's positional-tuple ordering directly
        # (rather than trusting alphabetical field order by accident),
        # mirroring TestDerefWalkFastPath.test_field_order_non_alphabetical
        # and TestCopyTermFastPath.test_field_order_non_alphabetical above.
        p = make_predicate("cw_nonalpha", ["b", "a"], instances=True)
        assert p._fields == ("b", "a")
        term = p(b=1, a=2)

        result = _tabling_core._deref_walk(term)
        assert result.b == 1
        assert result.a == 2

        result2 = _variables_c.walk(term)
        assert result2.b == 1
        assert result2.a == 2


@_needs_tabling_core
class TestCWalkerFastPathActuallyFires:
    """Confirm the C arms take the FAST branch (call ``_clausal_new``), not
    merely that results happen to match — instrument ``_clausal_new`` with a
    call-recording wrapper, the same technique
    TestDerefWalkFastPath/TestCopyTermFastPath use for the Python walkers."""

    def test_deref_walk_c_uses_fast_new_for_nested_term(self):
        # nv
        inner = make_predicate("cwf_inner", ["a", "b"], instances=True)
        outer = make_predicate("cwf_outer", ["p", "q"], instances=True)

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

            result = _tabling_core._deref_walk(term)

            assert calls, "expected _clausal_new to be invoked for the inner term"
            assert result == outer(p=inner(a=1, b=99), q="tail")
        finally:
            del inner._clausal_new
            inner._clausal_new = real_fast_new

    def test_walk_uses_fast_new_for_nested_term(self):
        # nv
        inner = make_predicate("cwf2_inner", ["a", "b"], instances=True)
        outer = make_predicate("cwf2_outer", ["p", "q"], instances=True)

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

            result = _variables_c.walk(term)

            assert calls, "expected _clausal_new to be invoked for the inner term"
            assert result == outer(p=inner(a=1, b=99), q="tail")
        finally:
            del inner._clausal_new
            inner._clausal_new = real_fast_new

    def test_deref_walk_c_field_named_clausal_new_uses_slow_path(self):
        # nv — regression guard for the name-only-check bug: a field
        # literally named "_clausal_new" must NOT be treated as the fast
        # constructor (it's a __slots__ member descriptor there, not a
        # classmethod — calling it would raise TypeError).
        weird = make_predicate("cwf_weird", ["_clausal_new"], instances=True)
        term = weird(_clausal_new=7)
        result = _tabling_core._deref_walk(term)
        assert result == term
        assert result._clausal_new == 7
        assert result is not term

    def test_walk_field_named_clausal_new_uses_slow_path(self):
        # nv
        weird = make_predicate("cwf2_weird", ["_clausal_new"], instances=True)
        term = weird(_clausal_new=7)
        result = _variables_c.walk(term)
        assert result == term
        assert result._clausal_new == 7
        assert result is not term


# ── Fix round 1 (controller ruling): c_copy_term adopts the same gate ───────
#
# clausal/logic/builtins/inspection.py:186 wires ``_copy_term =
# _copy_term_impl``, and that name is imported from
# ``clausal.logic.variables._variables`` when the C extension is present
# (see the ``try/except ImportError`` block above ``_copy_term_impl`` in that
# file) — so the C ``c_copy_term`` accelerator, not ``_copy_term_py``, is
# what actually runs at ``copy_term/2`` call sites. Its term-instance
# rebuild arm must decide fast-vs-slow identically to ``_copy_term_py``'s
# own gate (Task 1) or the two "walkers" silently diverge in practice.
#
# NOTE on value-equality checks below: ``copy_term`` mints a FRESH Var for
# every unbound Var it encounters, so two *independent* copies of a term
# holding an unbound Var are never ``==`` to each other by construction —
# that has nothing to do with the fast-path gate. The value-parity corpus
# here therefore uses a BOUND Var (copy_term dereferences it to its bound
# value before either implementation's fast/slow decision is even reached),
# and freshness/sharing on unbound Vars is checked structurally instead, the
# same way TestCopyTermFastPath does above.


def _c_copy_term_corpus():
    # nv
    inner = make_predicate("cct_p_inner", ["a", "b"], instances=True)
    outer = make_predicate("cct_p_outer", ["p", "q"], instances=True)
    v_bound = Var()
    trail = Trail()
    unify(v_bound, 42, trail)
    nested = outer(p=inner(a=1, b=v_bound), q="tail")

    node = BinOp(left=1, right=2)

    weird = make_predicate("cct_p_weird", ["_clausal_new"], instances=True)
    weird_term = weird(_clausal_new=7)

    posy = make_predicate("cct_p_posy", ["position"], instances=True)
    posy_term = posy(position=1)

    return [nested, node, weird_term, posy_term]


@_needs_tabling_core
class TestCCopyTermFastPathParity:
    def test_copy_term_c_matches_copy_term_py(self):
        # nv — ``_copy_term`` here is deliberately the runtime-wired name
        # from inspection.py (C-backed when the extension is present), not
        # ``_copy_term_impl`` directly, to exercise exactly what
        # ``copy_term/2`` calls.
        from clausal.logic.builtins.inspection import _copy_term, _copy_term_py

        for term in _c_copy_term_corpus():
            assert _copy_term_py(term, {}) == _copy_term(term, {})

    def test_copy_term_c_produces_fresh_object_with_fresh_unbound_vars(self):
        # nv — structural parity for the unbound-Var case: both
        # implementations must produce a fresh top-level object, a fresh
        # (distinct) Var standing in for each original unbound Var, and
        # preserve sharing (two references to the same original Var map to
        # the same fresh Var within one copy).
        from clausal.logic.builtins.inspection import _copy_term

        inner = make_predicate("cct_fresh_inner", ["a", "b"], instances=True)
        outer = make_predicate("cct_fresh_outer", ["p", "q"], instances=True)
        v = Var()
        term = outer(p=inner(a=1, b=v), q=[v, "tail"])

        var_map = {}
        result = _copy_term(term, var_map)

        assert result is not term
        assert result.p is not term.p
        assert result.p.a == 1
        from clausal.logic.variables import is_var

        assert is_var(result.p.b)
        assert result.p.b is not v
        # sharing preserved: the same original Var maps to the same fresh
        # Var both inside `p` and inside the `q` list.
        assert result.p.b is result.q[0]
        assert var_map[id(v)] is result.p.b

    def test_copy_term_c_field_named_clausal_new_uses_slow_path(self):
        # nv — regression guard for the name-only-check bug on the C
        # accelerator's own term-instance arm.
        from clausal.logic.builtins.inspection import _copy_term

        weird = make_predicate("cct_p_weird2", ["_clausal_new"], instances=True)
        term = weird(_clausal_new=7)
        result = _copy_term(term, {})
        assert result == term
        assert result._clausal_new == 7
        assert result is not term


@_needs_tabling_core
class TestCCopyTermFastPathActuallyFires:
    def test_copy_term_c_uses_fast_new_for_nested_term(self):
        # nv — same call-recording technique as
        # TestCWalkerFastPathActuallyFires, applied to the C copy_term
        # accelerator's term-instance arm.
        from clausal.logic.builtins.inspection import _copy_term

        inner = make_predicate("cct_fire_inner", ["a", "b"], instances=True)
        outer = make_predicate("cct_fire_outer", ["p", "q"], instances=True)

        calls = []
        real_fast_new = inner.__dict__["_clausal_new"]

        def recording(cls, *args):
            calls.append(args)
            return real_fast_new.__func__(cls, *args)

        inner._clausal_new = classmethod(recording)
        try:
            v = Var()
            term = outer(p=inner(a=1, b=v), q="tail")

            result = _copy_term(term, {})

            assert calls, "expected _clausal_new to be invoked for the inner term"
            assert result.p.a == 1
        finally:
            del inner._clausal_new
            inner._clausal_new = real_fast_new
