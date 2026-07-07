"""ISO Prolog-compatible operators that differ from Python semantics.

In Python, ``//`` is floor division (rounds toward negative infinity) and
``%`` is floor modulo.  ISO Prolog specifies truncation toward zero for
``(//)/2`` and ``mod/2``.  This module provides the ISO versions so that
translated Prolog code can use them via qualified calls::

    -import_module(prolog)

    X := prolog.TruncDiv(7, 2)    # 3  (same as Python here)
    X := prolog.TruncDiv(-7, 2)   # -3 (ISO: truncate toward zero)
                                   # Python // would give -4

    X := prolog.TruncMod(7, -3)   # -2 (ISO mod: sign follows the divisor)
                                   # sibling of Python % (also floored)

    X := prolog.Rem(-7, 3)        # -1 (ISO remainder: sign follows dividend)
"""


def TruncDiv(a, b):
    """ISO Prolog ``(//)/2`` — integer division truncated toward zero.

    Computed with integer arithmetic so it stays exact for operands beyond
    2**53, where routing through ``float`` (``int(a / b)``) loses precision
    (F021).
    """
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def TruncMod(a, b):
    """ISO Prolog ``mod/2`` — modulo whose sign follows the *divisor*.

    Equivalent to Python's floored ``%``: ``-7 mod 3 =:= 2`` and
    ``7 mod -3 =:= -2``. Prolog ``mod`` maps to this legacy name; use
    :func:`Rem` for ``rem/2`` (sign follows the dividend, F020).
    """
    return a % b


def Rem(a, b):
    """ISO Prolog ``rem/2`` — remainder whose sign follows the dividend.

    Defined as ``a - (a // b) * b`` with truncated division.
    """
    return a - TruncDiv(a, b) * b
