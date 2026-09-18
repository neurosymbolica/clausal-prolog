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

THE TRANSFER LAYER
==================
``TO_TRANSFER`` / ``FROM_TRANSFER`` and ``to_transfer`` / ``from_transfer``
sit BESIDE the seam registry. A same-interpreter seam PASSES THE OBJECT
(ruled 2026-09-15) -- a quantity stands in for a number and must reach
``#=/2`` as itself -- so the entries a subinterpreter, a process boundary or
a bytecode cache need (``Quantity`` as ``quantity/2``, ``Fraction`` as
``rdiv/2``) live in their own tables where no seam consumer can reach them.
The transfer functions consult their tables first and fall through to the
seam converters, so a Decimal or a date inside a quantity needs no second
entry. Unlike the seam, the transfer layer reads and writes compounds
recursively -- it carries engine terms, where every compound is a str-headed
tuple, so a registered head's arguments still convert instead of being left
alone. Spec: docs/superpowers/specs/2026-09-16-quantity-transfer-form-design.md

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
from fractions import Fraction
from typing import Any

from clausal.logic.cells import TUPLE_TAG, chars, is_chars, chars_text

__all__ = ["to_term", "from_term", "register", "TO_TERM", "FROM_TERM",
           "to_transfer", "from_transfer", "register_transfer",
           "TO_TRANSFER", "FROM_TRANSFER"]


def _decimal_to_term(d: Decimal) -> tuple:
    """``Decimal`` -> ``('decimal', mantissa, scale)``. Components are already
    ints, so nothing recurses."""
    sign, digits, exponent = d.as_tuple()
    if not isinstance(exponent, int):       # nan / inf carry a str exponent
        raise TypeError(f"to_term: {d!r} has no finite decimal shape")
    mantissa = int("".join(map(str, digits))) * (-1 if sign else 1)
    scale = -exponent
    if scale <= 0:
        # NO FRACTIONAL DIGITS -> an int. ``scale`` is a COUNT OF DECIMAL
        # PLACES, and a negative count is not a quantity of anything: a
        # positive Decimal exponent (``1E+5``) is a SIGNIFICANT-FIGURES claim,
        # an assertion about precision rather than about the value, which this
        # language does not model.
        #
        # The same rule the engine already applies one level up -- clpfd.py:
        # "an integral rational presents as int" -- normalised at a single
        # choke point rather than at every binding. This is that choke point
        # for decimals.
        #
        # Note what this does NOT do: ``Decimal("10.00")`` keeps its scale and
        # stays ('decimal', 1000, 2). Scale is why this encoding was chosen
        # over rdiv, so only the ABSENCE of fractional digits makes an int, not
        # integrality of the value.
        return mantissa * 10 ** -scale
    return ("decimal", mantissa, scale)


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

#: Python type -> the function yielding its TRANSFER term. Exact type, as
#: for ``TO_TERM``, and for the same reason.
#:
#: Defined HERE, above ``register``, rather than down in THE TRANSFER LAYER
#: section below: ``register``'s guard checks both tables, and the
#: module-level ``register(...)`` calls for the date family run before that
#: section's code, so the table must already exist when they run.
TO_TRANSFER: "dict[type, Any]" = {}

#: Functor string -> the function rebuilding the Python value from a
#: transfer term. Same reason as ``TO_TRANSFER`` above.
FROM_TRANSFER: "dict[str, Any]" = {}


def register(cls: type, functor: str, to_fn, from_fn) -> None:
    """Add a bidirectional conversion. OVERRIDING IS REFUSED.

    Global and immutable by the operator's ruling (2026-09-15): a per-module
    registry would let two ``.seam`` files disagree about what ``('date', ...)``
    means, and a term that means different things in different modules is not a
    term. If a second registration is ever legitimate, it needs a design for
    which one wins at a CROSSING, and that does not exist.

    Also refuses to shadow a TRANSFER entry (roborev F2): one class, one
    shape, whichever layer owns it -- the same symmetric rule
    ``register_transfer`` applies in the other direction.
    """
    if cls in TO_TERM or cls in TO_TRANSFER:
        raise ValueError(
            f"register: {cls.__name__} already has a conversion; "
            f"overriding is not allowed")
    if functor in FROM_TERM or functor in FROM_TRANSFER:
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
register(tuple, TUPLE_TAG, _tuple_to_term, _tuple_from_term)


