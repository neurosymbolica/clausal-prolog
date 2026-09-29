"""A Python datetime in a goal must say what to write instead.

RULED 2026-09-15 (option b): the seam stays strict -- a Python datetime is not
a term and is refused -- and callers pass the term they already hold.
Measured across the downstream callers: of their date() constructions,
ZERO came from a clock, a parse, or arithmetic on external input.
Every one is built from components the body has in hand, so nothing is lost by
requiring the term.

This message is what downstream domains will meet while making that edit, so it has to
name the fix rather than the fault.
"""
import datetime

import pytest

from clausal.logic.compiler.terms_to_ast import term_to_ast_expr


def _msg(value):
    with pytest.raises(NotImplementedError) as exc:
        term_to_ast_expr(value, {})
    return str(exc.value)


def test_a_date_error_shows_the_term_to_write():
    m = _msg(datetime.date(2023, 6, 1))
    assert "('date', 2023, 6, 1)" in m, m


def test_a_datetime_error_shows_the_term_to_write():
    m = _msg(datetime.datetime(2023, 6, 1, 14, 30))
    assert "('datetime', 2023, 6, 1, 14, 30, 0, 0)" in m, m


def test_a_timedelta_error_shows_the_term_to_write():
    m = _msg(datetime.timedelta(days=3))
    assert "('timedelta', 3, 0, 0)" in m, m


def test_an_aware_datetime_shows_its_offset_component():
    m = _msg(datetime.datetime(2023, 6, 1, tzinfo=datetime.timezone.utc))
    assert "('datetime', 2023, 6, 1, 0, 0, 0, 0, 0)" in m, m


def test_the_message_says_a_datetime_is_not_a_term():
    m = _msg(datetime.date(2023, 6, 1))
    assert "not a term" in m, m


def test_an_opaque_object_still_gets_the_plain_refusal():
    """Only values with a canonical term encoding get a suggestion. An opaque
    object has none, which is the distinction the ruling turns on."""
    class Opaque:
        pass
    m = _msg(Opaque())
    assert "not a term" not in m or "Opaque" in m
    assert "('date'" not in m
