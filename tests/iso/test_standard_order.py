"""Standard order of terms: the key itself, at the Python level.

Oracle rows for the PREDICATES live in test_standard_order_scryer.py. These
test `_standard_order_key` directly, so they need no Scryer binary and cannot
be silently retired by its absence.

Spec: docs/superpowers/specs/2026-09-09-standard-order-of-terms-design.md
"""
from decimal import Decimal
from fractions import Fraction

from clausal.logic.builtins._helpers import _standard_order_key as K
from clausal.logic.variables import Var
from clausal.terms import Quantity


def _lt(a, b):
    return K(a) < K(b)


# --- the ISO rules, verified against Scryer 2026-09-09 ----------------------

def test_the_six_iso_ordering_rules():
    """All six measured against Scryer on 2026-09-09 and agreeing. The
    number-band change must not move any ISO term relative to another ISO
    term (spec §2), so these are the guard on that."""
    assert _lt(Var(), 1)                    # var before number
    assert _lt(1, ("a",))                   # number before atom
    assert _lt(("a",), ("f", 1))            # atom before compound
    assert _lt(("g", 1), ("f", 1, 2))       # arity before name
    assert _lt(("f", 1), ("f", 2))          # args left to right
    assert _lt([], ("a",))                  # [] is an atom


# --- the ISO float/int tiebreak --------------------------------------------

def test_iso_float_precedes_int_of_equal_value():
    """ISO 7.2.1. Scryer: `compare(O, 1, 1.0)` gives `>`, and
    `sort([1, 1.0], L)` gives `[1.0, 1]` with BOTH kept."""
    assert _lt(1.0, 1)
    assert not _lt(1, 1.0)


def test_equal_value_numbers_of_different_types_are_distinct_terms():
    """Follows Task 1: `'=='` distinguishes them, so the order must too, or
    `compare(=, X, Y) <=> X == Y` fails."""
    for a, b in [(1.0, 1), (Decimal(1), 1), (Fraction(1), 1), (True, 1)]:
        assert K(a) != K(b), (a, b)


# --- Quantity ---------------------------------------------------------------

def test_quantity_is_in_the_number_band_not_the_opaque_band():
    assert K(Quantity(5, {"m": 1}))[0] == K(1)[0]


def test_dimensionless_quantity_sorts_beside_its_plain_twin_not_equal_to_it():
    """`'=='(Quantity(5000, {}), 5000)` is false (measured), so `compare/3`
    must not answer `=` — but under strict_units every number is a Quantity,
    so it must still sort AMONG the numbers rather than after every compound."""
    q = Quantity(5000, {})
    assert K(q) != K(5000)
    assert _lt(4999, q) and _lt(q, 5001)


def test_quantities_group_by_dimension_then_by_value():
    kg2 = Quantity(2, {"kg": 1})
    m3 = Quantity(3, {"m": 1})
    m5 = Quantity(5, {"m": 1})
    assert _lt(kg2, m3) and _lt(m3, m5)


def test_cross_dimension_comparison_never_raises():
    """The opaque band fell back to `repr` here and `Quantity.__lt__` raises
    across dimensions. The dimension signature makes it total instead."""
    assert _lt(Quantity(1, {"m": 1}), Quantity(1, {"s": 1})) in (True, False)


def test_a_quantity_still_sorts_before_atoms_and_compounds():
    assert _lt(Quantity(5, {"m": 1}), ("a",))
    assert _lt(Quantity(5, {"m": 1}), ("f", 1))
