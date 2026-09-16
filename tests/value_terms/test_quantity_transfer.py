"""The TRANSFER form: for boundaries that cannot carry an object.

Spec: docs/superpowers/specs/2026-09-16-quantity-transfer-form-design.md.
The transfer layer sits BESIDE the seam registry. A same-interpreter seam
passes the object (ruled 2026-09-15); only a subinterpreter, a process
boundary or a bytecode cache needs the term. So ``to_term``/``from_term``
must keep passing a Quantity through, and ``to_transfer``/``from_transfer``
must not.
"""
import datetime
import marshal
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.python_terms import (
    FROM_TERM, FROM_TRANSFER, TO_TERM, TO_TRANSFER,
    from_term, from_transfer, register_transfer, to_term, to_transfer,
)


# ── the layer itself ─────────────────────────────────────────────────────────

def test_the_transfer_tables_are_separate_from_the_seam_tables():
    assert TO_TRANSFER is not TO_TERM
    assert FROM_TRANSFER is not FROM_TERM
    assert Fraction in TO_TRANSFER and Fraction not in TO_TERM
    assert "rdiv" in FROM_TRANSFER and "rdiv" not in FROM_TERM


def test_to_transfer_falls_through_to_the_seam_registry_for_a_decimal():
    assert to_transfer(Decimal("10.01")) == ("decimal", 1001, 2)


def test_to_transfer_falls_through_for_a_date_and_a_scalar():
    assert to_transfer(datetime.date(2026, 9, 16)) == ("date", 2026, 9, 16)
    assert to_transfer(7) == 7


def test_to_transfer_REFUSES_a_logic_variable():
    from clausal.logic.variables import Var
    with pytest.raises(TypeError, match="logic variable"):
        to_transfer(Var())


def test_to_transfer_is_strict_about_an_unregistered_class():
    class Nope:
        pass
    with pytest.raises(TypeError, match="no registered conversion"):
        to_transfer(Nope())


def test_to_transfer_recurses_through_a_list_a_dict_and_a_data_tuple():
    assert to_transfer([Fraction(1, 2)]) == [("rdiv", 1, 2)]
    assert to_transfer({"k": Fraction(1, 2)}) == {"k": ("rdiv", 1, 2)}
    assert to_transfer((Fraction(1, 2), 3)) == ("()", ("rdiv", 1, 2), 3)


def test_from_transfer_recurses_the_same_way():
    assert from_transfer([("rdiv", 1, 2)]) == [Fraction(1, 2)]
    assert from_transfer({"k": ("rdiv", 1, 2)}) == {"k": Fraction(1, 2)}
    assert from_transfer(("()", ("rdiv", 1, 2), 3)) == (Fraction(1, 2), 3)


def test_from_transfer_falls_through_to_the_seam_registry():
    assert from_transfer(("decimal", 1001, 2)) == Decimal("10.01")
    assert from_transfer(("date", 2026, 9, 16)) == datetime.date(2026, 9, 16)


def test_from_transfer_leaves_an_unregistered_functor_UNCHANGED():
    t = ("cite", ("art52",))
    assert from_transfer(t) is t


def test_registering_a_transfer_type_twice_is_REFUSED():
    with pytest.raises(ValueError, match="already"):
        register_transfer(Fraction, "rdiv2", lambda v: v, lambda t: t)


def test_registering_a_transfer_functor_twice_is_refused_too():
    class Fresh:
        pass
    with pytest.raises(ValueError, match="already"):
        register_transfer(Fresh, "rdiv", lambda v: v, lambda t: t)


def test_a_transfer_entry_may_not_shadow_a_seam_entry():
    class Fresh2:
        pass
    with pytest.raises(ValueError, match="already"):
        register_transfer(Decimal, "decimal2", lambda v: v, lambda t: t)
    with pytest.raises(ValueError, match="already"):
        register_transfer(Fresh2, "decimal", lambda v: v, lambda t: t)


# ── Fraction <-> rdiv/2 ───────────────────────────────────────────────────────

def test_a_fraction_becomes_rdiv_with_the_sign_on_the_numerator():
    assert to_transfer(Fraction(-10, 3)) == ("rdiv", -10, 3)


def test_rdiv_comes_back_as_the_same_fraction():
    assert from_transfer(("rdiv", -10, 3)) == Fraction(-10, 3)


