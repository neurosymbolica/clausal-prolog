# tests/clpq_port/test_arithmetic.py
import random
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.clpq import arithmetic as a


def _fraction(r):
    return Fraction(*r)


@pytest.mark.parametrize("seed", range(200))
def test_operations_agree_with_fractions(seed):
    rng = random.Random(seed)
    x = a.make_rational(rng.randint(-10**40, 10**40),
                        rng.choice((1, -1)) * rng.randint(1, 10**30))
    y = a.make_rational(rng.randint(-10**40, 10**40),
                        rng.choice((1, -1)) * rng.randint(1, 10**30))
    assert x[1] > 0 and y[1] > 0
    fx, fy = _fraction(x), _fraction(y)
    assert _fraction(a.add(x, y)) == fx + fy
    assert _fraction(a.subtract(x, y)) == fx - fy
    assert _fraction(a.multiply(x, y)) == fx * fy
    if fy:
        assert _fraction(a.divide(x, y)) == fx / fy
    assert a.compare(x, y) == (fx > fy) - (fx < fy)


def test_normal_form():
    assert a.make_rational(4, -6) == (-2, 3)
    assert a.make_rational(0, 5) == (0, 1)


def test_coefficient_growth_stays_exact():           # Review Focus 3
    x = a.ZERO
    step = a.make_rational(7, 13)
    third = a.make_rational(1, 3)
    for _ in range(30):
        x = a.add(a.multiply(step, x), third)
    expected = Fraction(0)
    for _ in range(30):
        expected = Fraction(7, 13) * expected + Fraction(1, 3)
    assert _fraction(x) == expected and x[1] > 10**30


def test_numbers_in_and_out():
    assert a.from_number(Decimal("0.25")) == (1, 4)
    assert a.to_number((6, 1)) == 6 and type(a.to_number((6, 1))) is int
    assert a.to_number((1, 2)) == Fraction(1, 2)


def test_coefficient_growth_past_ten_to_the_sixty():  # Review Focus 3
    x = a.ZERO
    expected = Fraction(0)
    step = a.make_rational(7, 13)
    third = a.make_rational(1, 3)
    for _ in range(60):
        x = a.add(a.multiply(step, x), third)
        expected = Fraction(7, 13) * expected + Fraction(1, 3)
    assert type(x[0]) is int and type(x[1]) is int
    assert _fraction(x) == expected
    assert x[0] > 10**60 and x[1] > 10**60


def test_negate_sign_is_zero_one():
    assert a.negate((3, 4)) == (-3, 4)
    assert a.negate((-3, 4)) == (3, 4)
    assert a.negate(a.ZERO) == a.ZERO
    assert a.sign((-5, 2)) == -1
    assert a.sign(a.ZERO) == 0
    assert a.sign((5, 2)) == 1
    assert a.is_zero(a.ZERO) and a.is_zero(a.make_rational(0, -7))
    assert not a.is_zero((1, 10**40))
    assert a.ONE == (1, 1) and a.ZERO == (0, 1)
    assert a.multiply(a.ONE, (2, 3)) == (2, 3)
    assert a.add(a.ZERO, (2, 3)) == (2, 3)


def test_divide_by_zero_raises():
    with pytest.raises(ZeroDivisionError):
        a.divide(a.ONE, a.ZERO)
    with pytest.raises(ZeroDivisionError):
        a.make_rational(1, 0)


def test_from_number_int_and_fraction():
    assert a.from_number(-7) == (-7, 1)
    assert a.from_number(10**70) == (10**70, 1)
    assert a.from_number(Fraction(-6, 4)) == (-3, 2)
    assert a.from_number(Decimal("-1.50")) == (-3, 2)
    assert a.from_number(Decimal("12E3")) == (12000, 1)


class _IntSubclass(int):
    pass


@pytest.mark.parametrize("value", [
    True, False, 0.5, 1.0, _IntSubclass(3), "1", None,
    Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity"),
])
def test_from_number_rejects_inexact_input(value):
    with pytest.raises(TypeError, match="not an exact number"):
        a.from_number(value)
