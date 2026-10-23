"""The numeric KINDS of the engine's number terms -- one spelling, shared.

ISO 7.3 unifies an integer with an integer and a float with a float, never
one with the other: ``1 = 1.0`` fails, ``1 == 1.0`` fails, and ``compare/3``
orders ``1.0`` before ``1``.  Clausal extends the rule to every number type
it carries: a ``Decimal`` (an exact decimal with a SCALE) and a ``Fraction``
(an exact rational) are each a kind of their own, and so is ``complex``.
Two Decimals are one term only at one scale (``1.0`` is not ``1.00``, the
ruling of 2026-09-17 Q2); Python's ``Decimal.__eq__`` ignores scale, so it
is compared here.

Three mechanisms must agree on this, or two of them disagree about how many
terms exist (``todo/done/a01-d001-tabling-half-2026-09-09.md``):

* the unifier -- ``variables/_variables.c::numeric_kind`` is the C twin of
  :func:`numeric_kind` (operator ruling 2026-10-23, ISO 7.3), and
  ``constraints.structural_eq``'s atomic fast path asks :func:`same_number`;
* ``'=='``/2 and the standard order --
  ``builtins/iso_compare._numeric_tag`` and ``_helpers._NUMERIC_RANK``;
* the keys that stand in for identity -- tabling's variant keys
  (``tabling._normalize_for_key_py`` and ``_tabling_core.c::do_normalize``),
  setof/3's dedup, and the constant-list membership set
  (``runtime/const_set``).

A truth atom (``True``/``False``, D35) is an ATOM, not a number, and an int
SUBCLASS is untagged (falls back to ``==``), exactly as ``_numeric_tag``
has always had it.
"""

from __future__ import annotations

from decimal import Decimal as _Decimal
from fractions import Fraction as _Fraction

__all__ = ["numeric_kind", "decimal_scale", "same_number"]


def numeric_kind(x):
    """The numeric kind of *x* -- a TYPE object -- or ``None`` when *x* is not a
    tagged number (a bool, an int subclass, anything that is not a number)."""
    if type(x) is int:
        return int
    if isinstance(x, bool):
        return None                     # a truth ATOM (D35), not a number kind
    if isinstance(x, (float, complex, _Decimal, _Fraction)):
        return type(x)
    return None


def decimal_scale(x: _Decimal) -> int:
    """Decimal places of a Decimal object (``1.00`` -> 2).  A non-finite
    Decimal has a str exponent and gets a scale of its own, so ``NaN`` and
    ``Infinity`` never share one with a finite Decimal."""
    exponent = x.as_tuple().exponent
    return -exponent if isinstance(exponent, int) else None


def same_number(a, b) -> bool:
    """False iff *a* and *b* are two tagged numbers of DIFFERENT kinds, or
    two Decimals of different scale.  True for every other pair, including
    one tagged number against an untagged value, whose ``==`` then decides
    (:func:`numeric_kind` says why those stay untagged).

    This is the ONE-WAY check the unifier's C arm makes after its ``==``
    fallback would say equal: a caller that already has ``a == b`` adds
    ``same_number(a, b)`` to get the ISO answer."""
    ka = numeric_kind(a)
    kb = numeric_kind(b)
    if ka is None or kb is None:
        return True
    if ka is not kb:
        return False
    if ka is _Decimal:
        return decimal_scale(a) == decimal_scale(b)
    return True
