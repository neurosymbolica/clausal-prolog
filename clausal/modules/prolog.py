"""ISO Prolog-compatible operators that differ from Python semantics.

In Python, ``//`` is floor division (rounds toward negative infinity) and
``%`` is floor modulo.  ISO Prolog specifies truncation toward zero for
``(//)/2`` and ``mod/2``.  This module provides the ISO versions so that
translated Prolog code can use them via qualified calls::

    -import_module(prolog)

    X := prolog.TruncDiv(7, 2)    # 3  (same as Python here)
    X := prolog.TruncDiv(-7, 2)   # -3 (ISO: truncate toward zero)
                                   # Python // would give -4

    X := prolog.TruncMod(7, 3)    # 1
    X := prolog.TruncMod(-7, 3)   # -1 (ISO: sign follows dividend)
                                   # Python % would give 2

    X := prolog.Rem(7, 3)         # 1  (ISO remainder)
"""


def TruncDiv(a, b):
    """ISO Prolog ``(//)/2`` — integer division truncated toward zero."""
    return int(a / b)  # int() truncates toward zero


def TruncMod(a, b):
    """ISO Prolog ``mod/2`` — modulo with sign following the dividend.

    Defined as ``a - trunc(a / b) * b``.
    """
    return a - TruncDiv(a, b) * b


def Rem(a, b):
    """ISO Prolog ``rem/2`` — remainder (same as TruncMod for integers)."""
    return a - TruncDiv(a, b) * b
