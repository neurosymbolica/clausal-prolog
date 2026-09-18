"""Standard order of terms: the key itself, at the Python level.

Oracle rows for the PREDICATES live in test_standard_order_scryer.py. These
test `_standard_order_key` directly, so they need no Scryer binary and cannot
be silently retired by its absence.

Spec: docs/superpowers/specs/2026-09-09-standard-order-of-terms-design.md
"""
from decimal import Decimal
from fractions import Fraction

from clausal.logic.builtins._helpers import _standard_order_key as K
from clausal.logic.cells import chars
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
    assert _lt(1, "a")                   # number before atom
    assert _lt("a", ("f", 1))            # atom before compound
    assert _lt(("g", 1), ("f", 1, 2))       # arity before name
    assert _lt(("f", 1), ("f", 2))          # args left to right
    assert _lt([], "a")                  # [] is an atom


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
    assert _lt(Quantity(5, {"m": 1}), "a")
    assert _lt(Quantity(5, {"m": 1}), ("f", 1))


# --- the sort/2 fast path (spec §5) ----------------------------------------

from clausal.logic.builtins._helpers import _standard_order_sorted as S


def test_sort_is_not_input_order_dependent():
    """Measured BEFORE the fix: `S([1, 1.0])` -> `[1, 1.0]` and
    `S([1.0, 1])` -> `[1.0, 1]`. The same multiset sorted to two different
    answers, so sort/2 had no stable opinion about equal-value int/float and
    no tiebreak could be implemented while that path survived.

    Compared by TYPE, not by value: `[1, 1.0] == [1.0, 1]` is True in Python
    because `1 == 1.0`, so a plain list comparison here cannot fail for the
    reason this test exists. The first draft of this test did exactly that and
    passed while the bug was live."""
    def shape(xs):
        return [(type(x).__name__, x) for x in xs]
    assert shape(S([1, 1.0])) == shape(S([1.0, 1]))
    assert shape(S([1, 1.0])) == [("float", 1.0), ("int", 1)]


def test_same_type_is_not_a_sufficient_guard_for_the_native_path():
    """All tuples, one Python type — but cells key ARITY-FIRST (ISO 7.2.1)
    while Python compares tuples elementwise. Measured 2026-09-09:
    native gives [f/2, g/1], the key gives [g/1, f/2]. This is why the guard
    is a membership test and not a homogeneity test."""
    assert S([("f", 1, 2), ("g", 1)]) == [("g", 1), ("f", 1, 2)]


def test_sorting_across_dimensions_does_not_raise():
    """`Quantity.__lt__` raises `UnitsMismatch`, which is NOT a `TypeError`,
    so the old `except TypeError` never fired and the exception ESCAPED:
    sort/2 CRASHED on any list mixing dimensions or mixing quantities with
    plain numbers. The key handles all of them."""
    assert S([Quantity(5, {"m": 1}), Quantity(2, {"kg": 1})]) == [
        Quantity(2, {"kg": 1}), Quantity(5, {"m": 1})]
    assert S([3, Quantity(5, {"m": 1}), 4]) == [3, 4, Quantity(5, {"m": 1})]


def test_homogeneous_safe_types_still_take_the_native_path():
    assert S([3, 1, 2]) == [1, 2, 3]
    assert S(["b", "ab", "a"]) == ["a", "ab", "b"]
    assert S([b"b", b"ab"]) == [b"ab", b"b"]


def test_an_empty_list_sorts_without_reaching_the_membership_test():
    assert S([]) == []


# --- the ISO identity (spec §7 item 2) --------------------------------------

def test_compare_equals_iff_iso_identical():
    """ISO guarantees `compare(=, X, Y)` holds exactly when `X == Y`.

    This is the PRIMARY instrument for this work: it is what makes the
    ordering and the identity one design rather than two that happen to agree
    today. It is what the `1`/`1.0` contradiction would have failed —
    `'=='` said different while the order said equal — and what forced the
    transitivity fix in Task 1, since order-equality is necessarily transitive
    and `'=='` was not.
    """
    from clausal.logic.builtins.iso_compare import _iso_identical, _order_atom

    terms = [1, 1.0, True, Decimal(1), Fraction(1),
             Quantity(1, {}), Quantity(1, {"m": 1}), Quantity(2, {"m": 1}),
             2, 2.0, "a", "b", ("f", 1), ("f", 1, 2), ("g", 1),
             [], [1], [1, 2], chars("ab"), b"ab"]
    for a in terms:
        for b in terms:
            assert (_order_atom(a, b) == "=") == bool(_iso_identical(a, b)), (
                f"compare says {_order_atom(a, b)!r} but '==' says "
                f"{_iso_identical(a, b)!r} for {a!r} and {b!r}")


def test_the_order_is_total_over_every_pair():
    """No pair may raise, and exactly one of <, =, > must hold each way."""
    from clausal.logic.builtins.iso_compare import _order_atom

    terms = [Var(), 1, 1.0, Decimal(1), Quantity(1, {"m": 1}), Quantity(1, {"s": 1}),
             "a", ("f", 1), [], [1], chars("ab"), b"ab", {chars("a"): 1}, {1, 2}]
    for a in terms:
        for b in terms:
            ab, ba = _order_atom(a, b), _order_atom(b, a)
            assert ab in ("<", "=", ">")
            assert (ab == "=") == (ba == "="), (a, b, ab, ba)
            if ab != "=":
                assert ab != ba, (a, b, ab, ba)
