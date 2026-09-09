"""The numeric-type unify census (``unify_census_start/stop/unify_census``).

The census counts unifications that SUCCEEDED between two numbers of
different Python types — the population a type-strict ``unify`` would start
rejecting. It is a measuring instrument, so every test here starts with a
positive control: ``unify(1, 1.0)`` must count exactly one, or the instrument
is dark and the rest of the test proves nothing.

The C extension must be REBUILT for these tests (``python setup.py build_ext
--inplace``): the unordered key is in ``_variables.c``. Against a stale build
``unify(1.0, 1)`` is keyed ``float/int`` and the two order-insensitivity tests
fail — that is the stale ``.so`` talking, not the engine.
"""
from fractions import Fraction

import pytest

from clausal.logic.variables import Trail, unify
from clausal.logic.variables._variables import (
    unify_census, unify_census_start, unify_census_stop,
)


@pytest.fixture
def census():
    unify_census_start()
    try:
        yield
    finally:
        unify_census_stop()


def _by_type():
    report = unify_census()
    return {k: v for k, v in report["by_type_pair"].items()}


def test_positive_control_int_float_counts_one(census):
    assert unify(1, 1.0, Trail())
    report = unify_census()
    assert report["conflations"] == 1, report
    assert _by_type() == {"int/float": 1}, report


def test_same_type_pairs_are_not_counted(census):
    t = Trail()
    assert unify(1, 1, t)
    assert unify(Fraction(1, 2), Fraction(1, 2), t)
    assert unify_census()["conflations"] == 0


def test_key_is_order_insensitive(census):
    """``unify(2, Fraction(2, 1))`` and ``unify(Fraction(2, 1), 2)`` are ONE
    phenomenon; a total over the report must sum them under one key."""
    t = Trail()
    assert unify(2, Fraction(2, 1), t)
    assert unify(Fraction(2, 1), 2, t)
    by_type = _by_type()
    assert unify_census()["conflations"] == 2
    assert len(by_type) == 1, by_type
    (key, n), = by_type.items()
    assert n == 2, by_type
    assert set(key.split("/")) == {"int", "Fraction"}, key


def test_int_float_key_is_the_same_both_ways(census):
    t = Trail()
    assert unify(1.0, 1, t)
    assert unify(1, 1.0, t)
    assert _by_type() == {"int/float": 2}, _by_type()
