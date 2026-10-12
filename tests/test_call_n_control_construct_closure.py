"""``call/N`` of a control-construct CLOSURE: ``call(catch(G), C, R)`` is catch/3.

ISO 13211-1 §8.15.4: call/N appends its extra arguments to the closure, so
``call(catch(G), C, R)``, ``call(catch(G, C), R)``, ``call(findall(X), G, L)``
and ``call(forall(G), A)`` are catch/3, catch/3, findall/3 and forall/2.  Both
Scryer and Trealla run them (answers pinned below).

The runtime half already worked: ``higher_order`` folds the extra arguments
into the cell and hands a special form to ``call_body.special_form_dispatch``.
What failed (found by the catch/3 review, 2026-10-13) was BUILDING the closure
in a seam clause.  A special form has no term class -- no builtin carries the
name -- so ``terms_to_ast._goal_cell_functor`` builds its cell by name, but it
asked ``is_special_form`` at the WRITTEN arity: ``catch(G)`` is not catch/3,
so the construction fell through to the undeclared-functor path and raised
``existence_error(procedure, catch/1)`` before call/3 ever ran, under both
compile strategies.  A special-form name written BELOW one of its arities is
now a closure cell too.

The Clausal Prolog (``.clausal``) surface auto-declares every functor a file
uses, so it never had the bug; its twin here is a control, as are
``call(once, G)`` (a bare atom closure) and the existence errors that must
stay.

Answers, Scryer 0.9 (``library(iso_ext)`` for forall/2) and Trealla, verified
2026-10-13:

    call(catch(throw(z)), E, R = caught(E))        R = caught(z)
    call(catch(throw(z), E), R = caught(E))        R = caught(z)
    call(catch(throw(z), w), true)                 throws z
    call(findall(X), g(X), L)                      L = [1, 2]
    call(forall(g(X)), X > 0)                      true
    call(forall(g(X)), X > 1)                      false
    call(once, g(X))                               X = 1
    call(catch(throw(z)), _)                       existence_error(procedure, catch/2)
    call(findall(X), g(X))                         existence_error(procedure, findall/2)
    call(nope(1), 2)                               existence_error(procedure, nope/2)
"""
from __future__ import annotations

import sys
import textwrap
import warnings

import pytest

from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from tests._suffix import SEAM

_SEAM = """
-module(NAME, [])
-private([z, w, once, caught(x), nope(x)])
SHALLOW
g(1),
g(2),
catch_1(R) <- call(catch(throw(z)), E, R is caught(E))
catch_2(R) <- call(catch(throw(z), E), R is caught(E))
catch_nomatch() <- call(catch(throw(z), w), True)
findall_1(L) <- call(findall(X), g(X), L)
forall_1(N) <- call(forall(g(X)), X > N)
once_0(X) <- call(once, g(X))
built(G) <- (G is catch(throw(z)))
catch_too_few() <- call(catch(throw(z)), _)
findall_too_few() <- call(findall(X), g(X))
no_such() <- call(nope(1), 2)
"""

_PREDS = ("catch_1/1, catch_2/1, catch_nomatch/0, findall_1/1, forall_1/1, "
          "once_0/1, built/1, catch_too_few/0, findall_too_few/0, no_such/0")

_CLAUSAL = r"""
:- module(NAME, []).
g(1).
g(2).
catch_1(R) :- call(catch(throw(z)), E, R = caught(E)).
catch_2(R) :- call(catch(throw(z), E), R = caught(E)).
catch_nomatch :- call(catch(throw(z), w), true).
findall_1(L) :- call(findall(X), g(X), L).
forall_1(N) :- call(forall(g(X)), X > N).
once_0(X) :- call(once, g(X)).
built(G) :- G = catch(throw(z)).
catch_too_few :- call(catch(throw(z)), _).
findall_too_few :- call(findall(X), g(X)).
no_such :- call(nope(1), 2).
:- end_module(NAME).
"""


