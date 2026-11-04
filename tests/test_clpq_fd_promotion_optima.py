"""A CLP(FD) variable that enters CLP(Q) through in_q/1,3, sup/2, inf/2,
maximize, minimize or bb_inf brings its FD bounds with it.

docs/clpq.md ("FD<->Q coexistence"): when a CLP(Z) variable enters a CLP(Q)
context its FD bounds become rational bounds and both attributes stay.  A
comparison post did that ({X =< 7}); in_q and the optima did not.  With
X in 1..5 and no CLP(Q) state, ``sup(X, S)`` failed (X was unbounded to
CLP(Q)), and ``in_q(X, 0, 20), sup(X, S)`` gave 20.  The default solver's
promotion also raised OverflowError on an FD variable with an infinite end
(``X #\\= 3, {X =< 7}``)
(todo/done/clpq-prolog-surface-gaps-entailed-dump-tabling-2026-10-12.md,
item 4).

A variable that has neither state is unbounded, as in clp(q,r) 1.3.3:
sup/2 of it fails.  So does sup/2 of an FD variable whose domain has no
upper end.

Runs under the solver ``CLAUSAL_CLPQ`` selects; run the file under both.
"""
from fractions import Fraction

import pytest

from clausal.import_hook import _load_module
from clausal.logic.clpfd import FD_KEY, fd_ne, in_domain
from clausal.logic.clpq import (
    Q_KEY, bb_inf, in_q, inf, maximize, minimize, q_le, sup)
from clausal.logic.solve import _query_cache, call
from clausal.logic.variables import Trail, Var, deref, get_attr


def _domain(lo, hi):
    trail, x = Trail(), Var()
    assert in_domain(x, lo, hi, trail)
    assert get_attr(x, Q_KEY) is None
    return trail, x


def _value(goal):
    result = Var()
    assert goal(result)
    return deref(result)


def test_sup_and_inf_of_an_fd_variable_see_its_bounds():
    trail, x = _domain(1, 5)
    assert _value(lambda s: sup(x, s, trail)) == 5
    assert _value(lambda s: inf(x, s, trail)) == 1
    assert get_attr(x, FD_KEY) is not None      # the FD attribute stays
    assert get_attr(x, Q_KEY) is not None


def test_sup_of_an_expression_over_fd_variables():
    trail, x = _domain(1, 5)
    y = Var()
    assert in_domain(y, 0, 2, trail)
    assert _value(lambda s: sup(("+", x, ("*", 2, y)), s, trail)) == 9


def test_maximize_and_minimize_of_an_fd_variable():
    trail, x = _domain(1, 5)
    mark = trail.mark()
    assert _value(lambda s: maximize(x, s, trail)) == 5
    assert deref(x) == 5
    trail.undo(mark)
    assert _value(lambda s: minimize(x, s, trail)) == 1
    assert deref(x) == 1


def test_bb_inf_of_an_fd_variable():
    trail, x = _domain(2, 5)
    assert _value(lambda s: bb_inf([x], x, s, trail)) == 2


def test_in_q_of_an_fd_variable_keeps_its_bounds():
    trail, x = _domain(1, 5)
    assert in_q(x, trail=trail)
    assert _value(lambda s: sup(x, s, trail)) == 5


def test_in_q_with_wider_bounds_keeps_the_fd_bounds():
    trail, x = _domain(1, 5)
    assert in_q(x, 0, 20, trail)
    assert _value(lambda s: sup(x, s, trail)) == 5
    assert _value(lambda s: inf(x, s, trail)) == 1


def test_in_q_with_narrower_bounds_narrows():
    trail, x = _domain(1, 5)
    assert in_q(x, Fraction(3, 2), 4, trail)
    assert _value(lambda s: inf(x, s, trail)) == Fraction(3, 2)
    assert _value(lambda s: sup(x, s, trail)) == 4


def test_in_q_with_disjoint_bounds_fails():
    trail, x = _domain(1, 5)
    assert not in_q(x, 6, 7, trail)


def test_an_fd_variable_with_an_infinite_end():
    """X #\\= 3: no finite bound to bring.  in_q/1 makes it a CLP(Q)
    variable; sup/2 fails, it is unbounded; a later bound counts.  The
    default solver's promotion raised OverflowError (Fraction(inf))."""
    trail, x = Trail(), Var()
    assert fd_ne(x, 3, trail)
    assert not sup(x, Var(), trail)
    assert in_q(x, trail=trail)
    assert not sup(x, Var(), trail)
    assert q_le(x, 7, trail)
    assert _value(lambda s: sup(x, s, trail)) == 7


def test_a_comparison_post_on_an_fd_variable_with_an_infinite_end():
    trail, x = Trail(), Var()
    assert fd_ne(x, 3, trail)
    assert q_le(x, 7, trail)
    assert _value(lambda s: sup(x, s, trail)) == 7


