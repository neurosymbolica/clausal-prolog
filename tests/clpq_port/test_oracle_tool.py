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


# ---- fix round 1 -------------------------------------------------------------

from fractions import Fraction  # noqa: E402

from tests.clpq_oracle import _parse_clausal_line, _value  # noqa: E402


@needs_scryer
def test_aliased_shown_variables_keep_their_answer():
    program = ":- use_module(library(clpq)).\na(X, Y) :- X = Y, {X >= 1}.\n"
    oracle = oracle_answers(program, "a(X, Y)", ["X", "Y"])
    assert len(oracle) == 1
    clausal = clausal_answers(program, "a(X, Y)", ["X", "Y"], solver="legacy")
    ok, why = same_solution_sets(oracle, clausal)
    assert ok, why


@needs_scryer
def test_a_failing_dump_raises_instead_of_dropping_the_answer(monkeypatch):
    import tests.clpq_oracle as tool
    broken = tool._SCRYER_HELPER.replace("dump(Free, FreeNames, Cs0)", "fail")
    monkeypatch.setattr(tool, "_SCRYER_HELPER", broken)
    program = ":- use_module(library(clpq)).\np(X) :- {X >= 1}.\n"
    with pytest.raises(RuntimeError, match="dump_failed"):
        oracle_answers(program, "p(X)", ["X"])


def test_a_forced_value_in_the_residual_is_a_binding():
    a = [Answer({"X": Fraction(3)}, ["Y>=X"])]
    b = [Answer({}, ["X = 3", "Y >= 3"])]
    ok, why = same_solution_sets(a, b)
    assert ok, why


def test_an_equality_of_shown_variables_is_one_canonical_form():
    clausal = [_parse_clausal_line("Y = X, {X >= 1}.", ["X", "Y"])]
    oracle = [Answer({}, ["X=Y", "X>=1"])]
    ok, why = same_solution_sets(oracle, clausal)
    assert ok, why


def test_division_keeps_prolog_precedence():
    assert not same_solution_sets([Answer({}, ["Y=X/2/3"])], [Answer({}, ["Y=3/2*X"])])[0]
    assert same_solution_sets([Answer({}, ["Y=X/2/3"])], [Answer({}, ["Y=1/6*X"])])[0]


def test_a_float_in_a_residual_is_refused():
    with pytest.raises(ValueError):
        same_solution_sets([Answer({}, ["X>=0.1"])], [Answer({}, ["X>=1/10"])])


def test_only_arithmetic_is_evaluated():
    with pytest.raises(ValueError):
        same_solution_sets([Answer({}, ["X=X.__class__"])], [Answer({}, [])])


def test_an_answer_item_that_is_not_a_binding_is_refused():
    with pytest.raises(ValueError):
        _parse_clausal_line("X*Y = 6, {X >= 1}.", ["X", "Y"])
    with pytest.raises(ValueError):
        _parse_clausal_line("dif(X, Y).", ["X", "Y"])
    assert _parse_clausal_line("_A = 1, X = 2.", ["X"]).bindings == {"X": 2}


def test_bindings_compare_by_kind_and_value():
    assert not same_solution_sets([Answer({"X": 0.5}, [])],
                                  [Answer({"X": Fraction(1, 2)}, [])])[0]
    assert same_solution_sets([Answer({"X": 1}, [])], [Answer({"X": Fraction(1)}, [])])[0]


def test_parenthesised_negative_rationals_parse():
    assert _value("(-1)/2") == Fraction(-1, 2)
    assert _value("-(1 rdiv 2)") == Fraction(-1, 2)
    assert _value("f(Y)") == "f(Y)"


def test_clausal_answers_do_not_need_scryer(monkeypatch):
    import tests.clpq_oracle as tool
    monkeypatch.setattr(tool, "SCRYER", "/nonexistent/scryer-prolog")
    program = ":- use_module(library(clpq)).\np(X) :- {X >= 1}.\n"
    assert tool.clausal_answers(program, "p(X)", ["X"], solver="legacy") == [
        Answer({}, ["X >= 1"])]


# ---- fix round 2 -------------------------------------------------------------

def test_a_binding_is_not_evaluated():
    assert _value("1+1") == "1+1"
    assert _value("-(1 rdiv 2)") == Fraction(-1, 2)
    assert not same_solution_sets([Answer({"X": _value("1+1")}, [])],
                                  [Answer({"X": _value("2")}, [])])[0]


def test_a_negative_literal_is_the_base_of_a_power():
    # Prolog reads -2 as one number, so -2^2 is (-2)^2 = 4 (Scryer: Y is -2^2 gives 4).
    assert same_solution_sets([Answer({}, ["Y=-2^2"])], [Answer({}, ["Y=4"])])[0]
    assert not same_solution_sets([Answer({}, ["Y=-2^2"])], [Answer({}, ["Y=-4"])])[0]


def test_an_arithmetic_equality_with_a_constant_is_a_binding():
    ok, why = same_solution_sets([Answer({"X": Fraction(3)}, [])], [Answer({}, ["X=:=3"])])
    assert ok, why


def test_blanks_that_separate_two_words_are_refused():
    with pytest.raises(ValueError):
        same_solution_sets([Answer({}, ["Y=X mod 2"])], [Answer({}, ["Y=X mod 2"])])


# ---- fix round 3 -------------------------------------------------------------

def _equal(left, right):
    return same_solution_sets([Answer({}, [left])], [Answer({}, [right])])[0]


