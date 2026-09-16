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
