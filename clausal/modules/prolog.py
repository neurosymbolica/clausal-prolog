"""ISO Prolog integer arithmetic that differs from Python's operators.

In Python, ``//`` is floor division (rounds toward negative infinity).  ISO
Prolog's ``(//)/2`` truncates toward zero, its ``mod/2`` is floored (sign
follows the divisor, like Python ``%``) and its ``rem/2`` follows the
dividend.

The ``.pl`` front ends no longer route through this module: they emit the
quoted ISO evaluables (``'//'(X, Y)``, ``'mod'(X, Y)``, ``'rem'(X, Y)``)
that the engine's evaluable table implements.  The helpers below are
PRIVATE (operator ruling D16-X2, 2026-10-04: no public TitleCase names, no
aliases) and are kept only as plain Python reference implementations::

    _trunc_div(-7, 2)   # -3 (ISO: truncate toward zero; Python // gives -4)
    _trunc_mod(7, -3)   # -2 (ISO mod: sign follows the divisor)
    _rem(-7, 3)         # -1 (ISO remainder: sign follows the dividend)
"""


def _trunc_div(a, b):
    """ISO Prolog ``(//)/2`` — integer division truncated toward zero.

    Computed with integer arithmetic so it stays exact for operands beyond
    2**53, where routing through ``float`` (``int(a / b)``) loses precision
    (F021).
    """
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _trunc_mod(a, b):
    """ISO Prolog ``mod/2`` — modulo whose sign follows the *divisor*.

    Equivalent to Python's floored ``%``: ``-7 mod 3 =:= 2`` and
    ``7 mod -3 =:= -2``.  Use :func:`_rem` for ``rem/2`` (sign follows the
    dividend, F020).
    """
    return a % b


def _rem(a, b):
    """ISO Prolog ``rem/2`` — remainder whose sign follows the dividend.

    Defined as ``a - (a // b) * b`` with truncated division.
    """
    return a - _trunc_div(a, b) * b
