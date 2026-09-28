"""A DCG list terminal ``[D]`` binds D to the ELEMENT, so a following
``{D >= 0}`` compares a number (regression pin: this raised
``type_error(evaluable, [5])`` once, the terminal handing the list itself to
the brace goal).  The pushback form reads the element the same way."""

from __future__ import annotations

import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref

_SRC = """\
-allow_singletons
digit(D) >> ([D], {D >= 0}, {D <= 9})
(peek(D), [D]) >> ([D], {D >= 0}, {D <= 9})
one(D) <- phrase(digit(D), [5])
big(D) <- phrase(digit(D), [12])
look(D, R) <- phrase(peek(D), [7, 8], R)
"""


@pytest.fixture(scope="module")
def mod():
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                     delete=False) as f:
        f.write(_SRC)
        path = f.name
    try:
        return _load_module("_dcg_terminal_binds_element", path)
    finally:
        os.unlink(path)


def _answers(mod, name, n=1):
    vs = [Var() for _ in range(n)]
    return [tuple(deref(v) for v in vs) for _ in solve((name, *vs), mod)]


def test_terminal_binds_the_element(mod):
    assert _answers(mod, "one") == [(5,)]


def test_out_of_range_element_fails(mod):
    assert _answers(mod, "big") == []


def test_pushback_binds_the_element_and_keeps_it(mod):
    assert _answers(mod, "look", 2) == [(7, [7, 8])]
