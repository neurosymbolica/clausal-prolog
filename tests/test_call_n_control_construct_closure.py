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
-private([z, w, once, caught(x), nope(x), a, b, c, t])
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
h(1, a),
h(2, b),
h(1, c),
fa4_2(L) <- call(findall(X, g(X)), L, [t])
fa4_1(L) <- call(findall(X), g(X), L, [t])
bag_1(K, L) <- call(bagof(V), h(K, V), L)
bag_2(L) <- call(bagof(V, h(1, V)), L)
set_1(K, L) <- call(setof(V), h(K, V), L)
set_2(L) <- call(setof(V, h(1, V)), L)
scc_1(X) <- call(setup_call_cleanup(True), g(X), True)
scc_2(X) <- call(setup_call_cleanup(True, g(X)), True)
cc_1(X) <- call(call_cleanup(g(X)), True)
fr_1(Y) <- (call(freeze(X), Y is a), X is 1)
fr_1_waits(Y) <- call(freeze(_X), Y is a)
wh_1(Y) <- (call(when(nonvar(X)), Y is a), X is 1)
cn_1(X) <- call(call_nth(g(X)), 2)
cnt_1(N) <- call(count_all(g(_)), N)
ce_1(E) <- call(catch_error(throw(z)), E)
cr_1(R) <- call(catch_recover(throw(z)), E, R is caught(E))
cr_2(R) <- call(catch_recover(throw(z), E), R is caught(E))
cr_nomatch() <- call(catch_recover(throw(z), w), True)
ev_1(R) <- call(eval_(1 + 2), R)
built_eval(G) <- (G is eval_(1 + 2))
"""

_PREDS = ("catch_1/1, catch_2/1, catch_nomatch/0, findall_1/1, forall_1/1, "
          "once_0/1, built/1, catch_too_few/0, findall_too_few/0, no_such/0, "
          "fa4_2/1, fa4_1/1, bag_1/2, bag_2/1, set_1/2, set_2/1, scc_1/1, "
          "scc_2/1, cc_1/1, fr_1/1, fr_1_waits/1, wh_1/1, cn_1/1, cnt_1/1, "
          "ce_1/1, cr_1/1, cr_2/1, cr_nomatch/0, ev_1/1, built_eval/1")

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
h(1, a).
h(2, b).
h(1, c).
fa4_2(L) :- call(findall(X, g(X)), L, [t]).
fa4_1(L) :- call(findall(X), g(X), L, [t]).
bag_1(K, L) :- call(bagof(V), h(K, V), L).
bag_2(L) :- call(bagof(V, h(1, V)), L).
set_1(K, L) :- call(setof(V), h(K, V), L).
set_2(L) :- call(setof(V, h(1, V)), L).
scc_1(X) :- call(setup_call_cleanup(true), g(X), true).
scc_2(X) :- call(setup_call_cleanup(true, g(X)), true).
cc_1(X) :- call(call_cleanup(g(X)), true).
fr_1(Y) :- call(freeze(X), Y = a), X = 1.
fr_1_waits(Y) :- call(freeze(_X), Y = a).
wh_1(Y) :- call(when(nonvar(X)), Y = a), X = 1.
cn_1(X) :- call(call_nth(g(X)), 2).
cnt_1(N) :- call(count_all(g(_)), N).
ce_1(E) :- call(catch_error(throw(z)), E).
cr_1(R) :- call(catch_recover(throw(z)), E, R = caught(E)).
cr_2(R) :- call(catch_recover(throw(z), E), R = caught(E)).
cr_nomatch :- call(catch_recover(throw(z), w), true).
ev_1(R) :- call(eval_(1 + 2), R).
built_eval(G) :- G = eval_(1 + 2).
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


# ── every other special form, under-applied ──────────────────────────────────
#
# Review of 18c0eaed (2026-10-13): ``is_special_form_closure`` covers every
# special-form name below its widest arity -- catch/1-2, findall/1-3,
# bagof/1-2, setof/1-2, forall/1, catch_error/1, catch_recover/1-2,
# call_nth/1, count_all/1, setup_call_cleanup/1-2, call_cleanup/1, freeze/1,
# when/1, eval_/1 -- and each closure below was RED in the seam on a33877ec
# (existence_error at the written arity).  Scryer (``library(iso_ext)``,
# ``library(freeze)``, ``library(when)``) and Trealla (``library(freeze)``,
# ``library(when)``) give the same answers wherever they have the predicate:
#
#     call(findall(X, g(X)), L, [t])                 L = [1, 2, t]
#     call(findall(X), g(X), L, [t])                 L = [1, 2, t]
#     call(bagof(V), h(K, V), L)                     K = 1, L = [a, c] ; K = 2, L = [b]
#     call(bagof(V, h(1, V)), L)                     L = [a, c]
#     call(setof(V), h(K, V), L)                     K = 1, L = [a, c] ; K = 2, L = [b]
#     call(setof(V, h(1, V)), L)                     L = [a, c]
#     call(setup_call_cleanup(true), g(X), true)     X = 1 ; X = 2
#     call(setup_call_cleanup(true, g(X)), true)     X = 1 ; X = 2
#     call(call_cleanup(g(X)), true)                 X = 1 ; X = 2
#     call(freeze(X), Y = a), X = 1                  Y = a
#     call(freeze(_), Y = a)                         Y unbound
#     call(when(nonvar(X)), Y = a), X = 1            Y = a
#     call(call_nth(g(X)), 2)                        X = 2
#
# count_all/2, catch_error/2, catch_recover/3 and eval_/2 are Clausal's own
# (no Scryer/Trealla predicate); their answers follow the same forms written
# at full arity (docs/builtins.md).


def test_call_findall_closures_extend_to_findall_4(mod):
    assert _answers(mod, "fa4_2", Var()) == [([1, 2, "t"],)]
    assert _answers(mod, "fa4_1", Var()) == [([1, 2, "t"],)]


def test_call_bagof_closures(mod):
    assert _answers(mod, "bag_1", Var(), Var()) == [
        (1, ["a", "c"]), (2, ["b"])]
    assert _answers(mod, "bag_2", Var()) == [(["a", "c"],)]


def test_call_setof_closures(mod):
    assert _answers(mod, "set_1", Var(), Var()) == [
        (1, ["a", "c"]), (2, ["b"])]
    assert _answers(mod, "set_2", Var()) == [(["a", "c"],)]


def test_call_setup_call_cleanup_closures(mod):
    assert _answers(mod, "scc_1", Var()) == [(1,), (2,)]
    assert _answers(mod, "scc_2", Var()) == [(1,), (2,)]


def test_call_call_cleanup_closure(mod):
    assert _answers(mod, "cc_1", Var()) == [(1,), (2,)]


def test_call_freeze_closure(mod):
    assert _answers(mod, "fr_1", Var()) == [("a",)]
    from clausal.logic.variables import is_var
    ((y,),) = _answers(mod, "fr_1_waits", Var())
    assert is_var(y), y


def test_call_when_closure(mod):
    assert _answers(mod, "wh_1", Var()) == [("a",)]


def test_call_call_nth_closure(mod):
    assert _answers(mod, "cn_1", Var()) == [(2,)]


def test_call_count_all_closure(mod):
    assert _answers(mod, "cnt_1", Var()) == [(2,)]


def test_call_catch_error_closure(mod):
    assert _answers(mod, "ce_1", Var()) == [("z",)]


def test_call_catch_recover_closures(mod):
    assert _answers(mod, "cr_1", Var()) == [(("caught", "z"),)]
    assert _answers(mod, "cr_2", Var()) == [(("caught", "z"),)]
    # catch_recover never re-raises: a catcher that does not unify FAILS.
    assert _answers(mod, "cr_nomatch") == []


def test_call_eval_closure(mod):
    """``call(eval_(1 + 2), R)`` is ``eval_(1 + 2, R)``: R = 3."""
    assert _answers(mod, "ev_1", Var()) == [(3,)]


def test_an_under_applied_eval_in_term_position_is_a_cell(mod):
    """The visible side of the fix: ``G is eval_(1 + 2)`` (seam) used to
    raise ``existence_error(procedure, eval_/1)``; it now binds the CELL
    ``eval_(1 + 2)`` -- the closure -- as ``.clausal``'s ``G = eval_(1 + 2)``
    always did.  Nothing evaluates it: eval_/1 is no goal and no evaluable."""
    ((g,),) = _answers(mod, "built_eval", Var())
    assert type(g) is tuple and cell_functor(g) == "eval_", g
    assert len(cell_args(g)) == 1, g
