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
from clausal.logic.predicate import (
    PredicateMeta, _resolve_mangled_owner, is_declared_predicate_name,
    is_zero_field_class,
)
from clausal.logic.solve import _deref_walk, _templatize_query_goal, solve
from clausal.logic.variables import Var, is_var


def _fixture_path(name: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", name)


@pytest.fixture(scope="module")
def owner():
    # Loaded under ``hide_owner`` -- the module half every mangled spelling
    # below carries, so ``is_declared_predicate_name`` can resolve it.
    return _load_module("hide_owner", _fixture_path("hide_owner.clausal"))


@pytest.fixture(scope="module")
def zero():
    return _load_module("self_atom_zero", _fixture_path("self_atom_zero.clausal"))


PREDICATES = ("holds", "label", "same")


def _eval(expr: ast.expr):
    tree = ast.fix_missing_locations(ast.Expression(expr))
    return eval(compile(tree, "<t>", "eval"), {})


def _shapes(owner, zero=None):
    """(plain name, class binding, mangled binding) for every exported
    predicate -- the population compared.  Positive control: non-empty and
    each shape is what it claims to be."""
    population = [(owner, "hide_owner", n) for n in PREDICATES]
    if zero is not None:
        population.append((zero, "self_atom_zero", "z"))
    rows = []
    for mod, modname, name in population:
        cls = getattr(mod, name)
        mangled = mangle(modname, name)
        assert isinstance(cls, PredicateMeta), (name, cls)
        assert is_mangled(mangled) and is_declared_predicate_name(mangled), name
        rows.append((name, cls, mangled))
    assert len(rows) == len(population) > 0
    if zero is not None:
        assert sum(1 for _n, c, _m in rows if is_zero_field_class(c)) == 1
    return rows


def _hidden():
    secret = mangle("hide_owner", "hide_secret")
    assert is_mangled(secret)
    assert not is_declared_predicate_name(secret)
    return secret


# ── term_to_ast_expr ──────────────────────────────────────────────────────

def test_class_and_mangled_bindings_bake_the_same_plain_literal(owner, zero):
    for name, cls, mangled in _shapes(owner, zero):
        from_class = term_to_ast_expr(cls, {})
        from_mangled = term_to_ast_expr(mangled, {})
        assert isinstance(from_class, ast.Constant), name
        assert isinstance(from_mangled, ast.Constant), name
        assert from_class.value == name
        assert from_mangled.value == name, (
            f"mangled predicate binding baked {from_mangled.value!r}, "
            f"not its plain name {name!r}")


def test_nested_predicate_binding_bakes_plain(owner, zero):
    for name, cls, mangled in _shapes(owner, zero):
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

def test_ground_value_parameterizes_the_plain_name(owner, zero):
    """Both eras, every arity: the parameter is the plain atom (a str), never
    the class object and never the mangled spelling."""
    for name, cls, mangled in _shapes(owner, zero):
        for binding in (cls, mangled):
            _goal, params = _templatize_query_goal(("same", binding, Var()))
            assert [v for _p, v in params] == [name], (name, binding, params)
            assert type(params[0][1]) is str


def test_ground_value_keeps_hide_atom_mangled(owner):
    secret = _hidden()
    _goal, params = _templatize_query_goal(("holds", secret))
    assert [v for _p, v in params] == [secret]


# ── end to end through solve ──────────────────────────────────────────────

def test_solve_unifies_a_mangled_predicate_binding_as_its_plain_atom(owner, zero):
    for name, cls, mangled in _shapes(owner, zero):
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


def test_zero_arity_source_fact_matches_both_binding_shapes(zero):
    """``q(z)`` in source stores the plain atom ``z``; a query written with
    the binding -- the class today, the mangled handle post-flip -- must
    find it.  Before the ruling the class arm bound the CLASS object and
    answered 0 here."""
    X = Var()
    assert [_deref_walk(X) for _ in solve(("q", X), zero)] == ["z"]
    for binding in (zero.z, mangle("self_atom_zero", "z")):
        assert sum(1 for _ in solve(("q", binding), zero)) == 1, binding


# ── a mangled str whose owner module does not resolve: kept VERBATIM ──────

def test_unresolvable_mangled_str_is_baked_verbatim_not_refused(owner):
    """Deliberately NOT refused: an unresolvable mangled str is
    indistinguishable from a -hide DATA atom whose module was loaded under a
    different sys.modules key (see the comment at term_to_ast_expr)."""
    orphan = mangle("no_such_module_2026_09_24", "secret")
    assert is_mangled(orphan) and _resolve_mangled_owner(orphan) is None
    assert term_to_ast_expr(orphan, {}).value == orphan
    _goal, params = _templatize_query_goal(("holds", orphan))
    assert [v for _p, v in params] == [orphan]


_ALT_KEY_SCRIPT = r"""
import sys
import clausal.import_hook
from clausal.import_hook import _load_module
from clausal.logic.predicate import _resolve_mangled_owner
from clausal.logic.solve import solve, _deref_walk
from clausal.logic.variables import Var
m = _load_module("hide_owner_under_another_key", sys.argv[1])
X = Var()
got = [_deref_walk(X) for _ in solve(("holds", X), m)]
assert got == ["hide_owner\x1fhide_secret"], got
assert _resolve_mangled_owner(got[0]) is None
n = sum(1 for _ in solve(("holds", got[0]), m))
assert n == 1, n
print("OK")
"""


def test_a_legitimate_unresolvable_hide_atom_round_trips():
    """Why an unresolvable mangled str is NOT refused: a -hide atom minted by
    a module loaded under a sys.modules key other than its -module name
    resolves to no owner, yet is a real value that must round-trip into a
    query.  Fresh interpreter, so no other test's ``hide_owner`` load makes
    the owner resolvable."""
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(
        [sys.executable, "-c", _ALT_KEY_SCRIPT, _fixture_path("hide_owner.clausal")],
        cwd=root, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and out.stdout.strip() == "OK", out.stderr[-2000:]
