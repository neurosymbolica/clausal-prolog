"""A predicate's SELF-DENOTING atom stays PLAIN in both eras.

Operator ruling 2026-09-24 (todo/done/self-denoting-predicate-atom-spelling-
post-flip-mangled-or-plain-2026-09-24.md): a bare reference to a predicate in
DATA position denotes the atom of its plain name, "because the default in
Prolog is global, but be cognizant of directive hide/1".

Today a predicate's module binding is a ``PredicateMeta`` class; after the
flip it is the mangled handle ``module\\x1fname`` (a ``str``).  Both must lower
to the same PLAIN literal.  A ``-hide`` DATA atom is ALSO a mangled ``str``,
but it is not a predicate's self-atom: its mangled spelling is its identity
and must be kept -- so the discriminator is ``is_declared_predicate_name``,
never ``is_mangled``.

Sites: ``term_to_ast_expr`` (the baked literal) and ``_templatize_query_goal``'s
``_ground_value`` (the parameterized top-level query argument, which would
otherwise pass the mangled spelling through and bypass the first site).
"""
from __future__ import annotations

import ast
import os

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import is_mangled, mangle
from clausal.logic.compiler.terms_to_ast import term_to_ast_expr
from clausal.logic.predicate import PredicateMeta, is_declared_predicate_name
from clausal.logic.solve import _deref_walk, _templatize_query_goal, solve
from clausal.logic.variables import Var, is_var


def _fixture_path(name: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", name)


@pytest.fixture(scope="module")
def owner():
    # Loaded under ``hide_owner`` -- the module half every mangled spelling
    # below carries, so ``is_declared_predicate_name`` can resolve it.
    return _load_module("hide_owner", _fixture_path("hide_owner.clausal"))


PREDICATES = ("holds", "label", "same")


def _eval(expr: ast.expr):
    tree = ast.fix_missing_locations(ast.Expression(expr))
    return eval(compile(tree, "<t>", "eval"), {})


def _shapes(owner):
    """(plain name, class binding, mangled binding) for every exported
    predicate -- the population compared.  Positive control: non-empty and
    each shape is what it claims to be."""
    rows = []
    for name in PREDICATES:
        cls = getattr(owner, name)
        mangled = mangle("hide_owner", name)
        assert isinstance(cls, PredicateMeta), (name, cls)
        assert is_mangled(mangled) and is_declared_predicate_name(mangled), name
        rows.append((name, cls, mangled))
    assert len(rows) == len(PREDICATES) > 0
    return rows


def _hidden():
    secret = mangle("hide_owner", "hide_secret")
    assert is_mangled(secret)
    assert not is_declared_predicate_name(secret)
    return secret


# ── term_to_ast_expr ──────────────────────────────────────────────────────

def test_class_and_mangled_bindings_bake_the_same_plain_literal(owner):
    for name, cls, mangled in _shapes(owner):
        from_class = term_to_ast_expr(cls, {})
        from_mangled = term_to_ast_expr(mangled, {})
        assert isinstance(from_class, ast.Constant), name
        assert isinstance(from_mangled, ast.Constant), name
        assert from_class.value == name
        assert from_mangled.value == name, (
            f"mangled predicate binding baked {from_mangled.value!r}, "
            f"not its plain name {name!r}")


def test_nested_predicate_binding_bakes_plain(owner):
    for name, cls, mangled in _shapes(owner):
        assert _eval(term_to_ast_expr(("f", cls, 1), {})) == ("f", name, 1)
        assert _eval(term_to_ast_expr(("f", mangled, 1), {})) == ("f", name, 1)


def test_hide_data_atom_keeps_its_mangled_spelling(owner):
    secret = _hidden()
    expr = term_to_ast_expr(secret, {})
    assert isinstance(expr, ast.Constant)
    assert expr.value == secret
    assert _eval(term_to_ast_expr(("f", secret), {})) == ("f", secret)


def test_plain_string_is_untouched(owner):
    # A plain spelling that happens to name a predicate is not a binding.
    assert term_to_ast_expr("holds", {}).value == "holds"


# ── _templatize_query_goal / _ground_value ────────────────────────────────

def test_ground_value_parameterizes_the_plain_name(owner):
    for name, _cls, mangled in _shapes(owner):
        _goal, params = _templatize_query_goal(("same", mangled, Var()))
        assert [v for _p, v in params] == [name]


def test_ground_value_keeps_hide_atom_mangled(owner):
    secret = _hidden()
    _goal, params = _templatize_query_goal(("holds", secret))
    assert [v for _p, v in params] == [secret]


# ── end to end through solve ──────────────────────────────────────────────

def test_solve_unifies_a_mangled_predicate_binding_as_its_plain_atom(owner):
    for name, cls, mangled in _shapes(owner):
        for binding in (cls, mangled):
            for wrap in (lambda b: b, lambda b: ("f", b)):
                X = Var()
                got = [_deref_walk(X) for _ in solve(("=", X, wrap(binding)), owner)]
                assert got == [wrap(name)], (name, binding, got)


def test_solve_hide_atom_still_matches_its_owner_facts(owner):
    secret = _hidden()
    assert sum(1 for _ in solve(("holds", secret), owner)) == 1
    X = Var()
    got = [_deref_walk(X) for _ in solve(("holds", X), owner)]
    assert got == [secret] and not is_var(got[0])