def test_a_variable_with_no_state_is_unbounded():
    """As in 1.3.3: sup/2 of a variable the store does not know fails."""
    trail, x = Trail(), Var()
    assert not sup(x, Var(), trail)
    assert in_q(x, trail=trail)
    assert not sup(x, Var(), trail)


PL = """\
:- use_module(library(clpq)).
:- use_module(library(clpz)).
s(S) :- X #>= 1, X #=< 5, sup(X, S).
i(S) :- X #>= 1, X #=< 5, in_q(X, 0, 20), inf(X, S).
q(S) :- X #>= 1, X #=< 5, in_q(X), sup(X, S).
open_end(S) :- X #\\= 3, {X =< 7}, sup(X, S).
"""


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
@pytest.mark.parametrize("name, expected", [
    ("s", 5), ("i", 1), ("q", 5), ("open_end", 7)])
def test_on_the_prolog_surfaces(tmp_path, suffix, name, expected):
    path = tmp_path / f"fd_promotion_{name}{suffix}"
    path.write_text(PL, encoding="utf-8")
    module = _load_module(path.stem, path)
    _query_cache.clear()
    result = Var()
    answers = [deref(result) for _ in call(name, result, module=module)]
    _query_cache.clear()
    assert answers == [expected]


# ---- an FD domain with holes -------------------------------------------
#
# Promotion brings the FD domain's hull (its least and greatest values),
# a rational relaxation.  sup/2 and inf/2 answer on the relaxation: with
# X in 1..3 \/ 7..9 and {X >= 4}, inf(X, I) gives 4 though X is at least 7.
# An optimum that BINDS (maximize, minimize) or must be integral and in
# the domain (bb_inf) cannot be had from the relaxation: bb_inf gave 5, a
# value in the hole, and maximize/minimize failed where a value exists.
# They raise representation_error(fd_domain_with_holes) for an FD
# variable with holes in the objective (or bb_inf's integers).

HOLES_PL = """\
:- use_module(library(clpq)).
:- use_module(library(clpz)).
bb(I) :- X in 1..3 \\/ 7..9, {X >= 4}, bb_inf([X], X, I).
bb_ints(I) :- X in 1..3 \\/ 7..9, {Y >= 4, Y = X}, bb_inf([X], Y, I).
mx(X) :- X in 0..2 \\/ 8..10, {X =< 7}, maximize(X).
mn(X) :- X in 1..3 \\/ 7..9, in_q(X, 4, 10), minimize(X).
sp(S) :- X in 0..2 \\/ 8..10, {X =< 7}, sup(X, S).
nf(S) :- X in 1..3 \\/ 7..9, {X >= 4}, inf(X, S).
caught(F) :- X in 1..3 \\/ 7..9, catch(maximize(X), error(F, _), true).
"""


def _holes_module(tmp_path, suffix):
    path = tmp_path / f"fd_holes{suffix}"
    path.write_text(HOLES_PL, encoding="utf-8")
    return _load_module(path.stem, path)


def _first(module, name):
    _query_cache.clear()
    result = Var()
    try:
        return [deref(result) for _ in call(name, result, module=module)]
    finally:
        _query_cache.clear()


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
@pytest.mark.parametrize("name", ["bb", "bb_ints", "mx", "mn"])
def test_an_optimum_over_a_domain_with_holes_is_refused(tmp_path, suffix, name):
    from clausal.logic.exceptions import LogicException
    module = _holes_module(tmp_path, suffix)
    with pytest.raises(LogicException) as raised:
        _first(module, name)
    assert raised.value.term[1] == ("representation_error",
                                    "fd_domain_with_holes")


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_the_error_can_be_caught(tmp_path, suffix):
    module = _holes_module(tmp_path, suffix)
    assert _first(module, "caught") == [("representation_error",
                                         "fd_domain_with_holes")]


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
@pytest.mark.parametrize("name, expected", [("sp", 7), ("nf", 4)])
def test_sup_and_inf_over_a_domain_with_holes_answer_on_the_hull(
        tmp_path, suffix, name, expected):
    """The relaxation's bound (documented): 7 and 4, where the domain's
    own are 2 and 7."""
    assert _first(_holes_module(tmp_path, suffix), name) == [expected]


# ---- holes reached through the store; a relaxed optimum not integral ----
#
# Operator ruling 2026-11-03 (option A of
# todo/done/clpq-optimum-over-fd-variables-is-a-relaxation-2026-11-03.md):
# maximize, minimize and bb_inf never give a wrong answer or a silent
# failure from the relaxation.
#
# 1. An FD variable with holes anywhere in the objective's component of
#    the store (linked to it by constraints, not only written in it)
#    raises representation_error(fd_domain_with_holes): {Y = X, Y =< 7},
#    maximize(Y) bound X = 7, in the hole, so it failed, though Y = 2
#    exists; {Y = 2*X + Z, ...} gave Y = 7 on the port, a wrong answer
#    (X = 3..7/2 is in the hole).
# 2. maximize and minimize whose relaxed optimum gives an FD variable a
#    value that is not an integer raise
#    representation_error(fd_relaxation_not_integral): X in 1..5,
#    {2*X >= 3}, minimize(X) bound X = 3/2, clpfd refused it, so it
#    failed, though X = 2 exists.
# An FD variable with holes in another component, and an optimum that is
# integral, answer as before.