def test_an_rdiv_that_is_not_in_lowest_terms_or_has_a_bad_denominator_is_unchanged():
    # from_transfer's policy is from_term's: a look-alike is not a term
    for t in (("rdiv", 2, 4), ("rdiv", 1, 1), ("rdiv", 1, 0), ("rdiv", 1, -3),
              ("rdiv", "1", 3), ("rdiv", 1), ("rdiv", 1.5, 2), ("rdiv", True, 2)):
        assert from_transfer(t) is t, t


def test_an_rdiv_term_is_marshal_clean():
    t = to_transfer(Fraction(-10, 3))
    assert marshal.loads(marshal.dumps(t)) == t


def test_an_INTEGRAL_fraction_emits_as_an_int_so_D_gt_1_is_an_invariant():
    # the engine's own rule: an integral rational presents as an int, and the
    # read side's D > 1 guard would otherwise reject what the emit side wrote
    f = Fraction(1, 3) + Fraction(2, 3)
    assert f == 1 and type(f) is Fraction
    assert to_transfer(f) == 1 and type(to_transfer(f)) is int
    assert from_transfer(to_transfer(f)) == 1


# ── the seam is UNCHANGED for a Fraction ─────────────────────────────────────

def test_the_seam_still_passes_a_fraction_through_on_the_implicit_path():
    f = Fraction(1, 3)
    assert to_term(f, strict=False) is f


def test_the_seam_still_refuses_a_fraction_on_the_strict_path():
    with pytest.raises(TypeError, match="no registered conversion"):
        to_term(Fraction(1, 3), strict=True)


def test_the_seam_leaves_an_rdiv_term_alone():
    t = ("rdiv", 1, 3)
    assert from_term(t) is t


# ── Quantity -> term (EMIT) ───────────────────────────────────────────────────

from clausal.logic.python_terms import _dims_from_term, _dims_to_term  # noqa: E402
from clausal.modules import units  # noqa: E402
from clausal.modules.countries import european_union as eu  # noqa: E402
from clausal.terms import Quantity  # noqa: E402


def test_the_dims_slot_helper_emits_dimensionless_for_an_empty_map():
    assert _dims_to_term({}) == ("dimensionless",)


def test_the_dims_slot_helper_SORTS_on_emit():
    assert _dims_to_term({"second": -2, "metre": 1}) == \
        ("dimensions", ("metre", 1), ("second", -2))


def test_five_kilometre_emits_as_5000_metre_with_ratio_ONE():
    # The object has no ratio slot: the ratio is always 1 on emit (spec §3).
    q = Quantity(5, units.kilometre)
    assert to_transfer(q) == \
        ("quantity", 5000, ("unit", 1, ("dimensions", ("metre", 1))))


def test_money_emits_its_decimal_magnitude_WITH_its_scale():
    q = Quantity(Decimal("1550.00"), eu.euro)
    assert to_transfer(q) == \
        ("quantity", ("decimal", 155000, 2), ("unit", 1, ("dimensions", ("euro", 1))))


def test_three_percent_emits_as_a_dimensionless_decimal():
    q = Quantity(3, units.percent)
    assert to_transfer(q) == \
        ("quantity", ("decimal", 3, 2), ("unit", 1, ("dimensionless",)))


def test_a_divided_value_emits_an_rdiv_magnitude():
    q = Quantity(Fraction(10, 3), units.metre)
    assert to_transfer(q) == \
        ("quantity", ("rdiv", 10, 3), ("unit", 1, ("dimensions", ("metre", 1))))


def test_a_two_dimension_quantity_emits_its_dims_sorted():
    q = Quantity(1, units.metre) * Quantity(1, units.second)
    assert to_transfer(q) == \
        ("quantity", 1, ("unit", 1, ("dimensions", ("metre", 1), ("second", 1))))


def test_a_quantity_inside_a_list_converts_too():
    q = Quantity(5, units.kilometre)
    assert to_transfer([q]) == \
        [("quantity", 5000, ("unit", 1, ("dimensions", ("metre", 1))))]