# ═══════════════════════════════════════════════════════════════════════════
# THE TRANSFER LAYER -- beside the seam registry, not inside it
# ═══════════════════════════════════════════════════════════════════════════
#
# A same-interpreter seam PASSES THE OBJECT (ruled 2026-09-15): a quantity
# stands in for a number and must reach ``#=/2`` as itself. Only a boundary
# that cannot carry an object -- a subinterpreter, a process, a bytecode
# cache -- needs a term. Those entries live HERE, in their own tables, so
# that nothing consulting the seam registry (``py.datetime``'s wrapper, a
# ``++`` hook) can ever convert a quantity at a seam. ``to_transfer`` and
# ``from_transfer`` consult these tables FIRST and fall through to the seam
# converters, which is what makes a Decimal magnitude or a date inside a
# quantity free: one dispatcher, every registered shape.
#
# The transfer tables are also where a ``Fraction`` lives. It cannot be a
# seam entry: the engine has no arithmetic on an ``rdiv`` term yet (that is
# sequenced with the CLP(Q) C port), so a divided money value crossing a
# seam as a term would silently stop computing.
#
# Spec: docs/superpowers/specs/2026-09-16-quantity-transfer-form-design.md
#
# ``TO_TRANSFER`` / ``FROM_TRANSFER`` themselves are defined above, just
# before ``register`` -- see the comment there for why.


def register_transfer(cls: type, functor: str, to_fn, from_fn) -> None:
    """Add a transfer-only conversion. OVERRIDING IS REFUSED, and so is
    shadowing a SEAM entry: one class, one shape, whichever layer owns it."""
    if cls in TO_TRANSFER or cls in TO_TERM:
        raise ValueError(
            f"register_transfer: {cls.__name__} already has a conversion; "
            f"overriding is not allowed")
    if functor in FROM_TRANSFER or functor in FROM_TERM:
        raise ValueError(
            f"register_transfer: functor {functor!r} is already registered; "
            f"overriding is not allowed")
    TO_TRANSFER[cls] = to_fn
    FROM_TRANSFER[functor] = from_fn


def _fraction_to_term(f: Fraction):
    """``Fraction`` -> ``('rdiv', N, D)``, always in lowest terms with the
    sign on the numerator -- except an INTEGRAL Fraction, which emits as a
    plain int. That is the engine's own rule, the same choke-point
    ``_decimal_to_term`` already applies to a scale-less Decimal: an
    integral rational presents as an int. It also keeps ``D > 1`` a true
    invariant of the wire form, since a bare Fraction arithmetic result
    (``Fraction(1, 3) + Fraction(2, 3)``) can land on a whole number without
    ever being constructed as one."""
    if f.denominator == 1:
        return f.numerator
    return ("rdiv", f.numerator, f.denominator)


def _fraction_from_term(t: tuple) -> Fraction:
    """The reverse. Anything that is not ``rdiv(int, int)`` in lowest terms
    with ``D > 1`` is a look-alike and raises, which ``from_transfer`` turns
    into "unchanged" -- the same policy as ``from_term``."""
    _, n, d = t                              # ValueError if the arity is wrong
    for x in (n, d):
        if type(x) is not int:               # bool is a subclass; refuse it
            raise TypeError("rdiv components must be ints")
    if d <= 1:
        raise ValueError("rdiv denominator must be > 1")
    f = Fraction(n, d)
    if (f.numerator, f.denominator) != (n, d):
        raise ValueError("rdiv is not in lowest terms")
    return f


register_transfer(Fraction, "rdiv", _fraction_to_term, _fraction_from_term)
# RULED 2026-09-17 (Q1) and 2026-09-18 (Q7, option c): a Decimal is a NUMBER
# in the engine, like a Fraction -- the seam passes the object (it is in
# ``_SCALARS``) and ``('decimal', M, S)`` is its TRANSFER form only, beside
# ``rdiv``.  It was in the seam registry until 2026-09-18; nothing in the
# engine consulted that entry (measured: ``to_term``/``from_term`` have no
# engine callers), so the move changes the wire, not a behaviour.
register_transfer(Decimal, "decimal", _decimal_to_term, _decimal_from_term)


def _well_formed_transfer_term(value: tuple) -> bool:
    """True only for a tuple that is ALREADY a well-formed transfer term:
    a registered transfer functor whose components rebuild, or a well-formed
    seam term (date family, decimal). NARROW on purpose, like
    ``_already_a_term``: a head that merely LOOKS registered is a compound
    with a bad payload, and its arguments still need converting -- otherwise
    a live object could ride inside the returned term, which is the one
    thing this layer exists to prevent."""
    if not value or type(value[0]) is not str:
        return False
    rebuild = FROM_TRANSFER.get(value[0])
    if rebuild is not None:
        try:
            rebuild(value)
        except (TypeError, ValueError, OverflowError):
            return False
        return True
    if value[0] == TUPLE_TAG:
        return False                   # a data tuple's payload still converts
    return _already_a_term(value)      # a well-formed date / decimal term


