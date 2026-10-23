"""``1 = 1.0`` fails (ISO 7.3): the engine against the Scryer oracle, on one
ISO Prolog text run by both.

Operator ruling 2026-10-23 (todo/done/iso-unify-conflates-int-and-float-
2026-09-09.md).  Each case is a goal with a yes/no or a count answer; the
engine loads PROGRAM as a ``.pl`` module and Scryer consults the same text.
The engine-only matrix (the seam, ``.clausal``, tabling, the API) is
``tests/test_iso_int_float_unify.py``.
"""

from __future__ import annotations

import pytest

from clausal._suffixes import PROLOG_SUFFIX as PL
from clausal.import_hook import _load_module
from clausal.logic.solve import solve
from clausal.logic.variables import Trail

PROGRAM = """\
:- use_module(library(clpz)).
:- use_module(library(dif)).
:- use_module(library(lists)).
:- dynamic(q/1).
p(1).
r(1). r(1.0). r(2). r(3). r(4). r(5).
"""

# (name, goal, expected) -- the goal is ISO text both engines run as is.
YES_NO = [
    ("unify_int_float", "1 = 1.0", "no"),
    ("unify_float_int", "1.0 = 1", "no"),
    ("unify_same_int", "1 = 1", "yes"),
    ("unify_same_float", "1.0 = 1.0", "yes"),
    ("compound", "f(1) = f(1.0)", "no"),
    ("via_variable", "X = 1, X = 1.0", "no"),
    ("list", "[1] = [1.0]", "no"),
    ("fact_p1_called_with_float", "p(1.0)", "no"),
    ("fact_p1_called_with_int", "p(1)", "yes"),
    ("indexed_r_float", "r(1.0)", "yes"),
    ("not_unifiable", "1 \\= 1.0", "yes"),
    ("copy_term", "copy_term(f(1), f(1.0))", "no"),
    ("assertz_then_retract_float", "assertz(q(1)), retract(q(1.0))", "no"),
    ("assertz_then_retract_int", "assertz(q(2)), retract(q(2))", "yes"),
    ("dif_then_bind_int", "dif(X, 1.0), X = 1", "yes"),
    ("dif_then_bind_float", "dif(X, 1.0), X = 1.0", "no"),
    ("clpz_then_unify_float", "X #= 1, X = 1.0", "no"),
    ("clpz_then_unify_int", "X #= 1, X = 1", "yes"),
    ("memberchk_float_in_int_list", "memberchk(1.0, [1])", "no"),
    ("memberchk_int_second", "memberchk(1, [1.0, 1])", "yes"),
    ("setof_keeps_both", "setof(X, member(X, [1, 1.0, 2]), [1.0, 1, 2])", "yes"),
    ("structural_eq_still_fails", "1 == 1.0", "no"),
    ("arith_eq_still_succeeds", "1 =:= 1.0", "yes"),
]

COUNTS = [
    ("r_float_answers", "r(1.0)", 1),
    ("r_int_answers", "r(1)", 1),
    ("r_all_answers", "r(_)", 6),
    ("p_float_answers", "p(1.0)", 0),
]


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    """Load PROGRAM as a .pl module; ``run(goal)`` counts its solutions
    through a t/0-style wrapper clause appended per goal."""
    d = tmp_path_factory.mktemp("scryer_int_float")
    counter = [0]

    def run(goal: str) -> int:
        counter[0] += 1
        name = f"_sif{counter[0]}"
        path = d / f"{name}{PL}"
        path.write_text(PROGRAM + f"t(1) :- {goal}.\n")
        mod = _load_module(name, str(path))
        return sum(1 for _ in solve(("t", 1), mod, Trail()))
    return run


@pytest.mark.parametrize("name, goal, expected", YES_NO, ids=[c[0] for c in YES_NO])
def test_yes_no_engine(engine, name, goal, expected):
    assert engine(goal) == (1 if expected == "yes" else 0), (name, goal)


@pytest.mark.parametrize("name, goal, expected", YES_NO, ids=[c[0] for c in YES_NO])
def test_yes_no_oracle(scryer, name, goal, expected):
    got = scryer(f"(({goal}) -> write(yes) ; write(no)), nl, halt.", PROGRAM)
    assert got == expected, (name, goal, got)


@pytest.mark.parametrize("name, goal, expected", COUNTS, ids=[c[0] for c in COUNTS])
def test_count_engine(engine, name, goal, expected):
    assert engine(f"findall(x, ({goal}), L), length(L, {expected})") == 1, (name, goal)


@pytest.mark.parametrize("name, goal, expected", COUNTS, ids=[c[0] for c in COUNTS])
def test_count_oracle(scryer, name, goal, expected):
    got = scryer(f"findall(x, ({goal}), L), length(L, N), write(N), nl, halt.", PROGRAM)
    assert got == str(expected), (name, goal, got)
