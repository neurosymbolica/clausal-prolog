"""Strictness through projection, and implied equalities, against the oracle.

todo/clpq-projection-strictness-and-implied-equalities-2026-10-11.md named
two answers weaker than Scryer's (Scryer's copy of clp(Q,R) 1.3.3):

* strictness carried by an eliminated variable: ``{X < Y, Y =< 3}`` onto X
  is ``X < 3``, not ``X =< 3``;
* equalities the bounds imply through rows: ``{X =< Y, Y =< 3, X >= 3}``
  binds X = 3, Y = 3.

The port (CLAUSAL_CLPQ=holzbaur) gives Scryer's answers on every path:
the Python-API driver of test_against_oracle.py (residual_strings), the
``clausal -g`` printer, dump/3, and dump_q.  Legacy gives Scryer's answer
for strictness (since 459cd660, "legacy keeps strict bounds in the
simplex") but not for implied equalities: those tests are marked xfail
(strict), so a legacy fix shows up as an XPASS.
"""
import functools

import pytest

from clausal.logic.clpq import holzbaur, legacy
from clausal.logic.variables import Trail, Var, deref, is_var
from tests.clpq_oracle import clausal_answers, oracle_answers, same_solution_sets
from tests.clpq_port.test_against_oracle import (
    check_against_oracle, port_answers, scryer_answers)

#: Strictness reaching a shown variable only through eliminated ones.
STRICT = [
    ("{X < Y, Y =< 3}", ["X"]),
    ("{X < Y, Y =< 3}", ["X", "Y"]),
    ("{X =< Y, Y < 3}", ["X"]),
    ("{X < Y, Y < Z, Z =< 3}", ["X"]),
    ("{X - Y > 0, Y >= 1}", ["X"]),
    ("{2*X < Y, Y + Z =< 4, Z >= 0}", ["X"]),
    ("{X < Y, Y =< 3}, {X >= 1}", ["X"]),
]

#: Bounds that force values (or variable equalities) through rows.
IMPLIED = [
    ("{X =< Y, Y =< 3, X >= 3}", ["X", "Y"]),
    ("{X =< Y, Y =< 3, X >= 3}", ["X"]),
    ("{X + Y = 4, X =< 2, Y =< 2}", ["X", "Y"]),
    ("{X =< Y, Y =< Z, Z =< X}", ["X", "Y", "Z"]),
    ("{X =< Y, Y =< Z, Z =< 3, X >= 3}", ["X", "Y", "Z"]),
    ("{X + Y =< 2, X >= 1, Y >= 1}", ["X", "Y"]),
    ("{X >= Y, Y >= 3}, {X =< 3}", ["X", "Y"]),
    ("{X - 2*Y =< 0, Y =< 1, X >= 2}", ["X", "Y"]),
]


@pytest.mark.parametrize("text, shown", STRICT + IMPLIED)
def test_the_port_projects_as_the_oracle(text, shown):
    want = scryer_answers(text, shown)
    got = port_answers(text, shown)
    check_against_oracle(text, shown, got, want)


# ---- the toplevel printer and dump/3, through the CLI, on both solvers -----

PROGRAM = r"""
:- use_module(library(clpq)).
strict_one(X) :- {X < Y, Y =< 3}.
strict_chain(X) :- {X < Y, Y < Z, Z =< 3}.
strict_scaled(X) :- {2*X < Y, Y + Z =< 4, Z >= 0}.
strict_dump(Cs) :- {X < Y, Y =< 3}, dump([X], [x], Cs).
implied_two(X, Y) :- {X =< Y, Y =< 3, X >= 3}.
implied_sum(X, Y) :- {X + Y = 4, X =< 2, Y =< 2}.
implied_scaled(X, Y) :- {X - 2*Y =< 0, Y =< 1, X >= 2}.
implied_dump(Cs) :- {X =< Y, Y =< 3, X >= 3, X + Y =< W}, dump([W], [w], Cs).
"""

CLI_STRICT = [("strict_one(X)", ["X"]), ("strict_chain(X)", ["X"]),
              ("strict_scaled(X)", ["X"]), ("strict_dump(Cs)", ["Cs"])]
#: Legacy finds these too: X + Y = 4 substitutes into Y's bound, so X's own
#: bounds meet; and dump/3 projects onto a free W, whose projection
#: (W >= 6) is the same whether X and Y are bound or not.  (dump/3 cannot
#: show the gap: a bound target is an uninstantiation_error.)
CLI_IMPLIED_BOTH = [("implied_sum(X, Y)", ["X", "Y"]),
                    ("implied_dump(Cs)", ["Cs"])]
#: Legacy leaves X and Y unbound here, with the three inequalities.
CLI_IMPLIED = [("implied_two(X, Y)", ["X", "Y"]),
               ("implied_scaled(X, Y)", ["X", "Y"])]

_LEGACY_IMPLIED = pytest.mark.xfail(
    strict=True, reason="legacy does not detect implied equalities (todo/"
    "clpq-projection-strictness-and-implied-equalities-2026-10-11.md)")


@functools.lru_cache(maxsize=None)
def _oracle(goal, variables):
    return oracle_answers(PROGRAM, goal, list(variables))


def _check_cli(solver, goal, variables):
    want = _oracle(goal, tuple(variables))
    got = clausal_answers(PROGRAM, goal, variables, solver)
    ok, why = same_solution_sets(got, want)
    assert ok, f"{goal} under {solver}\n{why}\nclausal: {got}\noracle:  {want}"


@pytest.mark.parametrize("solver", ["legacy", "holzbaur"])
@pytest.mark.parametrize("goal, variables", CLI_STRICT + CLI_IMPLIED_BOTH)
def test_the_cli_answers_as_the_oracle_on_both_solvers(solver, goal, variables):
    _check_cli(solver, goal, variables)


@pytest.mark.parametrize("solver", [pytest.param("legacy", marks=_LEGACY_IMPLIED),
                                    "holzbaur"])
@pytest.mark.parametrize("goal, variables", CLI_IMPLIED)
def test_the_cli_shows_implied_equalities_as_the_oracle(solver, goal, variables):
    _check_cli(solver, goal, variables)


# ---- the Python API, dump_q ------------------------------------------------

@pytest.mark.parametrize("solver", [legacy, holzbaur], ids=["legacy", "holzbaur"])
def test_dump_q_keeps_strictness_through_an_eliminated_variable(solver):
    trail, x, y = Trail(), Var(), Var()
    assert solver.q_lt(x, y, trail) and solver.q_le(y, 3, trail)
    assert solver.dump_q([x], trail, lambda v: "X") == ["{X < 3}"]


@pytest.mark.parametrize("solver", [pytest.param(legacy, marks=_LEGACY_IMPLIED),
                                    holzbaur], ids=["legacy", "holzbaur"])
def test_dump_q_sees_implied_equalities_bound(solver):
    trail, x, y = Trail(), Var(), Var()
    assert (solver.q_le(x, y, trail) and solver.q_le(y, 3, trail)
            and solver.q_ge(x, 3, trail))
    assert not is_var(deref(x)) and not is_var(deref(y))
    assert (deref(x), deref(y)) == (3, 3)
    assert solver.dump_q([x, y], trail) == []
