"""The CLP(Q) oracle comparison tool (tests/clpq_oracle.py).

The first group checks ``same_solution_sets`` on hand-built answers; the
second runs real programs on Scryer and on Clausal through the two runners.
"""
import pathlib

import pytest

from tests._oracles import SCRYER
from tests.clpq_oracle import (
    Answer, clausal_answers, oracle_answers, same_solution_sets)

needs_scryer = pytest.mark.skipif(
    not pathlib.Path(SCRYER).exists(), reason="needs the local Scryer CLP(Q) build")


def test_the_same_residual_in_another_form_is_equal():
    a = [Answer({}, ["X+Y=<3", "X>=0"])]
    b = [Answer({}, ["0=<X", "Y=<3-X"])]
    assert same_solution_sets(a, b)[0]


def test_a_weaker_residual_is_not_equal():
    a = [Answer({}, ["X<3"])]
    b = [Answer({}, ["X=<3"])]
    ok, why = same_solution_sets(a, b)
    assert not ok and "X" in why


def test_bindings_must_match():
    assert not same_solution_sets([Answer({"X": 1}, [])], [Answer({"X": 2}, [])])[0]


def test_the_number_and_order_of_answers_count():
    one = Answer({"X": 1}, [])
    two = Answer({"X": 2}, [])
    assert not same_solution_sets([one, two], [two, one])[0]


def test_residuals_differing_only_in_internal_names_are_equal():
    a = [Answer({}, ["X+_A=<3", "_A>=0"])]
    b = [Answer({}, ["X+_Q1=<3", "_Q1>=0"])]
    assert same_solution_sets(a, b)[0]


def test_internal_variables_are_existential():
    # X = 2*_A with _A >= 0 says only X >= 0.
    a = [Answer({}, ["X=2*_A", "_A>=0"])]
    b = [Answer({}, ["X>=0"])]
    assert same_solution_sets(a, b)[0]


def test_rational_spellings_are_the_same_number():
    a = [Answer({}, ["X>= -1 rdiv 3", "Y=5 rdiv 14+1 rdiv 2*X"])]
    b = [Answer({}, ["X >= -1/3", "-1/2*X + Y = 5/14"])]
    assert same_solution_sets(a, b)[0]


@needs_scryer
def test_scryer_against_itself_on_a_known_store():
    program = ":- use_module(library(clpq)).\np(X, Y) :- {X + Y =< 3, X >= 0}.\n"
    answers = oracle_answers(program, "p(X, Y)", ["X", "Y"])
    assert same_solution_sets(answers, [Answer({}, ["X+Y=<3", "X>=0"])])[0]


@needs_scryer
def test_the_oracle_collects_every_answer_with_bindings():
    program = (":- use_module(library(clpq)).\n"
               "q(X) :- {X = 1/2}.\nq(X) :- {X >= 2}.\n")
    answers = oracle_answers(program, "q(X)", ["X"])
    from fractions import Fraction
    assert same_solution_sets(
        answers, [Answer({"X": Fraction(1, 2)}, []), Answer({}, ["X>=2"])])[0]


@needs_scryer
def test_clausal_legacy_matches_the_oracle():
    program = ":- use_module(library(clpq)).\np(X, Y) :- {X + Y =< 3, X >= 0}.\n"
    oracle = oracle_answers(program, "p(X, Y)", ["X", "Y"])
    clausal = clausal_answers(program, "p(X, Y)", ["X", "Y"], solver="legacy")
    ok, why = same_solution_sets(oracle, clausal)
    assert ok, why


@needs_scryer
def test_a_known_different_pair_is_reported():
    program = ":- use_module(library(clpq)).\np(X) :- {X >= 0, X =< 2}.\n"
    oracle = oracle_answers(program, "p(X)", ["X"])
    ok, why = same_solution_sets(oracle, [Answer({}, ["X>=0", "X=<3"])])
    assert not ok and "residual" in why


@needs_scryer
def test_no_answers_on_either_side():
    program = ":- use_module(library(clpq)).\np(X) :- {X >= 1, X =< 0}.\n"
    assert oracle_answers(program, "p(X)", ["X"]) == []
    assert clausal_answers(program, "p(X)", ["X"], solver="legacy") == []