LINKED_PL = """\
:- use_module(library(clpq)).
:- use_module(library(clpz)).
mx_linked(Y) :- X in 0..2 \\/ 8..10, {Y = X, Y =< 7}, maximize(Y).
mn_linked(Y) :- X in 0..2 \\/ 8..10, {Y = X, Y >= 3}, minimize(Y).
mx_through(Y) :- X in 0..2 \\/ 8..10,
    {Y = 2*X + Z, Z >= 0, Z =< 1, Y =< 7}, maximize(Y).
bb_linked(I) :- X in 0..2 \\/ 8..10, {Y = X, Y =< 7}, bb_inf([], -Y, I).
bb_linked_ints(I) :- X in 0..2 \\/ 8..10, {Y = X, Y =< 7},
    bb_inf([Y], -Y, I).
mn_fraction(X) :- X in 1..5, {2*X >= 3}, minimize(X).
mx_fraction(X) :- X in 1..5, {3*X =< 10}, maximize(X).
mx_fraction_linked(Y) :- X in 1..5, {Y = 2*X, Y =< 7}, maximize(Y).
mx_elsewhere(Y) :- X in 0..2 \\/ 8..10, {X =< 9}, {Y =< 7}, maximize(Y).
mn_integral(X) :- X in 1..5, {2*X >= 4}, minimize(X).
mx_integral_linked(Y) :- X in 1..5, {Y = X / 2}, maximize(Y).
bb_relaxed(I) :- X in 1..5, {2*X >= 3}, bb_inf([], X, I).
bb_integral(I) :- X in 1..5, {2*X >= 3}, bb_inf([X], X, I).
caught_fraction(F) :- X in 1..5, {2*X >= 3},
    catch(minimize(X), error(F, _), true).
"""


def _linked_module(tmp_path, suffix):
    path = tmp_path / f"fd_linked{suffix}"
    path.write_text(LINKED_PL, encoding="utf-8")
    return _load_module(path.stem, path)


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
@pytest.mark.parametrize("name, flag", [
    ("mx_linked", "fd_domain_with_holes"),
    ("mn_linked", "fd_domain_with_holes"),
    ("mx_through", "fd_domain_with_holes"),
    ("bb_linked", "fd_domain_with_holes"),
    ("bb_linked_ints", "fd_domain_with_holes"),
    ("mn_fraction", "fd_relaxation_not_integral"),
    ("mx_fraction", "fd_relaxation_not_integral"),
    ("mx_fraction_linked", "fd_relaxation_not_integral"),
])
def test_an_optimum_the_relaxation_cannot_answer_is_refused(
        tmp_path, suffix, name, flag):
    from clausal.logic.exceptions import LogicException
    module = _linked_module(tmp_path, suffix)
    with pytest.raises(LogicException) as raised:
        _first(module, name)
    assert raised.value.term[1] == ("representation_error", flag)


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_the_integrality_error_can_be_caught(tmp_path, suffix):
    assert _first(_linked_module(tmp_path, suffix), "caught_fraction") == [
        ("representation_error", "fd_relaxation_not_integral")]


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
@pytest.mark.parametrize("name, expected", [
    ("mx_elsewhere", 7),            # the holed X is in another component
    ("mn_integral", 2),
    ("mx_integral_linked", Fraction(5, 2)),     # X = 5
    ("bb_integral", 2),
])
def test_an_optimum_the_relaxation_answers_is_kept(
        tmp_path, suffix, name, expected):
    assert _first(_linked_module(tmp_path, suffix), name) == [expected]


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_bb_inf_over_an_fd_variable_not_among_its_integers(tmp_path, suffix):
    """bb_inf([], X, I) asks for the relaxation over X.  The port leaves
    the store as it was (1.3.3's bb_inf binds nothing), so it answers
    3/2.  The default solver binds the store at the optimum, X = 3/2,
    which clpfd refused, so it failed; it now raises the integrality
    error."""
    from clausal.logic.clpq import SOLVER
    from clausal.logic.exceptions import LogicException
    module = _linked_module(tmp_path, suffix)
    if SOLVER == "holzbaur":
        assert _first(module, "bb_relaxed") == [Fraction(3, 2)]
        return
    with pytest.raises(LogicException) as raised:
        _first(module, "bb_relaxed")
    assert raised.value.term[1] == ("representation_error",
                                    "fd_relaxation_not_integral")
