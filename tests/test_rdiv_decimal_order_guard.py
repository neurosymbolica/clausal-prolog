"""The ordering GUARD for the two exact-number cells (design 2026-09-17 §2 C).

A ``('decimal', M, S)`` or ``('rdiv', N, D)`` cell is the TRANSFER form of a
Decimal or a Fraction (RULED Q1, 2026-09-17).  It should never survive as a
compound inside the engine, but if one leaks it must still order as the NUMBER
it denotes: the defect this guards against was silent -- ``msort/2`` returned
``[9.9, 1.000]`` for two decimal cells because their mantissas ordered that
way, and a threshold test built on it reverses without raising
(todo/decimal-term-form-orders-as-a-term-in-compare-and-msort-2026-09-16.md).

Also pins RULED Q2: two decimals of equal value and different scale are
DISTINCT terms -- ``compare/3`` orders them by value then scale and ``'=='``
says they differ -- and the by-construction identity ``compare(=, X, Y) <=>
X == Y`` survives that, because the order key and ``_numeric_tag`` agree.
"""
from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.builtins._helpers import (
    _ORD_ATOM, _ORD_COMPOUND, _ORD_NUM, _standard_order_key as key,
)
from clausal.logic.builtins.iso_compare import _iso_identical
from clausal.logic.cells import chars
from clausal.logic.builtins.lists import _msort__2, _sort__2
from clausal.logic.trampoline import DONE
from clausal.logic.variables import Var, Trail, deref, exact_cell_number

D99, D1000 = ("decimal", 99, 1), ("decimal", 1000, 3)      # 9.9 and 1.000
R12, R13 = ("rdiv", 1, 2), ("rdiv", 1, 3)


def _drive(fn, items):
    """Drive a list builtin the way tests/test_standard_order.py does."""
    trail = Trail()
    out = Var()
    results = []
    for _cont, val in fn(None, "proceed", "fail", None, items, out, trail):
        if val is DONE:
            break
        results.append([deref(x) for x in deref(out)])
    assert len(results) == 1, f"expected one solution, got {results!r}"
    return results[0]


def _msort(items):
    return _drive(_msort__2, items)


def _sort(items):
    return _drive(_sort__2, items)


# ── the defect, closed ────────────────────────────────────────────────────

def test_decimal_cells_msort_by_value_not_by_mantissa():
    assert _msort([D99, D1000]) == [D1000, D99]        # 1.000 < 9.9


def test_rdiv_cells_msort_by_value_not_by_denominator():
    assert _msort([R12, R13]) == [R13, R12]            # 1/3 < 1/2


def test_cells_key_in_the_number_band():
    for cell in (D99, D1000, R12, R13):
        assert key(cell)[0] == _ORD_NUM


def test_cells_sort_among_numbers_not_after_atoms_and_compounds():
    out = _msort(["a", D99, ("f", 1), 20, R12, 5])
    assert out == [R12, 5, D99, 20, "a", ("f", 1)]


# ── identity: compare(=, X, Y) <=> X == Y, by construction ────────────────

def test_a_cell_and_its_object_are_different_terms_that_sort_adjacent():
    obj = Decimal("9.9")
    assert not _iso_identical(D99, obj)
    assert key(D99) != key(obj)
    assert _msort([D99, obj]) == [obj, D99]           # value equal: object first
    assert not _iso_identical(R12, Fraction(1, 2))
    assert _msort([R12, Fraction(1, 2)]) == [Fraction(1, 2), R12]


def test_RULED_Q2_equal_value_different_scale_are_distinct_terms():
    a, b = Decimal("1.0"), Decimal("1.00")
    assert not _iso_identical(a, b)                    # '==' says no
    assert key(a) != key(b) and key(a) < key(b)        # value, then scale
    # Compare SPELLINGS: Python's list ``==`` calls 1.0 and 1.00 equal, so an
    # assertion on the lists themselves cannot see the order (found by the
    # mutation control: Decimal back in the native fast path failed nothing).
    assert [str(x) for x in _msort([b, a])] == ["1.0", "1.00"]
    # sort/2 dedups by the KEY, so the two scales both survive, in order
    assert [str(x) for x in _sort([b, a, a])] == ["1.0", "1.00"]
    # the cells agree with the objects
    ca, cb = ("decimal", 10, 1), ("decimal", 100, 2)
    assert not _iso_identical(ca, cb)
    assert _msort([cb, ca]) == [ca, cb]


def test_equal_value_and_scale_ARE_identical():
    assert _iso_identical(Decimal("1.0"), Decimal("1.0"))
    assert key(Decimal("1.0")) == key(Decimal("1.0"))
    assert _iso_identical(("decimal", 10, 1), ("decimal", 10, 1))


# ── only a CANONICAL cell is a number; a look-alike stays a compound ──────

@pytest.mark.parametrize("cell", [
    ("rdiv", 2, 4),          # not in lowest terms
    ("rdiv", 3, 1),          # D must be > 1 (an integral rational is an int)
    ("rdiv", 1, 0),          # no denominator
    ("rdiv", 1, -2),         # sign belongs on the numerator
    ("decimal", 100, 0),     # S must be > 0 (a scale-less decimal is an int)
    ("decimal", 1, -5),      # negative scale
    ("decimal", chars("9"), 1),     # not ints
    ("decimal", True, 1),    # bool is not an int here
    ("rdiv", 1, 2, 3),       # wrong arity
])
def test_a_look_alike_is_not_a_number(cell):
    assert exact_cell_number(cell) is None
    assert key(cell)[0] == _ORD_COMPOUND


def test_exact_cell_number_values():
    assert exact_cell_number(D99) == Decimal("9.9")
    assert exact_cell_number(D1000) == Decimal("1.000")
    assert exact_cell_number(("decimal", -1001, 2)) == Decimal("-10.01")
    assert exact_cell_number(R13) == Fraction(1, 3)
    assert exact_cell_number(("rdiv", -1, 3)) == Fraction(-1, 3)
    assert exact_cell_number(5) is None and exact_cell_number(("a",)) is None


# ── the evaluator: an rdiv leaf evaluates; a decimal leaf stays LOUD ──────

def test_rdiv_cell_evaluates_as_its_fraction():
    from clausal.logic.clpfd import _eval_ground
    assert _eval_ground(R13) == Fraction(1, 3)


def test_decimal_cell_evaluates_as_its_decimal_since_step_2():
    """The guard pinned this as LOUD (raises, not evaluates) until step 2 of
    the design accepted a Decimal leaf; step 2 landed the same day, so the
    cell and the object now evaluate to the SAME number.  The loud pin moved
    to the non-finite case (tests/test_decimal_arithmetic.py)."""
    from clausal.logic.clpfd import _eval_ground
    assert _eval_ground(D99) == Decimal("9.9")
    assert _eval_ground(Decimal("9.9")) == Decimal("9.9")


def test_a_non_canonical_rdiv_cell_evaluates_as_rdiv():
    """Ruling Q15 (2026-09-28): rdiv/2 is the exact-rational spelling and is
    evaluable, as in Scryer (``2 rdiv 4`` is 1 rdiv 2) -- a non-canonical
    rdiv cell was refused before.  A non-number operand is still refused."""
    from fractions import Fraction
    from clausal.logic.clpfd import _eval_ground
    from clausal.logic.exceptions import LogicException
    assert _eval_ground(("rdiv", 2, 4)) == Fraction(1, 2)
    with pytest.raises(LogicException):
        _eval_ground(("rdiv", "a", 4))
