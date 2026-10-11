# clausal/logic/clpq/arithmetic.py
"""Exact rationals as (numerator, denominator) pairs of ints.

Deviation D1 (DEVIATIONS.md): 1.3.3 evaluates rat(N,D) terms through
arith_eval, expanded at compile time; this module is the plain-function
equivalent, written so it maps one-to-one onto C over PyLong.
"""
from decimal import Decimal
from fractions import Fraction
from math import gcd

ZERO = (0, 1)
ONE = (1, 1)


def make_rational(numerator, denominator):
    if denominator == 0:
        raise ZeroDivisionError("rational with denominator 0")
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    common = gcd(numerator, denominator)
    if common > 1:
        numerator //= common
        denominator //= common
    return (numerator, denominator)


def add(x, y):
    return make_rational(x[0] * y[1] + y[0] * x[1], x[1] * y[1])


def subtract(x, y):
    return make_rational(x[0] * y[1] - y[0] * x[1], x[1] * y[1])


def multiply(x, y):
    return make_rational(x[0] * y[0], x[1] * y[1])


def divide(x, y):
    if y[0] == 0:
        raise ZeroDivisionError("rational division by zero")
    return make_rational(x[0] * y[1], x[1] * y[0])


def negate(x):
    return (-x[0], x[1])


def compare(x, y):
    left = x[0] * y[1]
    right = y[0] * x[1]
    return (left > right) - (left < right)


def sign(x):
    return (x[0] > 0) - (x[0] < 0)


def is_zero(x):
    return x[0] == 0


def from_number(x):
    if type(x) is int:
        return (x, 1)
    if type(x) is Fraction:
        return (x.numerator, x.denominator)
    if type(x) is Decimal and x.is_finite():
        numerator, denominator = x.as_integer_ratio()
        return (numerator, denominator)
    raise TypeError(f"not an exact number: {x!r}")


def to_number(x):
    return x[0] if x[1] == 1 else Fraction(x[0], x[1])
