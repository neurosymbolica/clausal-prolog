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

__all__ = ["to_term", "from_term", "register", "TO_TERM", "FROM_TERM",
           "generic_functor"]


def _decimal_to_term(d: Decimal) -> tuple:
    """``Decimal`` -> ``('decimal', mantissa, scale)``. Components are already
    ints, so nothing recurses."""
    sign, digits, exponent = d.as_tuple()
    if not isinstance(exponent, int):       # nan / inf carry a str exponent
        raise TypeError(f"to_term: {d!r} has no finite decimal shape")
    mantissa = int("".join(map(str, digits))) * (-1 if sign else 1)
    return ("decimal", mantissa, -exponent)


def _decimal_from_term(t: tuple) -> Decimal:
    _, mantissa, scale = t
    return Decimal(mantissa).scaleb(-scale)


def _datetime_to_term(v: _dt.datetime) -> tuple:
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


def _datetime_from_term(t: tuple) -> _dt.datetime:
    args = t[1:]
    if len(args) == 8:
        *fields, offset = args
        return _dt.datetime(*fields, tzinfo=_dt.timezone(
            _dt.timedelta(minutes=offset)))
    return _dt.datetime(*args)


def _tuple_to_term(v: tuple) -> tuple:
    """The one entry that RECURSES -- a data tuple's elements are arbitrary.

    It also owns THE DOCUMENTED HAZARD, because the entry is the only place that
    knows what a tuple can be: a tuple already in functor-first form is left
    alone rather than wrapped as data. Keeping that here rather than in
    ``to_term`` is the same principle as the rest of the registry -- the
    conversion function decides, and the dispatcher only dispatches.
    """
    if _already_a_term(v):
        return v
    return (TUPLE_TAG,) + tuple(to_term(e) for e in v)


def _tuple_from_term(t: tuple) -> tuple:
    return tuple(from_term(e) for e in t[1:])


#: Python type -> the function that yields its TERM.
#:
#: Keyed by EXACT type, deliberately. An ``isinstance`` walk has to put
#: ``datetime`` before ``date`` -- it is a subclass -- and the wrong order
#: renders every datetime as a date and silently drops the time of day. Exact
#: keys remove that trap rather than documenting it, and make lookup O(1).
#:
#: A SUBCLASS therefore does not match its base's entry. That is the safe
#: direction: a subclass may carry state the base shape would drop without
#: saying so, and falling through to the generic form (or to the TypeError that
#: names the fix) is better than truncating in silence.
TO_TERM: "dict[type, Any]" = {}

#: Functor string -> the function that rebuilds the PYTHON value.
#:
#: The reverse direction, for a term coming back out. Each function knows its
#: own components: the date family moves ints across untouched, while the data
#: tuple recurses, because only it can contain anything.
FROM_TERM: "dict[str, Any]" = {}


def register(cls: type, functor: str, to_fn, from_fn) -> None:
    """Add a bidirectional conversion. OVERRIDING IS REFUSED.

    Global and immutable by the operator's ruling (2026-09-15): a per-module
    registry would let two ``.seam`` files disagree about what ``('date', ...)``
    means, and a term that means different things in different modules is not a
    term. If a second registration is ever legitimate, it needs a design for
    which one wins at a CROSSING, and that does not exist.
    """
    if cls in TO_TERM:
        raise ValueError(
            f"register: {cls.__name__} already converts to "
            f"{TO_TERM[cls].__name__}; overriding is not allowed")
    if functor in FROM_TERM:
        raise ValueError(
            f"register: functor {functor!r} is already registered; "
            f"overriding is not allowed")
    TO_TERM[cls] = to_fn
    FROM_TERM[functor] = from_fn


register(_dt.datetime, "datetime", _datetime_to_term, _datetime_from_term)
register(_dt.date, "date",
         lambda v: ("date", v.year, v.month, v.day),
         lambda t: _dt.date(*t[1:]))
register(_dt.time, "time",
         lambda v: ("time", v.hour, v.minute, v.second, v.microsecond),
         lambda t: _dt.time(*t[1:]))
register(_dt.timedelta, "timedelta",
         lambda v: ("timedelta", v.days, v.seconds, v.microseconds),
         lambda t: _dt.timedelta(*t[1:]))
register(Decimal, "decimal", _decimal_to_term, _decimal_from_term)
register(tuple, TUPLE_TAG, _tuple_to_term, _tuple_from_term)


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
    convert = TO_TERM.get(type(value))
    if convert is not None:
        return convert(value)
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


def from_term(value: Any) -> Any:
    """A TERM back to its Python value, recursively. The reverse of ``to_term``.

    For a term coming back OUT -- a harness reading an answer, say. Consults
    ``FROM_TERM`` by functor, so each registered type rebuilds itself and
    decides what recurses: the date family moves its ints across untouched,
    while the data tuple recurses because only it can contain anything.

    A term with no registered functor is returned UNCHANGED rather than guessed
    at. Most terms are not Python values in disguise -- ``('cite', ('art52',))``
    is a term and should stay one -- so silence is the correct default and the
    registry is the whole of the opt-in.
    """
    if isinstance(value, _SCALARS):
        return value
    if isinstance(value, list):
        return [from_term(v) for v in value]
    if isinstance(value, dict):
        return {from_term(k): from_term(v) for k, v in value.items()}
    if type(value) is not tuple or not value or type(value[0]) is not str:
        return value
    rebuild = FROM_TERM.get(value[0])
    if rebuild is None:
        return value
    try:
        return rebuild(value)
    except (TypeError, ValueError, OverflowError):
        # A look-alike, not a term: ("date", "x", "y") has the head but not the
        # components. Unchanged, for the same reason an unregistered functor is.
        return value
