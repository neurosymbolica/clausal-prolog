"""A predicate's SELF-DENOTING atom stays PLAIN.

Operator ruling 2026-09-24 (todo/done/self-denoting-predicate-atom-spelling-
post-flip-mangled-or-plain-2026-09-24.md): a bare reference to a predicate in
DATA position denotes the atom of its plain name, "because the default in
Prolog is global, but be cognizant of directive hide/1".

Since the W4b-2d flip a predicate's module binding is the mangled handle
``module\\x1fname`` (a ``str``; it used to be a ``PredicateMeta`` class, and
the class arm of these tests went with it).  It must lower to the PLAIN
literal.  A ``-hide`` DATA atom is ALSO a mangled ``str``,
but it is not a predicate's self-atom: its mangled spelling is its identity
and must be kept -- so the discriminator is ``is_declared_predicate_name``,
never ``is_mangled``.

Sites: ``term_to_ast_expr`` (the baked literal) and ``_templatize_query_goal``'s
``_ground_value`` (the parameterized top-level query argument, which would
otherwise pass the mangled spelling through and bypass the first site).  Both
pass the ruling-Q0 ``db=`` hint (the lowering scope's ``$module`` db; the
querying module's db), so a LOCAL handle resolves even after its module is
popped from ``sys.modules`` -- which is also why every helper here resolves
through the owner's db rather than trusting ``sys.modules``.
"""
from __future__ import annotations

import ast
import os
import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal import cell_args
from clausal.import_hook import _load_module
from clausal.logic.atoms import is_mangled, mangle
from clausal.logic.compiler.terms_to_ast import lowering_scope, term_to_ast_expr
from clausal.logic.predicate import (
    _resolve_mangled_owner, is_declared_predicate_name,
    mint_predicate_handle, predicate_binding_name,
)
from clausal.logic.solve import _deref_walk, _templatize_query_goal, solve
from clausal.logic.variables import Var, is_var


