"""when/2 conditions written in Prolog syntax: ``(C1 ; C2)`` and ``(C1 , C2)``
arrive as functor-first cells, not as the seam ``Or``/``And`` nodes.  The
runtime dispatcher must read them, nest them to any depth, fire a ``;`` once,
and refuse a bad condition the way Scryer does (instantiation_error for a
variable, domain_error(when_condition, C) for anything else, checked over the
WHOLE condition before anything is installed)."""
from __future__ import annotations

import itertools

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var

_N = itertools.count()

PL = """\
:- module({name}, [d1/1, d2/1, c1/1, hook/1, hook2/1, nest/1, nest2/1, once_only/1, ground_or/1,
                   bad_dom/1, bad_var/1, bad_inner/1,
                   viacall/1, inhook/1, backtrack/1, fired_twice/1]).

d1(R) :- when((nonvar(X) ; nonvar(Z)), R = fired), Z = go, X = go.
d2(R) :- when((nonvar(X) ; ground(Y)), R = fired), Y = f(1).
c1(R) :- when((nonvar(X), ground(f(Y))), R = fired), X = 1, R \== fired, Y = 2.
hook(R) :- freeze(X, when((nonvar(Y) ; nonvar(Z)), R = fired)), Y = 1, Z = 2, X = go.
hook2(R) :- freeze(X, when((nonvar(Y) ; nonvar(Z)), R = fired)), X = go, Z = 2, Y = 1.
nest(R) :- when(((nonvar(A), nonvar(B)) ; ground(C)), R = fired), A = 1, C = 2.
nest2(R) :- when(((nonvar(A) ; nonvar(B)), (ground(C) ; ground(D))), R = fired),
            A = 1, D = 2.
once_only(L) :- when((nonvar(A) ; nonvar(B)), put_in(L, x)), A = 1, B = 2.
put_in(L, X) :- nb_ins(L, X).
nb_ins(L, X) :- L = [X|_].
ground_or(R) :- when((ground(f(A)) ; nonvar(B)), R = fired), A = 1.
bad_dom(E) :- catch(when(foo(_), true), error(E, _), true).
bad_var(E) :- catch(when(_, true), error(E, _), true).
bad_inner(E) :- catch(when((nonvar(_) ; foo), true), error(E, _), true).
viacall(R) :- G = when((nonvar(X) ; nonvar(Z)), R = fired), call(G), Z = 1, X = 1.
inhook(R) :- when((nonvar(X) ; nonvar(Y)), (R = fired)), X = 1.
backtrack(R) :- when((nonvar(X) ; nonvar(Y)), R = fired), ( X = 1, fail ; Y = 2 ).
fired_twice(N) :- findall(x, (when((nonvar(X) ; nonvar(Y)), true), X = 1, Y = 2), L), length(L, N).
"""


def _all(mod, name):
    v = Var()
    return [_deref_walk(v) for _ in solve((name, v), mod)]


@pytest.fixture(params=["translator", "native"])
def plmod(request, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", request.param)
    name = f"when_pl_{request.param}_{next(_N)}"
    p = tmp_path / f"{name}.pl"
    p.write_text(PL.format(name=name))
    return _load_module(name, str(p))


def test_disjunction_either_side(plmod):
    assert _all(plmod, "d1") == ["fired"]
    assert _all(plmod, "d2") == ["fired"]


def test_nested(plmod):
    assert _all(plmod, "nest") == ["fired"]
    assert _all(plmod, "nest2") == ["fired"]


def test_ground_in_disjunction(plmod):
    assert _all(plmod, "ground_or") == ["fired"]


def test_fires_once(plmod):
    assert _all(plmod, "fired_twice") == [1]


def test_errors(plmod):
    (dom,) = _all(plmod, "bad_dom")
    assert dom[0] == "domain_error" and dom[1] == "when_condition"
    assert _all(plmod, "bad_var") == ["instantiation_error"]
    (inner,) = _all(plmod, "bad_inner")
    assert inner[0] == "domain_error" and inner[1] == "when_condition"


def test_through_call(plmod):
    assert _all(plmod, "viacall") == ["fired"]


def test_backtrack(plmod):
    assert _all(plmod, "backtrack") == ["fired"]


def test_conjunction_waits_for_both(plmod):
    assert _all(plmod, "c1") == ["fired"]


def test_inside_a_wake_up_hook(plmod):
    assert _all(plmod, "hook") == ["fired"]
    assert _all(plmod, "hook2") == ["fired"]


# ── ?=/2 and the seam surface ───────────────────────────────────────────────

from clausal.logic.exceptions import LogicException  # noqa: E402
from clausal.terms import And, Or, Call, LoadName, Unify  # noqa: E402

Q = """\
:- module({name}, [unif/1, unif2/1, unif3/1, unif4/1, unif_or/1, unif_once/1]).
unif(R) :- when('?='(X, Y), R = fired), X = 1, Y = 2.
unif2(R) :- when('?='(X, Y), R = fired), X = Y.
unif3(R) :- when('?='(f(X, a), f(Y, b)), R = fired).
unif4(R) :- when('?='(X, Y), R = fired), X = 1, R \\== fired, Y = 1.
unif_or(R) :- when(('?='(X, Y) ; nonvar(Z)), R = fired), Z = 1, X = 1, Y = 2.
unif_once(N) :- findall(x, (when(('?='(X, Y) ; nonvar(X)), true), X = 1, Y = 2), L),
                length(L, N).
"""


def test_query_unify_native(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    name = f"when_q_{next(_N)}"
    p = tmp_path / f"{name}.pl"
    p.write_text(Q.format(name=name))
    mod = _load_module(name, str(p))
    assert _all(mod, "unif") == ["fired"]
    assert _all(mod, "unif2") == ["fired"]
    assert _all(mod, "unif3") == ["fired"]   # decided already: never unifiable
    assert _all(mod, "unif4") == ["fired"]
    assert _all(mod, "unif_or") == ["fired"]
    assert _all(mod, "unif_once") == [1]


def _when(cond, goal):
    return Call(func=LoadName(name="when"), args=[cond, goal], kwargs=[])


def _nonvar(x):
    return Call(func=LoadName(name="nonvar"), args=[x], kwargs=[])


def _ground(x):
    return Call(func=LoadName(name="ground"), args=[x], kwargs=[])


def _run(goal, out):
    return [_deref_walk(out) for _ in solve(goal, _fresh())]


def _fresh():
    from clausal.logic.database import Module
    return Module(f"when_seam_{next(_N)}")


def test_seam_or_and_and_nodes():
    for cond_of in (
        lambda x, y: Or(left=_nonvar(x), right=_ground(y)),
        lambda x, y: Or(left=Or(left=_ground(y), right=_ground(y)), right=_nonvar(x)),
        lambda x, y: Or(left=And(left=_nonvar(x), right=_nonvar(x)), right=_ground(y)),
    ):
        x, y, r = Var(), Var(), Var()
        goal = And(left=_when(cond_of(x, y), Unify(left=r, right="fired")),
                   right=Unify(left=x, right=1))
        assert _run(goal, r) == ["fired"]


def test_seam_bad_conditions_are_scryer_errors():
    r = Var()
    with pytest.raises(LogicException) as e:
        _run(_when(Var(), Unify(left=r, right=1)), r)
    assert "instantiation_error" in repr(e.value.term)
    with pytest.raises(LogicException) as e:
        _run(_when(Or(left=_nonvar(Var()), right="foo"), Unify(left=r, right=1)), r)
    assert "when_condition" in repr(e.value.term)
