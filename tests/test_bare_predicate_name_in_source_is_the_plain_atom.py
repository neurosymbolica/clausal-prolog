"""Ruling S in CLAUSE SOURCE: a bare arity>=1 predicate name in data
position stores the PLAIN atom of its name, in both eras -- and every
goal-taking builtin handed that atom resolves it by name in the CALLER's
module, the way ``call/N`` does.

``todo/done/bare-predicate-name-in-clause-source-is-the-binding-not-the-atom-2026-09-24.md``.
Before: ``r(b)`` stored ``b/1``'s CLASS (a ``LoadName`` lowered to a runtime
``Name`` load), so a plain ``r(b)`` query answered 0.  Just lowering it to the
atom broke 25 tests, because the goal-first list builtins could only run a
goal OBJECT and failed silently on an atom.
"""
from __future__ import annotations

import ast

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.compiler.terms_to_ast import lowering_scope, term_to_ast_expr
from clausal.logic.predicate import PredicateMeta, mint_predicate_handle
from clausal.logic.solve import call, solve
from clausal.logic.variables import Var, deref
from clausal.terms import LoadName

_SRC = """\
-module({name}, [z/0, b/1, add/3, q/1, r/1, l/1, g_map/0, g_call/0,
                 g_fold/1, g_part/2, g_phrase/0, greet/2])
z <- True,
b(1),
add(X, Y, Z) <- (Z == X + Y),
q(z),
r(b),
l([b, 2]),
g_map <- maplist(b, [1, 1]),
g_call <- call(b, 1),
g_fold(S) <- foldl(add, [1, 2, 3], 0, S),
g_part(I, E) <- partition(b, [1, 2, 1], I, E),
greet >> (["h", "i"])
g_phrase <- phrase(greet, ["h", "i"]),
"""


@pytest.fixture
def mod(tmp_path, request):
    name = f"bpn_{request.node.name.replace('[', '_').replace(']', '')}"
    p = tmp_path / f"{name}.clausal"
    p.write_text(_SRC.format(name=name))
    return _load_module(name, str(p))


def _answers(lm, functor, n=1):
    xs = [Var() for _ in range(n)]
    out = []
    for _ in call(functor, *xs, module=lm):
        v = [deref(x) for x in xs]
        out.append(v[0] if n == 1 else tuple(v))
    return out


def test_the_stored_value_is_the_plain_atom(mod):
    lm = mod.__dict__["$module"]
    assert _answers(lm, "q") == ["z"]
    assert _answers(lm, "r") == ["b"]
    assert type(_answers(lm, "r")[0]) is str
    assert _answers(lm, "l") == [["b", 2]]
    assert len(list(call("r", "b", module=lm))) == 1, "a plain query answers"


def test_goal_taking_builtins_resolve_the_atom_in_the_caller(mod):
    lm = mod.__dict__["$module"]
    assert len(list(call("g_map", module=lm))) == 1
    assert len(list(call("g_call", module=lm))) == 1
    assert _answers(lm, "g_fold") == [6]
    assert _answers(lm, "g_part", 2) == [([1, 1], [2])]
    assert len(list(call("g_phrase", module=lm))) == 1


@pytest.mark.parametrize("flipped", [False, True], ids=["class", "flipped"])
def test_a_query_passing_the_binding_or_the_atom_answers(mod, flipped):
    """The query side (``_ground_value``) already lowered a class/handle to
    the atom; maplist answered 0 for it until the atom resolved by name."""
    lm = mod.__dict__["$module"]
    md = mod.__dict__
    assert isinstance(md["b"], PredicateMeta)
    binding = mint_predicate_handle(lm.db, "b") if flipped else md["b"]
    if flipped:
        md["b"] = binding
    for goal in (binding, "b"):
        assert len(list(solve(("maplist", goal, [1]), lm))) == 1, goal
        assert len(list(solve(("maplist", goal, [2]), lm))) == 0, goal


@pytest.mark.parametrize("flipped", [False, True], ids=["class", "flipped"])
def test_the_lowering_bakes_the_plain_atom_in_both_eras(mod, flipped):
    md = dict(mod.__dict__)
    if flipped:
        md["b"] = mint_predicate_handle(md["$module"].db, "b")
    with lowering_scope(md):
        expr = term_to_ast_expr(LoadName(name="b"), {})
    assert isinstance(expr, ast.Constant) and expr.value == "b"


def test_a_hide_data_atom_keeps_its_load(tmp_path):
    """A ``-hide`` DATA atom is mangled but no predicate: not lowered here
    (its runtime load IS its mangled spelling)."""
    md = {"hidden": mangle("somemod", "hidden")}
    with lowering_scope(md):
        expr = term_to_ast_expr(LoadName(name="hidden"), {})
    assert isinstance(expr, ast.Name)


def test_a_wrong_arity_atom_goal_still_names_the_arity(mod):
    """``maplist(b, L, L2)`` against b/1: the refusal a body call gets."""
    from clausal.predicate_diagnostics import PredicateArityMismatchError
    lm = mod.__dict__["$module"]
    with pytest.raises(PredicateArityMismatchError):
        list(solve(("maplist", "b", [1], Var()), lm))



def test_listing_a_bare_name_names_the_zero_arity_predicate(mod):
    """Source ``listing(b)`` now passes the ATOM, which names ``b/0``
    (spec 6.4, pinned by ``test_row_30_listing_takes_an_atom_and_refuses_a_
    string``) -- no longer b/1's class.  ``listing(b/1)`` is the spelling."""
    from clausal.logic.exceptions import LogicException
    lm = mod.__dict__["$module"]
    with pytest.raises(LogicException) as exc:
        list(solve(("listing", "b"), lm))
    assert exc.value.term.args[0].functor == "existence_error"
    assert len(list(solve(("listing", ("/", "b", 1)), lm))) == 1