def _fixture_path(name: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", name)


def _db(mod):
    return mod.__dict__["$module"].db


@pytest.fixture(scope="module")
def owner():
    return _load_module("hide_owner", _fixture_path("hide_owner.clausal"))


@pytest.fixture(scope="module")
def zero():
    return _load_module("self_atom_zero", _fixture_path("self_atom_zero.clausal"))


PREDICATES = ("holds", "label", "same")


def _eval(expr: ast.expr):
    tree = ast.fix_missing_locations(ast.Expression(expr))
    return eval(compile(tree, "<t>", "eval"), {})


def _lower(term, mod):
    """``term_to_ast_expr`` inside *mod*'s lowering scope -- as every
    compile does -- so the Q0 hint reaches the resolver."""
    with lowering_scope(mod.__dict__):
        return term_to_ast_expr(term, {})


def _is_zero_arity_predicate(mod, name):
    """*name* is a predicate of *mod*'s Database at arity 0 only."""
    return _db(mod).predicate_arities(name) == {0}


def _shapes(owner, zero=None):
    """(module, plain name, handle) for every exported predicate -- the
    population compared.  The module-dict binding must BE the handle (so a
    class era coming back fails here rather than being lowered as one).  The handle is minted from the
    owner's DATABASE (ruling X3) and checked through the Q0 ``db=`` hint, so
    another test popping ``hide_owner`` from ``sys.modules`` cannot turn this
    population empty.  Positive control: non-empty, each shape is what it
    claims, exactly one zero-arity predicate when *zero* is given."""
    population = [(owner, n) for n in PREDICATES]
    if zero is not None:
        population.append((zero, "z"))
    rows = []
    for mod, name in population:
        binding = getattr(mod, name)
        handle = mint_predicate_handle(_db(mod), name)
        assert binding == handle, (name, binding)
        assert is_mangled(handle), name
        assert is_declared_predicate_name(handle, db=_db(mod)), name
        rows.append((mod, name, handle))
    assert len(rows) == len(population) > 0
    if zero is not None:
        assert sum(1 for m, n, _h in rows if _is_zero_arity_predicate(m, n)) == 1
    return rows


def _hidden(owner):
    secret = mangle(_db(owner).module_name(), "hide_secret")
    assert is_mangled(secret)
    assert not is_declared_predicate_name(secret, db=_db(owner))
    return secret


# ── term_to_ast_expr ──────────────────────────────────────────────────────

def test_a_mangled_binding_bakes_its_plain_literal(owner, zero):
    for mod, name, handle in _shapes(owner, zero):
        from_handle = _lower(handle, mod)
        assert isinstance(from_handle, ast.Constant), name
        assert from_handle.value == name, (
            f"predicate handle baked {from_handle.value!r}, "
            f"not its plain name {name!r}")


def test_nested_predicate_binding_bakes_plain(owner, zero):
    for mod, name, handle in _shapes(owner, zero):
        assert _eval(_lower(("f", handle, 1), mod)) == ("f", name, 1)


def test_hide_data_atom_keeps_its_mangled_spelling(owner):
    secret = _hidden(owner)
    expr = _lower(secret, owner)
    assert isinstance(expr, ast.Constant)
    assert expr.value == secret
    assert _eval(_lower(("f", secret), owner)) == ("f", secret)


def test_plain_string_is_untouched(owner):
    # A plain spelling that happens to name a predicate is not a binding.
    assert _lower("holds", owner).value == "holds"


# ── _templatize_query_goal / _ground_value ────────────────────────────────

def test_ground_value_parameterizes_the_plain_name(owner, zero):
    """Every arity: the parameter is the plain atom (a str), never the
    mangled spelling."""
    for mod, name, handle in _shapes(owner, zero):
        for binding in (handle,):
            _goal, params = _templatize_query_goal(("same", binding, Var()), _db(mod))
            assert [v for _p, v in params] == [name], (name, binding, params)
            assert type(params[0][1]) is str


def test_ground_value_keeps_hide_atom_mangled(owner):
    secret = _hidden(owner)
    _goal, params = _templatize_query_goal(("holds", secret), _db(owner))
    assert [v for _p, v in params] == [secret]


# ── end to end through solve ──────────────────────────────────────────────

def test_solve_unifies_a_mangled_predicate_binding_as_its_plain_atom(owner, zero):
    for mod, name, handle in _shapes(owner, zero):
        for binding in (handle,):
            for wrap in (lambda b: b, lambda b: ("f", b)):
                X = Var()
                got = [_deref_walk(X) for _ in solve(("=", X, wrap(binding)), mod)]
                assert got == [wrap(name)], (name, binding, got)


def test_solve_hide_atom_still_matches_its_owner_facts(owner):
    secret = _hidden(owner)
    assert sum(1 for _ in solve(("holds", secret), owner)) == 1
    X = Var()
    got = [_deref_walk(X) for _ in solve(("holds", X), owner)]
    assert got == [secret] and not is_var(got[0])


def test_zero_arity_source_fact_matches_both_binding_shapes(zero):
    """``q(z)`` in source stores the plain atom ``z``; a query written with
    the binding -- the handle post-flip -- must find it.  (Before the
    ruling the class-era binding was the CLASS object and answered 0.)"""
    X = Var()
    assert [_deref_walk(X) for _ in solve(("q", X), zero)] == ["z"]
    assert zero.z == mint_predicate_handle(_db(zero), "z")
    for binding in (zero.z,):
        assert sum(1 for _ in solve(("q", binding), zero)) == 1, binding


# ── Q0: a local handle in a module POPPED from sys.modules ────────────────

def test_popped_module_local_handle_lowers_plain_only_with_the_db_hint(tmp_path):
    name = "self_atom_popped_2026_09_24"
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent("""
        sa_p(1),
    """).lstrip())
    sys.modules.pop(name, None)
    mod = _load_module(name, str(path))
    sys.modules.pop(name, None)            # as the .clausal runner does
    # Isolate the HINT from the handle-owner registry (ruling Q0's
    # cross-module remainder, test_handle_owner_registry.py): it would
    # otherwise answer for the popped module and make the control vacuous.
    from clausal.logic.predicate import _HANDLE_OWNERS
    _HANDLE_OWNERS.pop(name, None)
    db = _db(mod)
    handle = mint_predicate_handle(db, "sa_p")
    # Positive control: without the hint the popped owner is unreachable, so
    # everything below would bake/bind the mangled spelling.
    assert predicate_binding_name(handle) is None
    assert predicate_binding_name(handle, db=db) == "sa_p"
    assert term_to_ast_expr(handle, {}).value == handle          # no scope
    assert _lower(handle, mod).value == "sa_p"                   # scope -> db
    assert _templatize_query_goal(("g", handle))[1][0][1] == handle
    assert _templatize_query_goal(("g", handle), db)[1][0][1] == "sa_p"
    for wrap in (lambda b: b, lambda b: ("f", b)):
        X = Var()
        got = [_deref_walk(X) for _ in solve(("=", X, wrap(handle)), mod)]
        assert got == [wrap("sa_p")], got


