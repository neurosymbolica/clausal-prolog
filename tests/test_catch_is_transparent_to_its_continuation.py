"""catch/3 protects its Goal only: a ball from the goals after it escapes.

ISO 7.8.9: ``catch(G, C, R)`` behaves as ``call(G)`` while ``G`` runs; once
``G`` has succeeded, the catch is no longer active, and a ball thrown by the
continuation is not offered to ``C``.  When the continuation fails back into
``G`` the catch is active again while ``G`` looks for its next answer.  Scryer
and Trealla agree on every case below.

The compiled catch put the continuation inside the ``try`` that protects the
goal: a generator-based lowering runs the continuation while the ``try`` frame
is live.  The ball from ``chk(Y)`` below was caught::

    w5(Y) <- (catch(true, E, Y is E), chk(Y))      % gave Y = later

A goal woken by a binding the continuation makes runs in the continuation too
(``nc2``), while a goal woken inside the catch goal runs inside the catch
(``c_eq``, unchanged).

Every case runs under ``solve`` in both compilation strategies.
"""
from __future__ import annotations

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

_SEAM = """\
-private([later, oops, caught, inner, outer, b, c, second, two])
chk(Y) <- (var(Y), throw(later))
chk(Y) <- nonvar(Y)
chk2(1),
chk2(X) <- (X is 2, throw(second))
gen(1),
gen(_) <- throw(two)
ok(two),
p6(Y) <- catch(true, _, Y is caught)
p7(X) <- catch(freeze(X, throw(oops)), _, true)

w5(Y) <- (catch(true, E, Y is E), chk(Y))
w_inline(Y) <- (catch(true, E, Y is E), ((var(Y), throw(later)) or nonvar(Y)))
nc2(Y) <- (catch(freeze(X, throw(oops)), _, Y is caught), X == 3)
nc2_unify(Y) <- (catch(freeze(X, throw(oops)), _, Y is caught), X is 3)
c_eq(Y) <- catch((freeze(X, throw(oops)), X == 3), _, Y is caught)
w6(Y) <- (p6(Y), chk(Y))
nc3(Y) <- (p7(X), X == 3, Y is 1)
rk(Y) <- (catch(throw(b), b, true), chk(Y))

n_outer_takes(Y) <- catch((catch(true, _, Y is inner), throw(b)), E, Y is E)
n_inner_matches(Y) <- catch(catch(throw(b), b, Y is inner), _, Y is outer)
n_inner_declines(Y) <- catch(catch(throw(b), c, Y is inner), b, Y is outer)
n_after_both(Y) <- (catch(catch(true, _, Y is inner), _, Y is outer), chk(Y))
n_outer_declines(Y) <- catch((catch(true, b, Y is inner), ((var(Y), throw(b)) or nonvar(Y))), c, Y is outer)

in_findall(Y) <- catch(findall(Z, (catch(true, _, Z is inner), chk(Z)), _), later, Y is outer)
in_forall(Y) <- catch(forall((catch(true, _, Z is inner), chk(Z)), true), later, Y is outer)
in_once(Y) <- catch(once((catch(true, _, Z is inner), chk(Z))), later, Y is outer)
in_not(Y) <- catch(not (catch(true, _, Z is inner), chk(Z)), later, Y is outer)
in_findall_bare(L) <- findall(Z, (catch(true, _, Z is inner), chk(Z)), L)

multi(Y) <- (catch(member(Y, [1, 2]), _, Y is caught), chk2(Y))
reenter(Y) <- (catch(gen(Y), E, Y is E), not (Y is 1))
reenter_call(Y) <- (catch(gen(Y), E, Y is E), ok(Y))
reenter_inline(Y) <- (catch(gen(Y), E, Y is E), Y is two)
"""

_PREDS = ["chk", "chk2", "gen", "ok", "p6", "p7", "w5", "w_inline", "nc2",
          "nc2_unify", "c_eq", "w6", "nc3", "rk",
          "n_outer_takes", "n_inner_matches", "n_inner_declines",
          "n_after_both", "n_outer_declines",
          "in_findall", "in_forall", "in_once", "in_not", "in_findall_bare",
          "multi", "reenter", "reenter_call", "reenter_inline"]


@pytest.fixture(scope="module", params=["trampoline", "shallow"])
def mod(request, tmp_path_factory):
    src = _SEAM
    if request.param == "shallow":
        src = "-shallow([" + ", ".join(f"{p}/1" for p in _PREDS) + "])\n" + src
    p = tmp_path_factory.mktemp("catch_transparent_" + request.param) / "m.seam"
    p.write_text(src)
    return load_clausal_module(p)


def _answers(mod, goal):
    y = Var()
    return [deref(y) for _ in solve((goal, y), mod)]


def _ball(exc):
    return deref(exc.term)


# ── The ball from the continuation escapes ─────────────────────────────────


@pytest.mark.parametrize("goal, ball", [
    ("w5", "later"),           # a called goal after catch/3
    ("w_inline", "later"),     # an inline throw after catch/3
    ("nc2", "oops"),           # a goal woken by a comparison after catch/3
    ("nc2_unify", "oops"),     # ... by a unification after catch/3
    ("w6", "later"),           # catch/3 in the callee, ball in the caller
    ("nc3", "oops"),           # woken in the caller by the callee's freeze
    ("rk", "later"),           # after the recovery ran
    ("n_after_both", "later"),
    ("n_outer_declines", "b"), # the inner catcher would match it
    ("in_findall_bare", "later"),
])
def test_a_ball_from_the_continuation_escapes(mod, goal, ball):
    with pytest.raises(LogicException) as ei:
        _answers(mod, goal)
    assert _ball(ei.value) == ball


def test_a_goal_woken_inside_the_catch_goal_is_still_caught(mod):
    assert _answers(mod, "c_eq") == ["caught"]


# ── Nested catches ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("goal, expected", [
    ("n_outer_takes", ["b"]),        # thrown after the inner catch, inside the outer
    ("n_inner_matches", ["inner"]),
    ("n_inner_declines", ["outer"]),
])
def test_nested_catches(mod, goal, expected):
    assert _answers(mod, goal) == expected


# ── Inside a construct with a scope of its own ──────────────────────────────


@pytest.mark.parametrize("goal", ["in_findall", "in_forall", "in_once", "in_not"])
def test_a_ball_after_an_inner_catch_reaches_the_outer_catch(mod, goal):
    assert _answers(mod, goal) == ["outer"]


# ── Several answers, and re-entering the goal on backtracking ───────────────


def test_the_continuation_throwing_on_the_second_answer_escapes(mod):
    y = Var()
    got = []
    with pytest.raises(LogicException) as ei:
        for _ in solve(("multi", y), mod):
            got.append(deref(y))
    assert got == [1]
    assert _ball(ei.value) == "second"


@pytest.mark.parametrize("goal", ["reenter", "reenter_call", "reenter_inline"])
def test_the_goal_reentered_on_backtracking_is_protected_again(mod, goal):
    # The continuation rejects gen's first answer; gen's second answer throws
    # while the goal runs again, so the catch takes it (ISO, Scryer, Trealla).
    assert _answers(mod, goal) == ["two"]
