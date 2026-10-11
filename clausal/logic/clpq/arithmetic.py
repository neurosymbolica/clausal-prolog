# clausal/logic/clpq/arithmetic.py
"""Exact rationals as (numerator, denominator) pairs of ints.

Deviation D1 (DEVIATIONS.md): 1.3.3 evaluates rat(N,D) terms through
arith_eval, expanded at compile time; this module is the plain-function
equivalent, written so it maps one-to-one onto C over PyLong.
"""
from decimal import Decimal
from fractions import Fraction
import math as _math
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


# ---------------------------------------------------------------- arith.pl runtime
#
# The functions nf.pl (Task 10) evaluates besides + - * /: arith.pl's
# runtime predicates, in its file order.  The float-valued ones go through
# a float as arith.pl's do ("actually just a joke to have this stuff in Q").
# DEVIATIONS.md D1 lists them with their 1.3.3 names.

def limit_encoding_length(numerator, denominator, bits):
    """arith.pl, limit_encoding_length/5: N/D shifted right until it fits
    in *bits* bits, so the float division cannot overflow
    (test_rational_to_float_of_a_huge_rational_is_finite)."""
    if numerator == 0:
        return numerator, denominator
    msb_numerator = abs(numerator).bit_length() - 1
    msb_denominator = denominator.bit_length() - 1
    shift = min(max(msb_numerator, msb_denominator) - bits,
                min(msb_numerator, msb_denominator))
    if shift > 0:
        shifted_numerator = numerator >> shift
        shifted_denominator = denominator >> shift
        common = gcd(shifted_numerator, shifted_denominator)
        return shifted_numerator // common, shifted_denominator // common
    return numerator, denominator


def exponential(x):
    """arith.pl, exponential_rational/4 (expq/4): exp(X) through a float."""
    return float_to_rational(_math.exp(rational_to_float(x)))


def logarithm(x):
    """arith.pl, logarithm_rational/4 (logq/4)."""
    return float_to_rational(_math.log(rational_to_float(x)))


def sine(x):
    """arith.pl, sine_rational/4 (sinq/4)."""
    return float_to_rational(_math.sin(rational_to_float(x)))


def cosine(x):
    """arith.pl, cosine_rational/4 (cosq/4)."""
    return float_to_rational(_math.cos(rational_to_float(x)))


def tangent(x):
    """arith.pl, tangent_rational/4 (tanq/4)."""
    return float_to_rational(_math.tan(rational_to_float(x)))


def arc_sine(x):
    """arith.pl, arc_sine_rational/4 (asinq/4)."""
    return float_to_rational(_math.asin(rational_to_float(x)))


def arc_cosine(x):
    """arith.pl, arc_cosine_rational/4 (acosq/4)."""
    return float_to_rational(_math.acos(rational_to_float(x)))


def arc_tangent(x):
    """arith.pl, arc_tangent_rational/4 (atanq/4)."""
    return float_to_rational(_math.atan(rational_to_float(x)))


def exponential_power(x, y):
    """arith.pl, exponential_rational/6 (expq/6): X^Y, exact for an integer
    Y (test_exponential_power_is_exact_for_integer_exponents), through a
    float otherwise.  1.3.3 builds rat(1, 0) for 0^-N, which its callers
    then refuse; the port raises ZeroDivisionError, and nf.pl's caller
    checks first (DEVIATIONS.md D1)."""
    if y[1] == 1:
        if y[0] >= 0:
            return power(y[0], x, ONE)
        result = power(-y[0], x, ONE)
        return make_rational(result[1], result[0])
    return float_to_rational(_math.pow(rational_to_float(x),
                                       rational_to_float(y)))


def power(exponent, x, so_far):
    """arith.pl, power_rational/7 (powq/7): so_far * x^exponent for an
    exponent >= 0, by repeated squaring; the recursion is a loop."""
    while True:
        if exponent == 0:
            return so_far
        if exponent == 1:
            return multiply(x, so_far)
        if exponent & 1:
            so_far = multiply(x, so_far)
        x = multiply(x, x)
        exponent >>= 1


def minimum(x, y):
    """arith.pl, minimum_rational/6 (minq/6)."""
    return y if compare(x, y) > 0 else x


def maximum(x, y):
    """arith.pl, maximum_rational/6 (maxq/6)."""
    return x if compare(x, y) > 0 else y


def absolute(x):
    """arith.pl, abs(rat(Nx,Dx)) in specialize_rational_function//2."""
    return (abs(x[0]), x[1])


def rational_to_float(x):
    """arith.pl, rational_to_float/3 (rat_float/3)."""
    numerator, denominator = limit_encoding_length(x[0], x[1], 1023)
    return numerator / denominator


def float_to_rational(value):
    """arith.pl, float_to_rational/3,9 (float_rat): the continued fraction
    of *value*, at most 100 steps, stopping at the first convergent equal to
    it as a float (test_float_to_rational_gives_the_short_convergent: 0.1 is
    1/10).  The recursion is a loop."""
    if value != value or value in (_math.inf, -_math.inf):
        raise ValueError(f"float_to_rational: {value!r} is not finite")
    steps = 100
    remaining = value
    numerator_a, numerator_b = 1, 0
    denominator_a, denominator_b = 0, 1
    while True:
        if steps == 0:                                          # clause 1
            break
        if denominator_a != 0 and \
                abs(value - numerator_a / denominator_a) == 0.0:   # clause 2
            break
        whole = int(remaining)          # SICStus integer/1 truncates (clause 3)
        if whole == remaining:
            numerator_a = numerator_a * whole + numerator_b
            denominator_a = denominator_a * whole + denominator_b
            break
        numerator_a, numerator_b = numerator_a * whole + numerator_b, numerator_a
        denominator_a, denominator_b = (denominator_a * whole + denominator_b,
                                        denominator_a)
        remaining = 1 / (remaining - whole)
        steps -= 1
    return make_rational(numerator_a, denominator_a)


# ---------------------------------------------------------------- arith_q.pl

def arithmetic_normalize(value):
    """arith_q.pl, arithmetic_normalize/2 (arith_normalize/2): a number as
    a rational.  An int, Fraction or Decimal goes through from_number; a
    float through float_to_rational, as get_rational/3 does
    (test_arithmetic_normalize_of_a_float); a rational pair is normalised."""
    if type(value) is tuple:
        return make_rational(value[0], value[1])
    if type(value) is float:
        return float_to_rational(value)
    return from_number(value)


def rational_integer(x):
    """arith_q.pl, rational_integer/2 (integerp/2): the int of an integral
    rational, or None."""
    if x[1] == 1:
        return x[0]
    return None
