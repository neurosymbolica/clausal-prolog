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

from clausal.logic.python_terms import to_term


# ── an unregistered class has NO generic fallback ────────────────────────────

class Unregistered:
    """Deliberately has __match_args__, to pin that it is IGNORED."""
    __match_args__ = ("x", "y")

    def __init__(self, x, y):
        self.x, self.y = x, y


def test_an_unregistered_class_RAISES_and_names_the_registry():
    """No generic converter, by design. A class's attributes may each need
    converting differently and only that class knows how, so a generic walk is
    not a fallback -- it is a different, wrong answer."""
    with pytest.raises(TypeError) as exc:
        to_term(Unregistered(1, 2))
    assert "no registered conversion" in str(exc.value)
    assert "register(" in str(exc.value)


def test___match_args___is_NOT_consulted():
    """It was, in the first cut. Pinned so the generic path cannot creep back."""
    with pytest.raises(TypeError):
        to_term(Unregistered(1, 2))


def test_the_implicit_path_lets_an_unregistered_class_through():
    """``++`` must leave alone what it does not understand -- raising there
    refused values that had always been legal (323 failures)."""
    u = Unregistered(1, 2)
    assert to_term(u, strict=False) is u


def test_conversion_RECURSES_through_a_registered_container():
    got = to_term([datetime.date(2023, 6, 1), Decimal("0.5")])
    # a Decimal is a NUMBER at the seam (Q1/Q7, 2026-09-18): it passes as itself
    assert got == [("date", 2023, 6, 1), Decimal("0.5")]


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
    assert "no registered conversion" in str(exc.value)


# ── the reverse direction ────────────────────────────────────────────────────

def test_from_term_rebuilds_the_python_value():
    from clausal.logic.python_terms import from_term
    assert from_term(("date", 2023, 6, 1)) == datetime.date(2023, 6, 1)
    assert from_term(("timedelta", 3, 0, 0)) == datetime.timedelta(days=3)
    # the decimal cell is a TRANSFER form, not a seam form, since 2026-09-18
    from clausal.logic.python_terms import from_transfer
    assert from_transfer(("decimal", 1001, 2)) == Decimal("10.01")
    assert from_term(("decimal", 1001, 2)) == ("decimal", 1001, 2)


def test_a_decimal_round_trips_INCLUDING_its_scale():
    from clausal.logic.python_terms import from_transfer, to_transfer
    for lit in ("10.01", "10.010", "-10.01", "1550.00", "0.1"):
        assert str(from_transfer(to_transfer(Decimal(lit)))) == lit
        assert to_term(Decimal(lit)) == Decimal(lit)          # the seam passes the number


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


# ── a decimal with no fractional digits is an INT ────────────────────────────

def test_a_decimal_with_no_decimal_places_is_an_int():
    """RULED 2026-09-15. ('decimal', M, E) means M x 10^-E, so E is a COUNT OF
    DECIMAL PLACES. A negative count is not a quantity of anything -- it is a
    significant-figures claim (``1E+5`` is "100000 to one significant figure"),
    which is an assertion about precision rather than about the value, and the
    language does not model it.

    Same rule the engine already applies one level up: clpfd.py:1441 "an
    integral rational presents as int", normalised at 1506's "single choke
    point" rather than at every binding. This is that choke point for decimals.
    """
    from clausal.logic.python_terms import to_transfer
    assert to_transfer(Decimal("1E+5")) == 100000
    assert to_transfer(Decimal("100000")) == 100000
    assert isinstance(to_transfer(Decimal("1E+5")), int)


def test_but_a_decimal_WITH_places_keeps_its_scale_even_when_integral_in_value():
    """The distinction that matters: ``10.00`` has two decimal places and is
    worth ten. Scale is the reason this encoding was chosen over rdiv, so it
    survives -- only the absence of fractional digits makes an int."""
    from clausal.logic.python_terms import to_transfer
    assert to_transfer(Decimal("10.00")) == ("decimal", 1000, 2)
    assert to_transfer(Decimal("0.1")) == ("decimal", 1, 1)


def test_the_reverse_direction_agrees():
    from clausal.logic.python_terms import from_term
    assert from_term(to_term(Decimal("1E+5"))) == 100000