def test_every_emitted_transfer_term_is_marshal_clean_and_the_object_is_NOT():
    qs = [Quantity(5, units.kilometre), Quantity(Decimal("1550.00"), eu.euro),
          Quantity(3, units.percent), Quantity(Fraction(10, 3), units.metre),
          Quantity(1, units.metre) * Quantity(1, units.second)]
    for q in qs:
        t = to_transfer(q)
        assert marshal.loads(marshal.dumps(t)) == t, t
    with pytest.raises(ValueError):          # positive control
        marshal.dumps(qs[0])


# ── the seam is UNCHANGED for a Quantity ─────────────────────────────────────

def test_the_seam_still_passes_a_quantity_through_as_ITSELF():
    q = Quantity(5, units.kilometre)
    assert to_term(q, strict=True) is q
    assert to_term(q, strict=False) is q
    assert Quantity not in TO_TERM


# ── term -> Quantity (READ) ───────────────────────────────────────────────────

def test_an_emitted_term_reads_back_to_an_EQUAL_object():
    for q in (Quantity(5, units.kilometre), Quantity(Decimal("1550.00"), eu.euro),
              Quantity(3, units.percent), Quantity(Fraction(10, 3), units.metre),
              Quantity(1, units.metre) * Quantity(1, units.second)):
        back = from_transfer(to_transfer(q))
        assert isinstance(back, Quantity)
        assert back == q, q
        assert hash(back) == hash(q)


def test_an_AUTHORED_ratio_is_multiplied_through_on_read():
    # written by an author: 5 in a unit whose ratio to the standard unit is 1000
    t = ("quantity", 5, ("unit", 1000, ("dimensions", ("metre", 1))))
    assert from_transfer(t) == Quantity(5, units.kilometre)


def test_a_decimal_ratio_stays_EXACT_on_read():
    # 3 percent, written with the ratio rather than pre-scaled
    t = ("quantity", 3, ("unit", ("decimal", 1, 2), ("dimensionless",)))
    q = from_transfer(t)
    assert q == Quantity(3, units.percent)
    assert isinstance(q.value, Decimal) and q.value == Decimal("0.03")


def test_an_rdiv_ratio_and_an_rdiv_magnitude_compose_exactly():
    t = ("quantity", ("rdiv", 1, 3), ("unit", ("rdiv", 1, 2), ("dimensions", ("metre", 1))))
    q = from_transfer(t)
    assert q.value == Fraction(1, 6) and isinstance(q.value, Fraction)


def test_read_is_ORDER_INSENSITIVE_in_the_dims_slot():
    sorted_t = ("quantity", 1, ("unit", 1, ("dimensions", ("metre", 1), ("second", 1))))
    unsorted = ("quantity", 1, ("unit", 1, ("dimensions", ("second", 1), ("metre", 1))))
    assert from_transfer(unsorted) == from_transfer(sorted_t)


def test_a_dimensionless_term_reads_to_an_empty_dims_map():
    q = from_transfer(("quantity", 4, ("unit", 1, ("dimensionless",))))
    assert isinstance(q, Quantity) and dict(q.dims) == {} and q.value == 4


def test_a_MALFORMED_quantity_term_comes_back_unchanged():
    bad = [
        ("quantity", 5),                                              # arity
        ("quantity", 5, ("unit", 1)),                                 # unit arity
        ("quantity", 5, ("units", 1, ("dimensionless",))),            # wrong functor
        ("quantity", 5, ("unit", 1, ("dimensions",))),                # empty dimensions/N
        ("quantity", 5, ("unit", 1, ("dimensions", ("metre", 0)))),   # zero exponent
        ("quantity", 5, ("unit", 1, ("dimensions", ("metre", 1), ("metre", 2)))),  # dup
        ("quantity", "5", ("unit", 1, ("dimensionless",))),           # magnitude not a number
        ("quantity", 5, ("unit", "1", ("dimensionless",))),           # ratio not a number
        ("quantity", True, ("unit", 1, ("dimensionless",))),          # bool is not a number
        ("quantity", 5, ("unit", 1, ("dimensions", ("metre", "1")))), # exponent not int
    ]
    for t in bad:
        assert from_transfer(t) is t, t


def test_the_seam_leaves_a_quantity_term_ALONE():
    t = ("quantity", 5000, ("unit", 1, ("dimensions", ("metre", 1))))
    assert from_term(t) is t
    assert "quantity" not in FROM_TERM
