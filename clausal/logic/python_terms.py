"""Convert a Python object into functor-first-tuple form, and back.

Design ruled by the operator 2026-09-15, and REVISED the same day: there is NO
generic converter. **Every class that crosses the seam must have a registered
conversion function.**

The first cut walked ``__match_args__`` and emitted
``('{module}\\x1f{class}', ...)`` for anything unregistered. That is wrong, and
the reason is not that it fails on types lacking ``__match_args__`` (it does --
``datetime.date`` and ``Decimal`` both report ``None``). It is that **a class's
attributes may each need converting differently, and only that class knows
how.** A generic walk applies one rule to all of them, so it is not a fallback
for the registry -- it is a different, wrong answer that happens to typecheck.

THE REGISTRY
============
``TO_TERM``   maps a class    to the function yielding its TERM.
``FROM_TERM`` maps a functor  to the function rebuilding the PYTHON value.

Each function knows its own components and decides what recurses: the date
family moves its ints across untouched, while the data tuple recurses because
only it can contain anything.

Keyed by EXACT type. An ``isinstance`` walk has to put ``datetime`` before
``date`` -- it is a subclass -- and the wrong order renders every datetime as a
date and silently drops the time of day. Exact keys remove the trap instead of
documenting it. A SUBCLASS therefore needs its own registration, which is the
safe direction: it may carry state the base's function would drop in silence.

GLOBAL, AND OVERRIDING IS REFUSED. A per-module registry would let two ``.seam``
files disagree about what ``('date', ...)`` means, and a term that means
different things in different modules is not a term.

TWO MODES
=========
``strict=True``   an unregistered class RAISES, naming the fix. For a caller
                  who asked for a conversion.
``strict=False``  an unregistered class passes through UNCHANGED. For the
                  implicit ``++`` hook, which must leave alone what it does not
                  understand -- raising there refused values that had always
                  been legal, measured at 323 failures.

THE DOCUMENTED HAZARD: a tuple already in functor-first form
============================================================
``("date", 2023, 6, 1)`` is already a term and must not be wrapped as data, but
it is indistinguishable by shape from a Python tuple of a str and three ints.
The operator's call is to document rather than solve it.

Narrowed as far as shape allows: a tuple is DATA unless it is a well-formed
term the engine already recognises, so ``("date", "x", "y")`` converts as data
while ``("date", 2023, 6, 1)`` does not. If the residue ever bites, the fix is
an explicit wrapper at the call site, not a cleverer guess.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
from decimal import Decimal
from typing import Any

from clausal.logic.cells import TUPLE_TAG

__all__ = ["to_term", "from_term", "register", "TO_TERM", "FROM_TERM"]


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


def _is_already_engine_term(value: Any) -> bool:
    """True for a value the ENGINE already owns as a term.

    A logic variable most of all: converting one is not lossy, it is
    destructive. The rest are engine term types that have no Python value to
    convert TO -- they are already the representation.
    """
    from clausal.logic.variables import Var  # noqa: PLC0415
    if isinstance(value, Var):
        return True
    return type(value).__module__.startswith(("clausal.", "_variables"))


def _already_a_term(value: tuple) -> bool:
    """True for a tuple the engine would already read as a well-formed term.

    Narrow on purpose -- see THE DOCUMENTED HAZARD.  Only a canonical shape
    counts: a generic ``('mod\\x1fCls', ...)`` is admitted too, since nothing
    else can produce that head.
    """
    if not value or type(value[0]) is not str:
        return False
    head = value[0]
    if head == TUPLE_TAG:
        return True
    from clausal.modules.py.datetime import date_term_to_python  # noqa: PLC0415
    if date_term_to_python(value) is not value:
        return True
    if head == "decimal" and len(value) == 3:
        return all(isinstance(a, int) and not isinstance(a, bool)
                   for a in value[1:])
    return False


def to_term(value: Any, *, strict: bool = True) -> Any:
    """*value* as a functor-first term, recursively.

    Scalars pass through.  A registered type takes its canonical shape.  A list
    stays a list and a dict stays a dict, with their contents converted -- both
    are term shapes in their own right, so wrapping them would be wrong.  A
    tuple becomes the ``('()', ...)`` data form unless it is already a term.
    Anything else uses ``('{module}\\x1f{class}', *match_args)``.
    """
    if isinstance(value, _SCALARS):
        return value
    if _is_already_engine_term(value):
        # A logic VARIABLE, or a term type the engine already owns. Converting
        # one would be a category error -- an AttVar is not a Python value with
        # a term form, it IS the term -- and for a Var it would be destructive.
        return value
    convert = TO_TERM.get(type(value))
    if convert is not None:
        return convert(value)
    if isinstance(value, list):
        return [to_term(v, strict=strict) for v in value]
    if isinstance(value, dict):
        return {to_term(k, strict=strict): to_term(v, strict=strict)
                for k, v in value.items()}
    if not strict:
        # The IMPLICIT path (``++``). A class with no registered conversion
        # passes through UNCHANGED, exactly as it did before ++ auto-converted.
        return value
    raise TypeError(
        f"to_term: {type(value).__name__} has no registered conversion. "
        f"Every class that crosses the seam needs one -- register(cls, "
        f"functor, to_fn, from_fn) -- because only the class's own function "
        f"knows how its attributes convert."
    )


def from_term(value: Any) -> Any:
    """A TERM back to its Python value, recursively. The reverse of ``to_term``.

    For a term coming back OUT -- a harness reading an answer, say. Consults
    ``FROM_TERM`` by functor, so each registered type rebuilds itself and
    decides what recurses.

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