def _map_args(value: tuple, fn) -> tuple:
    """Apply *fn* to a compound's arguments (or a tagged data tuple's
    payload), keeping the head. Returns *value* ITSELF when nothing changed,
    so a term that needed no conversion keeps its identity."""
    args = tuple(fn(e) for e in value[1:])
    if len(args) == len(value) - 1 and all(a is b for a, b in zip(args, value[1:])):
        return value
    return (value[0],) + args


def to_transfer(value: Any) -> Any:
    """*value* as a TRANSFER term, recursively.

    Differs from ``to_term`` in exactly two ways: it consults ``TO_TRANSFER``
    first, and it does NOT wave an engine-owned object through -- a transfer
    is the one place a Quantity must not pass as itself. It is always strict:
    a caller asking for a transfer form has nowhere to put an object.

    The tuple rule: a str-headed tuple is a compound; only an empty or
    non-str-headed tuple is data.
    """
    _ensure_quantity_registered()
    # The transfer table FIRST: a Decimal and a Fraction are scalars at the
    # seam (numbers pass as themselves, Q1) but have a wire form here.
    convert = TO_TRANSFER.get(type(value))
    if convert is not None:
        return convert(value)
    if isinstance(value, _SCALARS):
        return value
    from clausal.logic.variables import Var  # noqa: PLC0415
    if isinstance(value, Var):
        raise TypeError("to_transfer: a logic variable has no transfer form; "
                        "bind it or leave it out of the transferred term")
    if isinstance(value, list):
        return [to_transfer(v) for v in value]
    if isinstance(value, dict):
        return {to_transfer(k): to_transfer(v) for k, v in value.items()}
    if isinstance(value, tuple):
        if not value or type(value[0]) is not str:
            # DATA: a Python tuple, not a term. Tagged so it reads back as one.
            return (TUPLE_TAG,) + tuple(to_transfer(e) for e in value)
        if _well_formed_transfer_term(value):
            return value               # idempotent
        # A COMPOUND (or an already-tagged data tuple): head kept, arguments
        # convert. This is where the transfer layer diverges from the seam's
        # narrow rule on purpose -- it carries ENGINE terms, where every
        # compound is a str-headed tuple, so that is the common case here.
        return _map_args(value, to_transfer)
    if _is_already_engine_term(value):
        # An engine term type with no transfer entry (an AttVar, say). It IS
        # the representation; nothing to convert.
        return value
    return to_term(value, strict=True)


def from_transfer(value: Any) -> Any:
    """A TRANSFER term back to its Python value, recursively.

    ``FROM_TRANSFER`` first, then the seam registry. A term with no registered
    functor, or a look-alike whose components do not fit, comes back
    UNCHANGED -- the same policy as ``from_term``, for the same reason.

    The tuple rule: a str-headed tuple is a compound; only an empty or
    non-str-headed tuple is data.
    """
    _ensure_quantity_registered()
    if isinstance(value, _SCALARS):
        return value
    if isinstance(value, list):
        return [from_transfer(v) for v in value]
    if isinstance(value, dict):
        return {from_transfer(k): from_transfer(v) for k, v in value.items()}
    if type(value) is not tuple or not value or type(value[0]) is not str:
        return value
    if value[0] == TUPLE_TAG:
        return tuple(from_transfer(e) for e in value[1:])
    rebuild = FROM_TRANSFER.get(value[0])
    if rebuild is not None:
        try:
            return rebuild(value)
        except (TypeError, ValueError, OverflowError):
            pass                       # a look-alike: read it as a compound
    seam = from_term(value)
    if seam is not value:
        return seam                    # a registered SEAM shape (date, decimal)
    return _map_args(value, from_transfer)   # any other compound: arguments read


# ── the dims slot: dimensions/N OR the atom dimensionless ──────────────────
#
# The dims slot carries TWO functors (spec §3, section-4 answer §4): the
# word ``dimensionless`` already names the concept, so the empty case is that
# atom rather than a degenerate ``('dimensions',)``. The cost is that "the
# dims slot has functor dimensions" is not free -- so it is said HERE, once,
# and every site goes through these two functions.

def _dims_to_term(dims) -> tuple:
    """An atom-keyed dims mapping -> its transfer term, SORTED by atom.

    The stored dict is order-insensitive; the sort is a boundary step so an
    emitted term is one term. ``dims.items()`` pairs are already
    ``('metre', 1)`` -- functor-first ``metre(1)`` -- so nothing is rebuilt."""
    if not dims:
        return ("dimensionless",)
    return ("dimensions", *sorted(dims.items()))