def _load(tmp_path, monkeypatch, name, suffix, text):
    from clausal.import_hook import _load_module
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / f"{name}{suffix}"
    path.write_text(textwrap.dedent(text).lstrip())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _load_module(name, str(path))


# seam_trampoline / seam_shallow carry the bug; clausal is the control.
@pytest.fixture(params=["seam_trampoline", "seam_shallow", "clausal"])
def mod(request, tmp_path, monkeypatch):
    surface = request.param
    name = f"cncc_{surface}"
    if surface == "clausal":
        m = _load(tmp_path, monkeypatch, name, ".clausal",
                  _CLAUSAL.replace("NAME", name))
    else:
        shallow = (f"-shallow([{_PREDS}])" if surface == "seam_shallow"
                   else "")
        m = _load(tmp_path, monkeypatch, name, SEAM,
                  _SEAM.replace("NAME", name).replace("SHALLOW", shallow))
    try:
        db = m.__dict__["$module"]
        if surface == "seam_shallow":
            for p in _PREDS.split(", "):
                f, a = p.split("/")
                assert db.db.is_shallow(f, int(a)), p
        yield db
    finally:
        sys.modules.pop(name, None)


def _answers(m, name, *args):
    goal = (name, *args) if args else name
    return [tuple(_deref_walk(a) for a in args) for _ in solve(goal, m)]


def _error(m, name):
    with pytest.raises(LogicException) as info:
        _answers(m, name)
    return _deref_walk(info.value.term)


def _existence_pi(term):
    assert cell_functor(term) == "error", term
    formal = cell_args(term)[0]
    assert cell_functor(formal) == "existence_error", term
    kind, pi = cell_args(formal)
    assert kind == "procedure", term
    return pi


# ── the closures ─────────────────────────────────────────────────────────────


def test_call_catch_1_closure_with_catcher_and_recovery(mod):
    """``call(catch(G), C, R)`` is ``catch(G, C, R)`` -- the todo's repro."""
    assert _answers(mod, "catch_1", Var()) == [(("caught", "z"),)]


def test_call_catch_2_closure_with_recovery(mod):
    assert _answers(mod, "catch_2", Var()) == [(("caught", "z"),)]


def test_call_catch_closure_whose_catcher_does_not_unify_rethrows(mod):
    with pytest.raises(LogicException) as info:
        _answers(mod, "catch_nomatch")
    assert _deref_walk(info.value.term) == "z"


def test_call_findall_1_closure(mod):
    assert _answers(mod, "findall_1", Var()) == [([1, 2],)]


def test_call_forall_1_closure(mod):
    assert _answers(mod, "forall_1", 0) == [(0,)]
    assert _answers(mod, "forall_1", 1) == []


def test_call_once_atom_closure(mod):
    """Control: an atom closure always worked."""
    assert _answers(mod, "once_0", Var()) == [(1,)]


def test_a_partial_special_form_builds_its_cell(mod):
    """The construction itself, outside call/N: ``catch(throw(z))`` is the
    cell ``catch(throw(z))`` -- what ``.clausal`` and Scryer build."""
    assert _answers(mod, "built", Var()) == [(("catch", ("throw", "z")),)]


# ── existence errors that must stay ──────────────────────────────────────────


def test_a_closure_extended_to_no_control_construct_is_existence_error(mod):
    """``call(catch(G), _)`` is catch/2 and ``call(findall(X), G)`` findall/2:
    neither is a control construct, so the closure CELL is built and call/N
    reports the extended indicator, as Scryer and Trealla do."""
    assert _existence_pi(_error(mod, "catch_too_few")) == ("/", "catch", 2)
    assert _existence_pi(_error(mod, "findall_too_few")) == (
        "/", "findall", 2)


def test_an_undefined_closure_is_still_existence_error(mod):
    """Control: a real undefined closure keeps its error at the CALLED arity."""
    assert _existence_pi(_error(mod, "no_such")) == ("/", "nope", 2)
