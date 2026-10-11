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


# ---------------------------------------------------------------- arith.pl runtime (Task 10, for nf.pl)

def test_float_to_rational_gives_the_short_convergent():
    assert a.float_to_rational(0.1) == a.make_rational(1, 10)
    assert a.float_to_rational(-2.5) == a.make_rational(-5, 2)
    assert a.float_to_rational(3.0) == a.make_rational(3, 1)
    pi = a.float_to_rational(3.141592653589793)
    assert pi[0] / pi[1] == 3.141592653589793


def test_rational_to_float_of_a_huge_rational_is_finite():
    assert a.rational_to_float(a.make_rational(10**400 + 1, 3 * 10**399)) == pytest.approx(10 / 3)


def test_exponential_power_is_exact_for_integer_exponents():
    assert a.exponential_power(a.make_rational(2, 3), a.make_rational(5, 1)) == a.make_rational(32, 243)
    assert a.exponential_power(a.make_rational(-2, 3), a.make_rational(-3, 1)) == a.make_rational(-27, 8)
    assert a.exponential_power(a.make_rational(9, 1), a.make_rational(1, 2)) == a.make_rational(3, 1)
    with pytest.raises(ZeroDivisionError):
        a.exponential_power(a.ZERO, a.make_rational(-1, 1))


def test_arithmetic_normalize_of_a_float():
    assert a.arithmetic_normalize(0.75) == a.make_rational(3, 4)
    assert a.arithmetic_normalize((2, 4)) == a.make_rational(1, 2)
    assert a.arithmetic_normalize(7) == a.make_rational(7, 1)


def test_power_minimum_maximum_absolute():
    assert a.power(10, a.make_rational(3, 2), a.ONE) == a.make_rational(3**10, 2**10)
    assert a.power(0, a.make_rational(3, 2), a.make_rational(5, 1)) == a.make_rational(5, 1)
    assert a.minimum(a.make_rational(1, 2), a.make_rational(1, 3)) == a.make_rational(1, 3)
    assert a.maximum(a.make_rational(1, 2), a.make_rational(1, 3)) == a.make_rational(1, 2)
    assert a.absolute(a.make_rational(-7, 2)) == a.make_rational(7, 2)


def test_functions_through_a_float():
    import math
    for function, reference, x in [
            (a.sine, math.sin, 0.5), (a.cosine, math.cos, 0.5),
            (a.tangent, math.tan, 0.5), (a.arc_sine, math.asin, 0.5),
            (a.arc_cosine, math.acos, 0.5), (a.arc_tangent, math.atan, 0.5),
            (a.exponential, math.exp, 0.5), (a.logarithm, math.log, 0.5)]:
        result = function(a.make_rational(1, 2))
        assert result[0] / result[1] == reference(x)


def test_limit_encoding_length_keeps_small_rationals():
    assert a.limit_encoding_length(3, 7, 1023) == (3, 7)
    # The shift is at most the smaller msb, so the denominator never
    # reaches 0 (arith.pl: min(max(...)-Bits, min(msb(N), msb(D)))).
    assert a.limit_encoding_length(10**400, 3, 1023) == (5 * 10**399, 1)
    numerator, denominator = a.limit_encoding_length(10**400, 10**399 + 1, 1023)
    assert numerator.bit_length() <= 1024 and denominator > 0