def _dims_from_term(t) -> dict:
    """The reverse: ``('dimensionless',)`` or ``('dimensions', *pairs)`` ->
    an atom-keyed dict. Order-insensitive. Raises on anything else."""
    if type(t) is not tuple or not t or type(t[0]) is not str:
        raise TypeError("dims slot is not a term")
    if t == ("dimensionless",):
        return {}
    if t[0] != "dimensions" or len(t) < 2:
        raise TypeError("dims slot is neither dimensionless nor dimensions/N")
    dims: dict = {}
    for pair in t[1:]:
        if (type(pair) is not tuple or len(pair) != 2
                or type(pair[0]) is not str or type(pair[1]) is not int
                or pair[1] == 0 or pair[0] in dims):
            raise TypeError(f"not a dimension pair: {pair!r}")
        dims[pair[0]] = pair[1]
    return dims


# ── Quantity <-> quantity/2 ──────────────────────────────────────────────────
#
# ``Quantity`` is registered lazily, on first use of ``to_transfer`` /
# ``from_transfer`` -- see ``_ensure_quantity_registered`` below -- rather
# than at module load, so that ``clausal.terms`` (imported by everything)
# could itself import this module without a cycle (roborev F7 / review M4).
# The registry stays a LEAF.

def _quantity_to_term(q: "Quantity") -> tuple:
    """``quantity(Magnitude, unit(1, Dims))``. The ratio is ALWAYS 1 on emit:
    the object normalised at construction and keeps no ratio, so ``5
    kilometre`` emits as 5000 metre. The magnitude goes through
    ``to_transfer`` so a Decimal keeps its scale and a Fraction becomes
    rdiv."""
    return ("quantity", to_transfer(q.value), ("unit", 1, _dims_to_term(q.dims)))


_NUMBER_TYPES = (int, float, Decimal, Fraction)


def _transfer_number(x):
    """A magnitude or ratio slot -> a Python number, or raise."""
    n = from_transfer(x)
    if isinstance(n, bool) or not isinstance(n, _NUMBER_TYPES):
        raise TypeError(f"not a number term: {x!r}")
    return n


def _quantity_from_term(t: tuple) -> "Quantity":
    """``('quantity', M, ('unit', R, Dims))`` -> the object, with ``R``
    multiplied through EXACTLY: an int magnitude with a Decimal ratio stays
    Decimal, a Fraction with a Fraction stays Fraction (``_num_pair`` is the
    class's own coercion). The object then normalises as it always does --
    an integral Fraction presents as an int, a currency magnitude becomes
    Decimal -- so an emitted term reads back to an EQUAL object."""
    from clausal.terms import Quantity  # noqa: PLC0415
    _, magnitude, unit = t                   # ValueError if the arity is wrong
    if type(unit) is not tuple or len(unit) != 3 or unit[0] != "unit":
        raise TypeError("the unit slot must be unit/2")
    _, ratio, dims_term = unit
    m = _transfer_number(magnitude)
    r = _transfer_number(ratio)
    dims = _dims_from_term(dims_term)
    if type(r) is int and r == 1:
        value = m
    else:
        a, b = Quantity._num_pair(m, r)
        value = a * b
    return Quantity(value, dims)


def _ensure_quantity_registered() -> None:
    """Register the Quantity converters on first use. ``clausal.terms`` is
    imported HERE, not at module scope, so this registry stays a leaf that
    ``clausal.terms`` could itself import without a cycle."""
    from clausal.terms import Quantity  # noqa: PLC0415
    if Quantity not in TO_TRANSFER:
        register_transfer(Quantity, "quantity", _quantity_to_term, _quantity_from_term)


#: Left alone.  ``bool`` is listed for the reader, not for the code: it is a
#: subclass of ``int`` and would pass anyway, but a future edit that narrows the
#: int case must not silently widen ``True`` to ``1``.
# Decimal and Fraction are NUMBERS (RULED 2026-09-17 Q1): the seam passes
# them as it passes an int; their cells are transfer forms (see below).
_SCALARS = (bool, int, float, str, bytes, bytearray, complex, type(None), Decimal, Fraction)


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
    if type(value) is str:
        # STAGE 1 (spec 2026-09-18 §3): a Python str crossing the seam is
        # TEXT today, and text is the chars carrier -- so a str becomes the
        # carrier here (a dict KEY too: a string key is already a different
        # key from the atom of the same spelling).  Stage 2 makes it the ATOM.
        return chars(value)
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
    if is_chars(value):
        return chars_text(value)       # stage 1: the carrier comes back as the str
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
