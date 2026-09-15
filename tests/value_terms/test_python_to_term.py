"""Recursively convert a Python object into functor-first-tuple form.

Design (operator, 2026-09-15): take the class name prefixed with its module,
take the match args, convert them recursively, and emit
``('{module}\\x1f{class}', arg0, ..., argN)``. Scalars pass through. A tuple
becomes the ``('()', ...)`` data form.

TWO THINGS THE DESIGN MEETS ON CONTACT WITH THE TREE, both measured:

* ``HIDDEN_SEP`` is already ``"\\x1f"`` in ``logic/atoms.py``, with a ``mangle``
  that already spells ``f"{module}{HIDDEN_SEP}{name}"``. One definition, reused.
* ``__match_args__`` is ABSENT on the types that matter most -- ``datetime.date``
  and ``Decimal`` both report ``None``. So a purely generic converter fails on
  exactly the values that prompted this, and a REGISTRY of canonical shapes has
  to come first.

The registry winning is not a detail: a generic mangle would give a date
``('datetime\\x1fdate', 2023, 6, 1)`` while 94 corpus rulebases expect
``('date', 2023, 6, 1)``. Two encodings for one value is the thing this whole
representation change exists to remove.
"""
import datetime
from decimal import Decimal

import pytest

from clausal.logic.atoms import HIDDEN_SEP
from clausal.logic.python_terms import to_term


class Point:
    __match_args__ = ("x", "y")

    def __init__(self, x, y):
        self.x, self.y = x, y


# ── scalars pass through untouched ───────────────────────────────────────────

@pytest.mark.parametrize("v", [1, -3, 0, 1.5, "text", b"bytes", True, False, None])
def test_scalars_are_left_alone(v):
    assert to_term(v) is v or to_term(v) == v


def test_a_bool_is_not_widened_to_an_int():
    assert to_term(True) is True


# ── the registry comes first ─────────────────────────────────────────────────

def test_a_date_gets_its_CANONICAL_shape_not_a_mangled_one():
    """The whole point of registry-first."""
    assert to_term(datetime.date(2023, 6, 1)) == ("date", 2023, 6, 1)


def test_a_timedelta_gets_its_canonical_shape():
    assert to_term(datetime.timedelta(days=3)) == ("timedelta", 3, 0, 0)


def test_a_decimal_gets_its_canonical_shape():
    """Ruled: mantissa and power-of-ten scale."""
    assert to_term(Decimal("10.01")) == ("decimal", 1001, 2)


# ── the generic form, for anything the registry does not know ────────────────

def test_an_arbitrary_object_becomes_module_sep_class_plus_match_args():
    got = to_term(Point(1, 2))
    assert got == (f"{Point.__module__}{HIDDEN_SEP}Point", 1, 2)


def test_conversion_RECURSES_into_the_match_args():
    got = to_term(Point(datetime.date(2023, 6, 1), [Decimal("0.5")]))
    assert got[1] == ("date", 2023, 6, 1)
    assert got[2] == [("decimal", 5, 1)]


# ── containers ───────────────────────────────────────────────────────────────

def test_a_tuple_becomes_the_data_tuple_form():
    assert to_term((1, 2)) == ("()", 1, 2)


def test_a_list_stays_a_list_and_its_elements_convert():
    assert to_term([datetime.date(2023, 6, 1), 2]) == [("date", 2023, 6, 1), 2]


def test_a_dict_converts_keys_and_values():
    assert to_term({"k": datetime.date(2023, 6, 1)}) == {"k": ("date", 2023, 6, 1)}


# ── the hazard the operator named: a tuple ALREADY in functor-first form ─────

def test_an_already_functor_first_tuple_is_the_DOCUMENTED_hazard():
    """``("date", 2023, 6, 1)`` is already a term; wrapping it as data would be
    wrong. But it is indistinguishable from a genuine data tuple of a string
    and ints, so this is DOCUMENTED rather than solved (operator's call).

    The rule chosen: a tuple is data unless it is a WELL-FORMED term the engine
    already recognises. That keeps the common case right and makes the residual
    ambiguity narrow and nameable, rather than leaving every tuple ambiguous.
    """
    assert to_term(("date", 2023, 6, 1)) == ("date", 2023, 6, 1)
    # ... and a look-alike that is NOT a well-formed term is treated as data
    assert to_term(("date", "x", "y")) == ("()", "date", "x", "y")


def test_an_object_with_no_match_args_says_so_rather_than_guessing():
    class Opaque:
        def __init__(self):
            self.a = 1
    with pytest.raises(TypeError) as exc:
        to_term(Opaque())
    assert "__match_args__" in str(exc.value)


# ── the reverse direction ────────────────────────────────────────────────────

def test_from_term_rebuilds_the_python_value():
    from clausal.logic.python_terms import from_term
    assert from_term(("date", 2023, 6, 1)) == datetime.date(2023, 6, 1)
    assert from_term(("timedelta", 3, 0, 0)) == datetime.timedelta(days=3)
    assert from_term(("decimal", 1001, 2)) == Decimal("10.01")


def test_a_decimal_round_trips_INCLUDING_its_scale():
    from clausal.logic.python_terms import from_term
    for lit in ("10.01", "10.010", "-10.01", "1550.00", "0.1"):
        assert str(from_term(to_term(Decimal(lit)))) == lit


def test_an_aware_datetime_round_trips_with_its_offset():
    from clausal.logic.python_terms import from_term
    v = datetime.datetime(2023, 6, 1, tzinfo=datetime.timezone.utc)
    assert from_term(to_term(v)) == v


def test_the_data_tuple_recurses_both_ways():
    from clausal.logic.python_terms import from_term
    v = (datetime.date(2023, 6, 1), 2, "x")
    assert from_term(to_term(v)) == v


def test_an_unregistered_functor_comes_back_UNCHANGED():
    """Most terms are not Python values in disguise."""
    from clausal.logic.python_terms import from_term
    t = ("cite", ("art52",))
    assert from_term(t) is t


def test_a_look_alike_with_the_right_head_but_wrong_components_is_unchanged():
    from clausal.logic.python_terms import from_term
    t = ("date", "x", "y")
    assert from_term(t) is t


# ── the registry is global and immutable ─────────────────────────────────────

def test_overriding_a_registered_type_is_REFUSED():
    from clausal.logic.python_terms import register
    with pytest.raises(ValueError) as exc:
        register(datetime.date, "date2", lambda v: (), lambda t: None)
    assert "overriding is not allowed" in str(exc.value)


def test_overriding_a_registered_FUNCTOR_is_refused_too():
    from clausal.logic.python_terms import register
    class Other:
        pass
    with pytest.raises(ValueError) as exc:
        register(Other, "date", lambda v: (), lambda t: None)
    assert "overriding is not allowed" in str(exc.value)
