"""Recursively convert a Python object into functor-first-tuple form.

Design ruled by the operator 2026-09-15: take the class name prefixed with its
module, take the match args, convert them recursively, and emit
``('{module}\\x1f{class}', arg0, ..., argN)``.  Scalars are left alone.  A tuple
becomes the ``('()', ...)`` data form.

The intended consumer is ``++`` (the Python escape), so a value crossing from
Python into a goal arrives as a TERM without the author converting it by hand.
This module does not hook ``++``; that is a separate change with its own gate.

REGISTRY FIRST, generic second, and that ordering is load-bearing
=================================================================
``__match_args__`` is ABSENT on the types that matter most -- measured,
``datetime.date`` and ``Decimal`` both report ``None`` -- so a purely generic
converter fails on exactly the values that prompted this design.

More importantly a generic mangle would give a date
``('datetime\\x1fdate', 2023, 6, 1)`` while 94 corpus rulebases expect
``('date', 2023, 6, 1)``.  **Two encodings for one value is precisely what this
representation change exists to remove**, so a type with a canonical shape uses
it and never the generic form.

The separator is ``atoms.HIDDEN_SEP``, which already exists and already spells
``f"{module}{HIDDEN_SEP}{name}"`` in ``atoms.mangle``.  Reused rather than
respelled: a second definition of an encoding is a drift this lane has paid for
three times.

THE DOCUMENTED HAZARD: a tuple already in functor-first form
============================================================
``("date", 2023, 6, 1)`` is already a term and must not be wrapped as data --
but it is indistinguishable, by shape alone, from a genuine Python tuple of a
string and three ints.  The operator's call is to document this rather than
solve it.

What is implemented narrows it as far as shape allows: a tuple is DATA unless
it is a well-formed term the engine already recognises.  So the common cases are
right and the residue is nameable -- a Python tuple whose first element is a
str, whose remaining elements happen to fit a known term's component types,
converts as that term rather than as data.  In practice that is a tuple like
``("date", 2023, 6, 1)`` meant as data, which has no way to say so.

If that residue ever bites, the fix is not a cleverer guess: it is an explicit
wrapper at the call site saying which was meant.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
from decimal import Decimal
from typing import Any

from clausal.logic.atoms import HIDDEN_SEP
from clausal.logic.cells import TUPLE_TAG

__all__ = ["to_term", "CANONICAL_SHAPES", "generic_functor"]


def _decimal_shape(d: Decimal) -> tuple:
    """``Decimal`` -> ``('decimal', mantissa, scale)``.

    Python's own model: ``as_tuple()`` is ``(sign, digits, exponent)``, so this
    is lossless both ways and SCALE survives -- ``10.01`` and ``10.010`` are
    distinct terms with the same rational value.  A positive Decimal exponent
    (``1E+5``) yields a NEGATIVE scale, which is Decimal's model exactly.
    """
    sign, digits, exponent = d.as_tuple()
    if not isinstance(exponent, int):       # nan / inf carry a str exponent
        raise TypeError(f"to_term: {d!r} has no finite decimal shape")
    mantissa = int("".join(map(str, digits))) * (-1 if sign else 1)
    return ("decimal", mantissa, -exponent)


def _datetime_shape(v: _dt.datetime) -> tuple:
    """Aware values carry a ninth component, the UTC offset in MINUTES.

    Dropping it was measurably wrong: an audit pins that a naive/aware MIX must
    fail cleanly, and with the offset gone every value became naive and the mix
    quietly succeeded.
    """
    base = ("datetime", v.year, v.month, v.day,
            v.hour, v.minute, v.second, v.microsecond)
    if v.tzinfo is None:
        return base
    return base + (v.utcoffset() // _dt.timedelta(minutes=1),)


#: Types whose term shape the language DEFINES.  Consulted before the generic
#: form, so these never appear mangled.  ``datetime`` precedes ``date`` because
#: it is a SUBCLASS -- the other order renders every datetime as a date and
#: silently drops the time of day.
CANONICAL_SHAPES: "list[tuple[type, Any]]" = [
    (_dt.datetime, _datetime_shape),
    (_dt.date, lambda v: ("date", v.year, v.month, v.day)),
    (_dt.time, lambda v: ("time", v.hour, v.minute, v.second, v.microsecond)),
    (_dt.timedelta, lambda v: ("timedelta", v.days, v.seconds, v.microseconds)),
    (Decimal, _decimal_shape),
]

#: Left alone.  ``bool`` is listed for the reader, not for the code: it is a
#: subclass of ``int`` and would pass anyway, but a future edit that narrows the
#: int case must not silently widen ``True`` to ``1``.
_SCALARS = (bool, int, float, str, bytes, bytearray, complex, type(None))


def generic_functor(cls: type) -> str:
    """``('{module}\\x1f{class}', ...)``'s head, for a type with no canonical
    shape.  The separator is ``atoms.HIDDEN_SEP``, so a generic functor cannot
    collide with a name a program can write."""
    return f"{cls.__module__}{HIDDEN_SEP}{cls.__qualname__}"


def _match_arg_names(obj: Any) -> "tuple[str, ...] | None":
    """The component names to convert, or None if the object does not say.

    ``__match_args__`` first, because it is the object's own statement of its
    positional structure.  A dataclass without one still declares its fields,
    and a namedtuple declares ``_fields``.  Nothing else is guessed: reading
    ``__dict__`` would invent an order the class never promised.
    """
    ma = getattr(type(obj), "__match_args__", None)
    if ma:
        return tuple(ma)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return tuple(f.name for f in dataclasses.fields(obj))
    fields = getattr(type(obj), "_fields", None)
    if isinstance(fields, tuple) and all(isinstance(f, str) for f in fields):
        return fields
    return None


def _already_a_term(value: tuple) -> bool:
    """True for a tuple the engine would already read as a well-formed term.

    Narrow on purpose -- see THE DOCUMENTED HAZARD.  Only a canonical shape
    counts: a generic ``('mod\\x1fCls', ...)`` is admitted too, since nothing
    else can produce that head.
    """
    if not value or type(value[0]) is not str:
        return False
    head = value[0]
    if HIDDEN_SEP in head:
        return True
    if head == TUPLE_TAG:
        return True
    from clausal.modules.py.datetime import date_term_to_python  # noqa: PLC0415
    if date_term_to_python(value) is not value:
        return True
    if head == "decimal" and len(value) == 3:
        return all(isinstance(a, int) and not isinstance(a, bool)
                   for a in value[1:])
    return False


def to_term(value: Any) -> Any:
    """*value* as a functor-first term, recursively.

    Scalars pass through.  A registered type takes its canonical shape.  A list
    stays a list and a dict stays a dict, with their contents converted -- both
    are term shapes in their own right, so wrapping them would be wrong.  A
    tuple becomes the ``('()', ...)`` data form unless it is already a term.
    Anything else uses ``('{module}\\x1f{class}', *match_args)``.
    """
    if isinstance(value, _SCALARS):
        return value
    for cls, shape in CANONICAL_SHAPES:
        if isinstance(value, cls):
            return shape(value)
    if isinstance(value, tuple):
        if _already_a_term(value):
            return value
        return (TUPLE_TAG,) + tuple(to_term(v) for v in value)
    if isinstance(value, list):
        return [to_term(v) for v in value]
    if isinstance(value, dict):
        return {to_term(k): to_term(v) for k, v in value.items()}
    names = _match_arg_names(value)
    if names is None:
        raise TypeError(
            f"to_term: {type(value).__name__} has no __match_args__, no "
            f"dataclass fields and no _fields, so its component order is "
            f"unknown. Give it __match_args__, or register a canonical shape."
        )
    return (generic_functor(type(value)),) + tuple(
        to_term(getattr(value, n)) for n in names)
