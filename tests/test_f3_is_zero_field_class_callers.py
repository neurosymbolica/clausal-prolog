"""F3 (row 9): verification, not migration, of `is_zero_field_class`'s
callers outside the F1/F2/F2b/F5 grep population.

Design authority: ``implementation_plans/w4b2-f2b-and-hard-families-2026-09-23.md``
section F3.

Four callers of ``is_zero_field_class``/``_is_zero_field_class_py`` sit
outside the 49-row migration population:

  - ``logic/database.py`` ``head_key`` -- the brief already verified this
    one (an immediately-following ``if type(head) is str: return head, 0``
    branch already covers the post-flip shape); not re-tested here.
  - ``logic/solve.py:487`` (``_ground_value``, nested in
    ``_templatize_query_goal``)
  - ``builtins/_helpers.py:207`` (``_is_ground_py``)
  - ``compiler/terms_to_ast.py:1099`` (``term_to_ast_expr``'s
    ``is_zero_field_class`` branch)

These three were marked INFERENCE in the design brief ("this is INFERENCE,
not verified by running the flip"). This suite turns that inference into a
directly-observed fact by calling each function with a mangled-atom
``str`` standing in for the post-flip shape of a bare zero-arity predicate
reference, in place of today's ``PredicateMeta`` class -- exactly the
substitution the brief describes.

Verdict for each (see the todo this suite backs,
``todo/self-denoting-predicate-atom-spelling-post-flip-mangled-or-plain-2026-09-24.md``):

  - ``_ground_value``/``_templatize_query_goal``: CONFIRMED harmless -- the
    resolved value passes through verbatim in both eras (a class object
    today, a mangled atom string post-flip); no code change.
  - ``_is_ground_py``: CONFIRMED harmless -- both eras answer ``True``; no
    code change.
  - ``term_to_ast_expr``: the brief's narrow claim ("no exception, falls
    through to the pre-existing str branch") is CONFIRMED. A DIFFERENT,
    more precise fact not stated in the brief: the two eras' emitted
    ``ast.Constant`` literal do not carry the *same spelling* (today mints
    the class's plain ``__name__``; post-flip the generic str branch bakes
    the full mangled string verbatim, undemangled). Whether that is a bug
    depends on an undecided design question (parked in the todo above),
    not on anything present in today's code -- so no code change is made
    here either, but the DIVERGENCE itself is pinned by this test so a
    future change to either branch is caught.
"""
from __future__ import annotations

import ast

from clausal.logic.atoms import mangle
from clausal.logic.builtins._helpers import _is_ground_py
from clausal.logic.compiler.terms_to_ast import term_to_ast_expr
from clausal.logic.predicate import is_zero_field_class, make_predicate
from clausal.logic.solve import _templatize_query_goal


def _mangled_self_atom() -> str:
    """Stand-in for the post-flip shape: a bare zero-arity predicate
    reference resolves to a mangled atom naming its owning module, per
    the W4b-2d spec's own description ("mint handles with the import
    name")."""
    return mangle("f3_probe_mod", "f3_probe_pred")


# ── is_zero_field_class itself: never true for a str, in either era ────────

def test_is_zero_field_class_false_for_mangled_atom():
    assert is_zero_field_class(_mangled_self_atom()) is False


def test_is_zero_field_class_true_for_the_class_it_replaces():
    P0 = make_predicate("F3ProbeZeroArityA", [])
    assert is_zero_field_class(P0) is True


# ── _ground_value (via _templatize_query_goal): verbatim pass-through ──────

class TestGroundValuePassesThroughVerbatimInBothEras:
    def test_class_field_is_parameterized_with_the_class_itself(self):
        P0 = make_predicate("F3ProbeZeroArityB", [])
        Goal = make_predicate("F3ProbeGoalB", ["a"])
        _, params = _templatize_query_goal(Goal(a=P0))
        assert len(params) == 1
        _var, value = params[0]
        assert value is P0

    def test_mangled_atom_field_is_parameterized_with_the_string_itself(self):
        mangled = _mangled_self_atom()
        Goal = make_predicate("F3ProbeGoalC", ["a"])
        _, params = _templatize_query_goal(Goal(a=mangled))
        assert len(params) == 1
        _var, value = params[0]
        assert value == mangled
        assert isinstance(value, str)


# ── _is_ground_py: identical boolean in both eras ───────────────────────────

class TestIsGroundIdenticalInBothEras:
    def test_class_is_ground(self):
        P0 = make_predicate("F3ProbeZeroArityD", [])
        assert _is_ground_py(P0) is True

    def test_mangled_atom_is_ground(self):
        assert _is_ground_py(_mangled_self_atom()) is True


# ── term_to_ast_expr: no exception either era, but spelling DIVERGES ───────

class TestTermToAstExprNoCrashButSpellingDiverges:
    def test_class_mints_the_plain_name(self):
        P0 = make_predicate("F3ProbeZeroArityE", [])
        expr = term_to_ast_expr(P0, {})
        assert isinstance(expr, ast.Constant)
        assert expr.value == "F3ProbeZeroArityE"

    def test_mangled_atom_bakes_the_mangled_spelling_verbatim(self):
        """No exception (the brief's claim, confirmed) -- but the baked
        literal is the FULL mangled string, not the plain functor name a
        demangle() call would recover. Pinned so a future edit to either
        branch surfaces here rather than silently changing which spelling
        gets baked."""
        mangled = _mangled_self_atom()
        expr = term_to_ast_expr(mangled, {})
        assert isinstance(expr, ast.Constant)
        assert expr.value == mangled
        assert expr.value != "f3_probe_pred"  # the plain functor half
