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
    x = a.make_rational(rng.randint(-10**40, 10**40), rng.randint(1, 10**30))
    y = a.make_rational(rng.randint(-10**40, 10**40), rng.randint(1, 10**30))
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