def test_a_negative_literal_is_read_from_the_source_text():
    # Scryer: W = -(2^2), Y is W gives -4 and prints W as `- (2^2)`;
    # V = -2^2, U is V gives 4.
    assert _equal("Y=-(2^2)", "Y=-4")
    assert not _equal("Y=-(2^2)", "Y=4")
    assert _equal("Y= - (2^2)", "Y=-4")
    assert not _equal("Y=X*(-(2^2))", "Y=4*X")
    assert _equal("Y=-2^2", "Y=4")
    assert not _equal("Y=-2^2", "Y=-4")
    assert _equal("Y=X-2^2", "Y=X-4")
    assert _equal("X>=2^ -1", "X>=1/2")


def test_a_power_is_right_associative():
    # ^ is 200 xfy in ISO and Scryer: X^2^2 is X^(2^2).
    assert _equal("Y=X^2^2", "Y=X^4")
    assert not _equal("Y=X^2^2", "Y=X^2*X^2*X^2")


def _binding(text):
    return [Answer({"X": _value(text)}, [])]


def test_only_a_prolog_float_literal_is_a_float():
    assert _value("1.5e3") == 1500.0
    assert _value("inf") == "inf" and _value("nan") == "nan"
    assert not same_solution_sets(_binding("inf"), _binding("infinity"))[0]
    # Inf and Infinity are variable names: shown-variable equalities, not floats.
    assert _value("Inf") == "Inf"
    assert not same_solution_sets(_binding("Inf"), _binding("Infinity"))[0]


def test_a_binding_rational_is_printed_in_lowest_terms():
    assert not same_solution_sets(_binding("4/2"), _binding("2"))[0]
    assert not same_solution_sets(_binding("1/2/3"), _binding("1 rdiv 6"))[0]
    assert not same_solution_sets(_binding("- (1)"), _binding("-1"))[0]
    for text, number in [("1/2", Fraction(1, 2)), ("-1/2", Fraction(-1, 2)),
                         ("1 rdiv 2", Fraction(1, 2)), ("-1 rdiv 2", Fraction(-1, 2)),
                         ("-3", Fraction(-3)), ("7", Fraction(7))]:
        assert _value(text) == number, text


def test_text_is_normalised_once():
    # _sides splits the printed text and leaves each side as it was; _parse
    # normalises a side exactly once.  (Round 3 read `- 2^2` as -(2^2); the
    # engines read the sign and the number as one literal, so it is 4.)
    assert _sides("Y = - 2 ^ 2") == ("Y", "=", "- 2 ^ 2")
    assert _equal("Y= - 2^2", "Y=4")


def test_python_only_number_syntax_is_refused():
    assert _value("1_000") == "1_000"
    with pytest.raises(ValueError):
        _equal("X>=1_000", "X>=1000")


# ---- fix round 4 -------------------------------------------------------------

from tests.clpq_oracle import _constant, _mark_negative_literals, _sides  # noqa: E402


def test_a_malformed_negative_number_is_refused_not_dropped():
    # A `-` before text that is not a Prolog integer is left unmarked, so the
    # existing refusals see it; it must never become an existential variable.
    for text in ["X>= -1_000", "X>= -0x10", "X>= -1e3", "X>= -2j"]:
        with pytest.raises(ValueError):
            _equal(text, "X>=5")
        with pytest.raises(ValueError):
            same_solution_sets([Answer({}, [text])], [Answer({}, [])])
    assert _mark_negative_literals("X>= -1_000") == "X>= -1_000"
    for text in ["-1_000", "-0x10", "-1e3", "-2j"]:
        assert _value(text) == text
    # A name that only looks like a marker is refused too.
    with pytest.raises(ValueError):
        _equal("X>=__negative_literal_1_000", "X>=5")


def test_a_sign_then_blanks_then_a_number_is_the_number():
    # Scryer and Trealla read `- 2` as the integer -2 (integer(- 1) succeeds;
    # V = - 2^2, U is V gives 4), unless the `-` is infix.
    assert _equal("Y= - 2^2", "Y=4")
    assert not _equal("Y= - 2^2", "Y=-4")
    assert _equal("Y=X* - 2^2", "Y=4*X")
    assert _equal("Y=-(2^2)", "Y=-4")
    assert _equal("Y= - (2^2)", "Y=-4")
    assert _equal("Y=X - 2", "Y=X+(-2)")
    assert _equal("Y=X - 2^2", "Y=X-4")
    assert _equal("X>= - 1 rdiv 3", "X>= -1/3")
    assert _value("- 2") == Fraction(-2)


def test_a_negated_rational_literal_needs_a_positive_numerator():
    assert _value("-(1/2)") == Fraction(-1, 2)
    assert _value("-(-1/2)") == "-(-1/2)"
    assert _value("- (-1/2)") == "- (-1/2)"
    assert _value("-(-1 rdiv 2)") == "-(-1 rdiv 2)"
    assert not same_solution_sets(_binding("-(-1/2)"), _binding("1/2"))[0]


def test_a_huge_exponent_is_refused():
    with pytest.raises(ValueError):
        _equal("Y=X^9^9^9", "Y=X")
    with pytest.raises(ValueError):
        _equal("Y=X^10001", "Y=X")
    with pytest.raises(ValueError):
        _equal("Y=X^ -10001", "Y=X")
    assert _constant("2^14") == 16384
