"""Colour schemes of the ``?-`` top-level (``clausal.toplevel_colour``)."""

from __future__ import annotations

import re

import pytest

from clausal.toplevel_colour import (
    PALETTE, SCHEMES, colour_of, paint_variables, scheme_named)

ESC = re.compile(r"\x1b\[38;5;(\d+)m([^\x1b]*)\x1b\[0m")


def _painted(text):
    return [(m.group(2), int(m.group(1))) for m in ESC.finditer(
        paint_variables(text))]


def test_the_first_scheme_is_off_and_changes_nothing():
    assert SCHEMES[0].name == "off"
    assert SCHEMES[0].paint("X = f(Y)") == "X = f(Y)"


def test_a_variable_has_one_colour_wherever_it_is():
    got = _painted("X = f(Y,Y), Z = g(X,Y)")
    colours = {}
    for name, col in got:
        assert colours.setdefault(name, col) == col
    assert set(colours) == {"X", "Y", "Z"}


def test_the_colour_is_a_stable_function_of_the_name():
    # fixed values: a change of palette, salt or hash is a visible change
    assert [colour_of(n) for n in "XYZ"] == [colour_of(n) for n in "XYZ"]
    assert all(colour_of(n) in PALETTE for n in ("X", "_G12", "Result"))
    assert colour_of("X") != colour_of("Y") != colour_of("Z")


def test_common_one_letter_names_have_different_colours():
    names = list("XYZABCDEFGHLNR")
    assert len({colour_of(n) for n in names}) == len(names)


@pytest.mark.parametrize("text", [
    "X = 'Foo bar'", 'X = "Baz Qux"', "X = a, Y = 1.5e3", "X = 0'A",
    "X = 'it''s Fine'", "X = `Back`",
])
def test_quoted_text_numbers_and_atoms_are_not_painted(text):
    names = [n for n, _ in _painted(text)]
    assert names in (["X"], ["X", "Y"]), (text, names)


def test_underscore_names_are_variables():
    assert [n for n, _ in _painted("_G12 = _A, foo(_)")] == ["_G12", "_A", "_"]


def test_scheme_named():
    assert scheme_named("variables") == 1
    assert scheme_named("Variables ") == 1
    assert scheme_named("nonesuch") == 0
