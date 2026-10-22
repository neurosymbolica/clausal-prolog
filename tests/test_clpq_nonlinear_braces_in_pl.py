"""A non-linear function inside clpq's ``{}`` in a .pl file: nf.pl's
``abs``, ``sin``, ``cos``, ``tan``, ``min``, ``max``, ``exp``, ``pow`` and
``^``.

The native front end lowered only ``+ - * /`` inside the braces and refused
the program at load (todo/clpq-port-vs-sicstus-manual-23-gaps-2026-10-16.md
item 4); the port delays a non-linear constraint as SICStus does, the
default solver refuses it when posted.  The manual's ten queries are in
tests/clpq_port/test_manual_examples.py::test_nonlinear; these run without
the example files, through the CLI.
"""
from fractions import Fraction

import pytest

from tests.clpq_oracle import clausal_answers

PROGRAM = r"""
:- use_module(library(clpq)).

q_sin_cos(X) :- {sin(X) = cos(X)}.
q_sin_of_cos(X) :- {sin(cos(X)) = 1/2}.
q_square(X, Y) :- {exp(X+Y+1, 2) = 3*X*X + Y*Y}, X = Y.
q_pow(X) :- {12 = pow(2, X)}.
q_abs(X) :- {abs(X) = 3}, X = -3.
q_abs_fails(X) :- {abs(X) = 3}, X = 2.
q_min(X) :- {X = min(3, 5) + max(1, 2)}.
"""


def _answers(solver, goal, variables):
    return clausal_answers(PROGRAM, goal, variables, solver)


def _one(solver, goal, variables):
    [answer] = _answers(solver, goal, variables)
    return answer


def test_a_nonlinear_function_in_braces_waits_on_the_port():
    # nf.pl delays {sin(X) = cos(X)} until X is known; the answer shows it.
    answer = _one("holzbaur", "q_sin_cos(X)", ["X"])
    assert answer.bindings == {}
    assert answer.residual, answer


def test_a_nonlinear_function_in_braces_is_refused_by_legacy_at_run_time():
    # Legacy cannot delay a non-linear constraint (DEVIATIONS.md D20): the
    # program loads, the post raises.  It was refused at load, for both.
    with pytest.raises(RuntimeError, match=r"exited|linear"):
        _answers("legacy", "q_sin_cos(X)", ["X"])


def test_a_nested_nonlinear_function_reaches_the_port():
    # sin(cos(X)): the post boundary's strict rewrite (ruling R9 A1)
    # refused the inner cos/1, an evaluable with no operator node, as
    # type_error(evaluable, cos/1) once it was nested.
    answer = _one("holzbaur", "q_sin_of_cos(X)", ["X"])
    assert abs(float(answer.bindings["X"]) - 1.0197267436954502) < 1e-9


def test_a_square_collapses_when_its_variables_are_equal():
    answer = _one("holzbaur", "q_square(X, Y)", ["X", "Y"])
    assert answer.bindings == {"X": Fraction(-1, 4), "Y": Fraction(-1, 4)}


def test_pow_with_the_exponent_unknown():
    answer = _one("holzbaur", "q_pow(X)", ["X"])
    assert abs(float(answer.bindings["X"]) - 3.5849625007211565) < 1e-9


def test_abs_min_and_max_in_braces():
    # {abs(X) = 3} waits for X; the binding checks it.
    assert _one("holzbaur", "q_abs(X)", ["X"]).bindings == {"X": -3}
    assert _answers("holzbaur", "q_abs_fails(X)", ["X"]) == []
    assert _one("holzbaur", "q_min(X)", ["X"]).bindings == {"X": 5}