# ── a mangled str whose owner module does not resolve: kept VERBATIM ──────

def test_unresolvable_mangled_str_is_baked_verbatim_not_refused(owner):
    """Deliberately NOT refused: an unresolvable mangled str is
    indistinguishable from a -hide DATA atom whose module was loaded under a
    different sys.modules key (see the comment at term_to_ast_expr)."""
    orphan = mangle("no_such_module_2026_09_24", "secret")
    assert is_mangled(orphan) and _resolve_mangled_owner(orphan) is None
    assert _resolve_mangled_owner(orphan, db=_db(owner)) is None
    assert _lower(orphan, owner).value == orphan
    _goal, params = _templatize_query_goal(("holds", orphan), _db(owner))
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
    env = dict(os.environ)
    # Import THIS tree's clausal, not whatever the ambient path finds first.
    env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    script = f"import sys; sys.path.insert(0, {root!r})\n" + _ALT_KEY_SCRIPT + (
        f"\nimport clausal, os\n"
        f"assert os.path.realpath(clausal.__file__).startswith(os.path.realpath({root!r}) + os.sep), clausal.__file__\n")
    out = subprocess.run(
        [sys.executable, "-c", script, _fixture_path("hide_owner.clausal")],
        cwd=root, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and out.stdout.strip() == "OK", (
        f"rc={out.returncode}\nstdout:\n{out.stdout[-2000:]}\nstderr:\n{out.stderr[-2000:]}")


# ── ruling S, extended 2026-09-24: goal-argument use must qualify ─────────

def test_goal_argument_must_be_qualified_to_reach_another_module():
    """A predicate binding passed as a GOAL argument lowers to its PLAIN
    atom, which ``call/1`` resolves in the CALLING module; only the
    qualified form reaches the other module's predicate.  Modules are loaded
    here (not in a shared fixture) so a peer popping them cannot interfere."""
    other = _load_module("sa_goal_other", _fixture_path("sa_goal_other.clausal"))
    caller = _load_module("sa_goal_caller", _fixture_path("sa_goal_caller.clausal"))
    local = _load_module("sa_goal_caller_local",
                         _fixture_path("sa_goal_caller_local.clausal"))
    handle = mint_predicate_handle(_db(other), "z")
    assert other.z == handle
    bindings = (handle,)
    assert _is_zero_arity_predicate(other, "z")
    assert predicate_binding_name(handle, db=_db(other)) == "z"

    def answers(goal, mod):
        return sum(1 for _ in solve(goal, mod))

    # Positive control: the other module's z IS reachable, qualified.
    assert answers(("run", (":", "sa_goal_other", "z")), caller) == 1
    # The caller defines no z: the plain atom -- and so either binding --
    # finds nothing there.  FLIPPED 2026-09-25 -- operator ruling 2 ("like
    # Scryer"): an unknown procedure in a meta-call RAISES
    # existence_error(procedure, z/0); these used to answer 0.
    from clausal.logic.exceptions import LogicException
    for g in ("z", *bindings):
        with pytest.raises(LogicException) as exc:
            answers(("run", g), caller)
        assert cell_args(cell_args(cell_args(exc.value.term)[0])[1]) == ("z", 0), g
    # A caller WITH its own z (two solutions): the binding resolves to THAT
    # one, never to sa_goal_other's (one solution).
    assert answers(("run", "z"), local) == 2
    for b in bindings:
        assert answers(("run", b), local) == 2, b
    assert answers(("run", (":", "sa_goal_other", "z")), local) == 1


def test_plain_string_lowering_skips_the_db_lookup(owner, monkeypatch):
    """Hot path: only a MANGLED str can be a predicate handle, so lowering a
    plain string must not consult the lowering scope's db at all."""
    import clausal.logic.compiler.terms_to_ast as t2a
    calls = []
    real = t2a._lowering_db
    monkeypatch.setattr(t2a, "_lowering_db", lambda: calls.append(1) or real())
    assert _lower("holds", owner).value == "holds"
    assert _lower("some plain text", owner).value == "some plain text"
    assert calls == []
    # Positive control: a mangled str DOES consult it.
    assert _lower(mint_predicate_handle(_db(owner), "holds"), owner).value == "holds"
    assert calls == [1]
