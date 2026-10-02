"""An unevaluated arithmetic term in a numeric position names `is` vs `==`.

`is/2` is unification: ``R is 5000 * 2`` binds ``R`` to the *term* ``Mult(5000,
2)``, and ``==`` is the evaluating operator.  That is deliberate, but `is` is
spelled like Prolog's arithmetic-evaluation operator, so authors carrying
Prolog habits write it and the unevaluated term surfaces far from its cause —
as ``type_error(number, FloorDiv(...))`` out of a numeric builtin, or as a
nearest-solution diff rendered ``(2500 + 0)``.

Both of those already hold the arithmetic node at the point of the message.
These tests pin that they say so.  See ``todo/done/`` for the request.
"""

from __future__ import annotations

import pytest

import textwrap

from clausal.logic.atoms import mint
from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException, type_error
from clausal.terms import Add, FloorDiv
from clausal.testing import main
from tests._suffix import SEAM


def write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


# The half-sentence both sites share.  Asserted rather than the whole note so a
# reworded subject clause does not break five tests at once.
IS_VS_EQ = "`is` unifies without evaluating"


# ── site 1: type_error(number, <arith node>) ─────────────────────────────────


def test_type_error_number_on_arith_term_names_the_operator():
    exc = LogicException(
        type_error(mint("number"), FloorDiv(left=10000, right=4), "sum_list/2"))
    msg = str(exc)
    assert "unevaluated arithmetic term" in msg
    assert IS_VS_EQ in msg
    # the surface form, because the repr in the line above is what confused
    # the reader in the first place
    assert "10000 // 4" in msg


def test_the_note_does_not_disturb_the_error_term():
    """The note is message-only: ``catch/3`` matches on ``.term``."""
    culprit = FloorDiv(left=10000, right=4)
    exc = LogicException(type_error("number", culprit, "sum_list/2"))
    assert cell_functor(exc.term) == "error"
    assert cell_args(exc.term)[0] == ("type_error", mint("number"), culprit)
    assert cell_args(exc.term)[1] == ("/", "sum_list", 2)


def test_type_error_number_on_a_non_arith_culprit_says_nothing():
    exc = LogicException(type_error("number", "abc", "sum_list/2"))
    assert IS_VS_EQ not in str(exc)


def test_type_error_on_a_non_numeric_expectation_says_nothing():
    """A term where an *atom* was wanted is not an is/== confusion."""
    exc = LogicException(
        type_error("atom", Add(left=1, right=2), "atom_length/2"))
    assert IS_VS_EQ not in str(exc)


def test_an_unhashable_expected_type_still_renders():
    """`str()` on an exception must not be able to raise. ``throw/1`` can put
    anything in the type slot, including something a set lookup would reject."""
    exc = LogicException(
        type_error(["not", "a", "type"], Add(left=1, right=2), "user/0"))
    assert "Uncaught logic exception" in str(exc)
    assert IS_VS_EQ not in str(exc)


SUM_LIST_SRC = """
-double_quotes(atom)
z(0),

test("term reaches a numeric builtin") <- (
    R is 10000 // 4,
    sum_list([R], S),
    S == 2500
),
"""


def test_note_reaches_the_test_report(capsys, tmp_path):
    p = write(tmp_path, f"suml{SEAM}", SUM_LIST_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "type_error" in out
    assert IS_VS_EQ in out


# ── site 2: nearest-solution diff is an arith node, the goal wanted a number ──

NEAREST_SRC = """
-double_quotes(atom)
eff(R) <- (
    R is 2500 + 0
),

test("effective value") <- (
    eff(2500)
),
"""


def test_nearest_solution_arith_term_names_the_operator(capsys, tmp_path):
    p = write(tmp_path, f"nearest{SEAM}", NEAREST_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "did not unify" in out
    assert IS_VS_EQ in out


MIRROR_SRC = """
-double_quotes(atom)
eff(2500),

test("caller wrote the expression") <- (
    eff(2500 + 0)
),
"""


def test_nearest_solution_names_it_when_the_caller_wrote_the_expression(
        capsys, tmp_path):
    """The mirror case: the goal's argument is the unevaluated term."""
    p = write(tmp_path, f"mirror{SEAM}", MIRROR_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert IS_VS_EQ in out


COMPOUND_SRC = """
-double_quotes(atom)
-private([verdict(A, B, C), beneficial_owner, not_beneficial_owner])

chain_assess("simple", verdict(beneficial_owner, 2500, [])),

test("ordinary near miss") <- (
    chain_assess("simple", verdict(not_beneficial_owner, _BPS, _CITES))
),
"""


def test_ordinary_near_miss_says_nothing_about_arithmetic(capsys, tmp_path):
    """A near miss on a compound must not be blamed on `is`."""
    p = write(tmp_path, f"plain{SEAM}", COMPOUND_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "did not unify" in out
    assert IS_VS_EQ not in out


NUMERIC_SRC = """
-double_quotes(atom)
eff(2500),

test("plain numeric near miss") <- (
    eff(2400)
),
"""


def test_number_vs_number_near_miss_says_nothing(capsys, tmp_path):
    p = write(tmp_path, f"num{SEAM}", NUMERIC_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "did not unify" in out
    assert IS_VS_EQ not in out


# ── the branches the two sites do not otherwise reach ────────────────────────


def test_site1_fires_for_an_integer_expectation_too():
    """``_NUMERIC_EXPECTATIONS`` holds `integer` as well as `number`.

    Only `number` is exercised above, so the `integer` half of the set was
    asserted nowhere and could have been dropped silently.
    """
    exc = LogicException(
        type_error(mint("integer"), FloorDiv(left=10000, right=4), "nth0/3"))
    msg = str(exc)
    assert "unevaluated arithmetic term" in msg
    assert IS_VS_EQ in msg


KEYWORD_SRC = """
-double_quotes(atom)
eff(R=RESULT) <- (
    RESULT is 2500 + 0
),

test("keyword argument") <- (
    eff(R=2500)
),
"""


def test_nearest_solution_note_fires_on_a_keyword_argument(capsys, tmp_path):
    """The kw branch of ``_report_nearest`` is UNREACHABLE FROM SOURCE.

    It reads ``kwargs[i].value``, a distinct branch from the positional one,
    and a wrong index there would compare the wrong pair silently — which is
    why it was pinned.  Since 2026-09-19 a term is built positionally and the
    source that reached that branch does not load, so what can be pinned is
    the refusal.  The branch itself still exists and goes with the keyword
    machinery in P4; if that removal leaves it behind, this test is the
    reminder that nothing reaches it.
    """
    p = write(tmp_path, f"kwarg{SEAM}", KEYWORD_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "keyword arguments" in out and "eff/1" in out


def test_a_boolean_opposite_an_arith_term_does_not_fire():
    """``_is_number`` excludes `bool`: `True` is not 1 for this note.

    Pairing a boolean with an operator term is not the is/== confusion, and a
    note there would be claiming something false about the author's intent.
    """
    from clausal.testing import _arith_vs_number_note

    assert _arith_vs_number_note(
        "argument 1", Add(left=1, right=1), True) is None
    assert _arith_vs_number_note(
        "argument 1", True, Add(left=1, right=1)) is None
    # ...while a real number on either side still does fire.
    assert _arith_vs_number_note(
        "argument 1", Add(left=1, right=1), 2) is not None
    assert _arith_vs_number_note(
        "argument 1", 2, Add(left=1, right=1)) is not None
