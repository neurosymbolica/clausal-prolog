"""clausal.modules.py.datetime — Date and time predicates for Clausal.

Provides relational predicates for constructing, decomposing, and
manipulating dates and times.  Import via::

    -import_from(date_time, [now, today, date, time, datetime,
                             timedelta, date_add, date_sub, date_diff,
                             days_between, datetime_string,
                             date_of, weekday, date_between,
                             date_max, date_min, ordinal])

Or via module import::

    -import_module(py.datetime)
    # then use py.datetime.now(...), py.datetime.date(...), etc.

Python interop
--------------
All predicates produce and consume **real Python datetime objects**:

- ``date/4``      ↔ ``datetime.date``
- ``time/4``      ↔ ``datetime.time``
- ``datetime/7``  ↔ ``datetime.datetime``
- ``timedelta/3`` ↔ ``datetime.timedelta``

These are not custom term types — they are the actual Python classes from
the ``datetime`` module.  Unification uses Python's native ``==``.  Any
``datetime`` method can be called via ``++()`` interop on the resulting
values, e.g. ``S_ is ++D_.isoformat()`` or ``++D_.strftime("%Y-%m-%d")``.

Bidirectional predicates
------------------------
``date/4``, ``time/4``, ``datetime/7``, ``timedelta/3``, and ``date_of/2``
are bidirectional: pass ground components to construct, or pass a ground
datetime object to decompose into components.

Prefer these declarative predicates over ``++`` Python escapes:
``date_of(DT, D)`` instead of ``D is ++DT.date()``; ``timedelta(N, _, TD)``
instead of ``N is ++TD.days``; ``datetime_string(DT, S, "%Y-%m-%d")``
instead of ``S is ++DT.isoformat()``; and ``days_between(A, B, N)`` for a
direct integer day count instead of ``date_diff(A, B, TD), timedelta(N, _, TD)``.

Ordering
--------
``date``, ``time`` and ``datetime`` values are orderable with the standard
comparison operators ``<``, ``>``, ``<=``, ``>=`` and sort chronologically
through ``sort/2``, ``msort/2``, ``min_list/2`` and ``max_list/2`` -- two
values of the SAME kind.  A ``date`` against a ``datetime`` does NOT raise
today: the two are different terms, and the comparison is decided by the
standard order of terms, not chronologically (``date(2030, 1, 1) < DT``
holds for a ``datetime`` in 2020).  Convert with ``date_of/2`` before
comparing.  (docs/date_time.md says the same.)
"""

from __future__ import annotations

from clausal.modules.py import (
    text_result,   # stage 1: a str result is the chars carrier
    ModulePredicate,
    _import_stdlib,
    expect_type as _expect_type,
    note_mismatch,
    note_rejected_call,
    simple_to_trampoline,
    to_text,
)
_dt = _import_stdlib("datetime")

from typing import Any

from clausal.logic.variables import (  # noqa: F401
    Var, deref as _deref, is_var, unify as _unify, walk as _walk,
)
from clausal.logic.builtins._helpers import _is_ground
from clausal.logic.exceptions import (
    LogicException, domain_error, instantiation_error, type_error)
from clausal.logic.trampoline import DONE


# ── now / today ──────────────────────────────────────────────────────────


# ── THE SEAM: terms in, terms out; Python only in between ──────────────────
#
# RULED 2026-09-15: "We don't need to use Python date and datetime classes any
# more ... Internally, we can call back to Python, but the seam shouldn't need
# dates."  The predicates below still COMPUTE with `datetime`, because that is
# where calendar arithmetic belongs -- they just no longer hand one out.
#
# Done at two choke points rather than at ~36 argument sites: the module-local
# `deref` converts an incoming date TERM to the Python object, and the
# module-local `unify` converts an outgoing Python object back to a term. Every
# predicate in this file then works unchanged, which is also why this diff does
# not touch their bodies.
#
# Emitted shapes carry FULL precision -- `now/1` has microseconds and losing
# them silently would be worse than a wider term. Short forms are ACCEPTED on
# input (a missing trailing microsecond reads as 0), so `timedelta(3, 0)` and
# `timedelta(3, 0, 0)` both work.
# THE ENCODING LIVES IN ``logic.python_terms``, not here. This module used to
# carry its own emit/read tables, which is a SECOND DEFINITION of the same
# encoding -- the drift this lane has paid for three times in one session. The
# registry is now the single source and this module consumes it.
from clausal.logic import python_terms as _pt  # noqa: E402

#: The date family only. NOT ``python_terms.to_term``/``from_term``: those are
#: the GENERAL converters for ``++``, and the general one wraps any tuple as
#: ``('()', ...)`` data -- which would destroy every term passing through this
#: module's seam. The shapes still come from the registry, so there is one
#: definition; what is narrowed here is the SCOPE, not the encoding.
_DATE_TYPES = (_dt.datetime, _dt.date, _dt.time, _dt.timedelta)
_DATE_FUNCTORS = frozenset(("datetime", "date", "time", "timedelta"))


def _dt_to_term(value):
    """A Python datetime value -> its term. Anything else passes through."""
    convert = _pt.TO_TERM.get(type(value))
    if convert is not None and isinstance(value, _DATE_TYPES):
        return convert(value)
    return value


def _term_to_dt(value):
    """A date-family TERM -> the Python object. Anything else passes through."""
    if type(value) is not tuple or not value or type(value[0]) is not str:
        return value
    if value[0] not in _DATE_FUNCTORS:
        return value
    rebuild = _pt.FROM_TERM.get(value[0])
    if rebuild is None:
        return value
    try:
        # WALK the components, not just the outer term.  A cell built while a
        # component was still unbound -- ``Y = 2025, ordinal(date(Y, 3, 1), N)``
        # builds ``('date', Y, 3, 1)`` and binds Y afterwards -- arrives here
        # holding the BOUND Var, which ``datetime.date`` rejects with a
        # TypeError.  Without the walk that rejection read as "not a date"
        # and every predicate below failed the goal silently.
        return rebuild(_walk(value))
    except (TypeError, ValueError, OverflowError):
        return value                   # the ORIGINAL: ``is not`` discriminates


def _is_dt_term(value) -> bool:
    """A cell whose functor is one of the date family's (``date/3``, ...)."""
    return (type(value) is tuple and len(value) > 1
            and type(value[0]) is str and value[0] in _DATE_FUNCTORS)


def _is_open(value) -> bool:
    """An argument an OUTPUT may still be unified into: an unbound variable,
    or a date-family term with an unbound component (``date(Y, M, D)``)."""
    return is_var(value) or (_is_dt_term(value) and not _is_ground(value))


def _reject_dt_term(value, pred) -> None:
    """Raise for a date-family TERM that did not convert to its value.

    Such a term names a date (the caller wrote the functor) but is not one, so
    failing the goal would be a silent wrong answer.  Unbound component ->
    ``instantiation_error``; a component of the wrong type ->
    ``type_error(integer, Term)`` (``number`` for ``timedelta``); right types
    but no such value -> ``domain_error(<functor>, Term)`` -- the same terms
    ``date/3`` raises when it is constructed from bad components.  A term that
    DID convert, and anything else, returns: the caller's ordinary type guard
    decides.
    """
    if not _is_dt_term(value):
        return
    if not _is_ground(value):
        raise LogicException(instantiation_error(pred))
    try:
        _pt.FROM_TERM[value[0]](_walk(value))
    except TypeError:
        raise LogicException(type_error(
            "number" if value[0] == "timedelta" else "integer",
            _walk(value), pred)) from None
    except (ValueError, OverflowError):
        raise LogicException(
            domain_error(value[0], _walk(value), pred)) from None


def expect_type(value, types, pred, *, expected=None, arg=None) -> bool:  # noqa: F811
    """The shared py-interop guard, plus :func:`_reject_dt_term`: a value of
    the wrong class still FAILS the goal with a diagnostic note (the module
    convention), but a date-family term that is not a date RAISES."""
    if isinstance(value, types):
        return True
    _reject_dt_term(value, pred)
    return _expect_type(value, types, pred, expected=expected, arg=arg)


def date_term_to_python(value):
    """PUBLIC: a date-family TERM -> its Python value; anything else unchanged.

    Exposed for callers outside the engine that have to tell a date term from a
    look-alike container -- notably the eval harness's ``profile_terms``, which
    recurses into tuples ELEMENTWISE and would otherwise try to resolve ``date``
    as an atom on a rulebase that never declared it.

    ``cells.is_cell`` does NOT discriminate: ``('date', 2023, 6, 1)`` and a
    profile tuple ``('alpha', 'beta')`` are both cells. This does, because it
    requires the components to be well formed -- and it is the SAME function the
    engine converts with, so a caller's rule cannot drift from the engine's.
    ``date_term_to_python(x) is not x`` is the discrimination test.
    """
    return _term_to_dt(value)


def deref(value):  # noqa: F811 -- deliberately shadows the import above
    """``variables.deref`` then term->Python, so every predicate below reads
    a Python value whatever the caller wrote."""
    return _term_to_dt(_deref(value))


def unify(a, b, trail):  # noqa: F811 -- deliberately shadows the import above
    """``variables.unify`` with Python->term on the way out, so no predicate
    below can hand a Python datetime across the seam."""
    return _unify(_dt_to_term(a), _dt_to_term(b), trail)



def _now_1(dt, trail, k):
    """now/1: bind dt to datetime.datetime.now()."""
    if unify(dt, _dt.datetime.now(), trail):
        yield None


def _now_utc_1(dt, trail, k):
    """now_utc/1: bind dt to datetime.datetime.now(datetime.timezone.utc)."""
    if unify(dt, _dt.datetime.now(_dt.timezone.utc), trail):
        yield None


def _today_1(d, trail, k):
    """today/1: bind d to datetime.date.today()."""
    if unify(d, _dt.date.today(), trail):
        yield None


# ── date/3 — the date TERM (the standard representation) ────────────────
#
# `date(Y, M, D)` IS a real datetime.date, and it is bidirectional by
# UNIFICATION rather than by a constructor predicate:
#
#     DATE = date(2026, 1, 15)     construct — ground args
#     DATE = date(Y, M, D)         decompose — DATE bound, components free
#
# That is what makes date/4 redundant: it does both of those modes as a
# 4-place relation, and neither needs a predicate once the term carries
# the value itself.
#
# The value must be a real datetime.date and NOT a compound named `date`.
# A compound compares its arguments in standard order, which for the
# integer-like components is string order — so "15" < "2" < "9" and
# msort/2 returns a WRONG chronological order without raising. A real
# date orders natively and sorts correctly through sort/msort/min_list/
# max_list (see the Ordering note in this module's docstring).


# (``_DatePattern`` -- a ``metaclass=PredicateMeta`` class with a
# hand-rolled ``__unify__`` bridging a pattern to a real ``datetime.date`` and
# an ``_index_transparent`` flag -- was DELETED at W4b-3 slice 7 (2026-09-26),
# and ``arg_index``'s branches reading that flag with it.
# Measured over the full suite first: nothing constructed it, called its
# ``__unify__``, ``isinstance``-tested it or read an attribute of it (0 of
# each; the instrument's positive control fired).  ``date/3`` below builds a
# cell for every mode.  See implementation_plans/w4b3-slice7-datepattern-
# 2026-09-26.md.)


def date(year, month, day):
    """Construct a datetime.date, or a pattern when a component is unbound."""
    y, m, d = _deref(year), _deref(month), _deref(day)
    if is_var(y) or is_var(m) or is_var(d):
        # No pattern class any more. A cell with unbound components IS the
        # pattern: ``("date", Y, M, D)`` unifies against a ground
        # ``("date", 2026, 1, 15)`` and binds Y/M/D natively, so construct and
        # decompose are one mechanism. _DatePattern existed only because a real
        # datetime.date is a FOREIGN type that a cell is not -- it had to
        # hand-roll a __unify__ to bridge the two, and index-transparently at
        # that. Grounding-after-the-fact now works too, which the old KNOWN
        # BOUNDARY could not do.
        return ("date", y, m, d)
    # Ground: hand the components to datetime.date UNCHANGED so it rejects a
    # float with a TypeError instead of int()-truncating 2020.9 to 2020, and
    # rejects (2025, 2, 29) as the non-date it is. Same reasoning as _date_4
    # (F015) -- a bogus date must never be constructible.
    try:
        _dt.date(y, m, d)          # VALIDATE through datetime, then discard:
    except (TypeError, ValueError) as exc:   # rejects 2025-02-29 and floats
        # A term constructor cannot FAIL the way date/4's goal could, so it
        # raises -- but as a proper ISO error term, not a bare Python one.
        # An impossible date is a fact about the PROGRAM, not about Python,
        # and ISO already has a term for it; leaking `ValueError` here would
        # make the one case with a portable meaning the one case that does not
        # translate. `catch(D is date(Y, 2, 29), error(domain_error(date, _),
        # _), fail)` recovers date/4's failure semantics where a caller wants
        # them.
        note_rejected_call("date/3", exc)
        culprit = ("date", y, m, d)
        if isinstance(exc, TypeError):
            # Wrong TYPE of component (a float, a string) -> type_error.
            raise LogicException(
                type_error("integer", culprit, "date/3")) from None
        # Right types, impossible VALUE (month 13, 29 Feb in a common year)
        # -> domain_error. This is the ISO distinction and it is the one a
        # reader needs: a typo in the shape, versus a date that is not a day.
        raise LogicException(
            domain_error("date", culprit, "date/3")) from None
    return ("date", y, m, d)


# ── time/4 — construct or decompose datetime.time ───────────────────────


def _time_4(hour, minute, second, t, trail, k):
    """time/4: bidirectional — time(H, M, S, TimeObj).

    If TimeObj is unbound: construct datetime.time(H, M, S) → TimeObj.
    If TimeObj is a datetime.time: decompose → H, M, S.
    """
    hour, minute, second, t = deref(hour), deref(minute), deref(second), deref(t)
    if _is_open(t):
        # construct mode — pass components through unchanged so datetime.time
        # rejects floats with a TypeError instead of int()-truncating 10.9 to
        # 10 (F015, same treatment as date/4).
        try:
            tm = _dt.time(hour, minute, second)
        except (TypeError, ValueError) as exc:
            # Fully-bound rejections only — see date/4.
            if not (is_var(hour) or is_var(minute) or is_var(second)):
                note_rejected_call("time/4", exc)
            elif not is_var(t):
                # A partial time term and unbound components: neither mode
                # can run, and failing would read as "no such time".
                raise LogicException(instantiation_error("time/4")) from None
            return
        if unify(t, tm, trail):
            yield None
    elif isinstance(t, _dt.time):
        mark = trail.mark()
        if (unify(hour, t.hour, trail)
                and unify(minute, t.minute, trail)
                and unify(second, t.second, trail)):
            yield None
        else:
            trail.undo(mark)
    else:
        expect_type(t, _dt.time, "time/4", arg=4)


# ── datetime/7 — construct or decompose datetime.datetime ────────────────


def _datetime_7(year, month, day, hour, minute, second, dt, trail, k):
    """datetime/7: bidirectional — datetime(Y, Mo, D, H, Mi, S, DtObj).

    If DtObj is unbound: construct datetime.datetime(Y, Mo, D, H, Mi, S) → DtObj.
    If DtObj is a datetime.datetime: decompose → Y, Mo, D, H, Mi, S.
    """
    year, month, day = deref(year), deref(month), deref(day)
    hour, minute, second, dt = deref(hour), deref(minute), deref(second), deref(dt)
    if _is_open(dt):
        # construct mode — pass components through unchanged so
        # datetime.datetime rejects floats with a TypeError instead of
        # int()-truncating them (F015, same treatment as date/4).
        try:
            obj = _dt.datetime(year, month, day, hour, minute, second)
        except (TypeError, ValueError) as exc:
            # Fully-bound rejections only — see date/4.
            if not any(is_var(c) for c in
                       (year, month, day, hour, minute, second)):
                note_rejected_call("datetime/7", exc)
            elif not is_var(dt):
                raise LogicException(
                    instantiation_error("datetime/7")) from None
            return
        if unify(dt, obj, trail):
            yield None
    elif isinstance(dt, _dt.datetime):
        mark = trail.mark()
        if (unify(year, dt.year, trail)
                and unify(month, dt.month, trail)
                and unify(day, dt.day, trail)
                and unify(hour, dt.hour, trail)
                and unify(minute, dt.minute, trail)
                and unify(second, dt.second, trail)):
            yield None
        else:
            trail.undo(mark)
    else:
        expect_type(dt, _dt.datetime, "datetime/7", arg=7)


# ── timedelta/3 — construct or decompose datetime.timedelta ──────────────


def _timedelta_3(days, seconds, td, trail, k):
    """timedelta/3: bidirectional — timedelta(Days, Seconds, TdObj).

    If TdObj is unbound: construct datetime.timedelta(days, seconds) → TdObj.
    If TdObj is a datetime.timedelta: decompose → Days, Seconds.
    """
    days, seconds, td = deref(days), deref(seconds), deref(td)
    if _is_open(td):
        # construct mode — pass components through unchanged (F015). Unlike
        # date/time/datetime, stdlib timedelta legitimately accepts floats
        # and converts them exactly (1.5 days → 1 day 12 h), so floats are
        # supported here rather than rejected — never int()-truncated.
        try:
            obj = _dt.timedelta(days=days,
                                seconds=seconds if not is_var(seconds) else 0)
        except (TypeError, ValueError) as exc:
            # Fully-bound rejections only — see date/4 (seconds is already
            # substituted when unbound, so only days can be a probe Var).
            if not is_var(days):
                note_rejected_call("timedelta/3", exc)
            elif not is_var(td):
                raise LogicException(
                    instantiation_error("timedelta/3")) from None
            return
        if unify(td, obj, trail):
            yield None
    elif isinstance(td, _dt.timedelta):
        mark = trail.mark()
        if (unify(days, td.days, trail)
                and unify(seconds, td.seconds, trail)):
            yield None
        else:
            trail.undo(mark)
    else:
        expect_type(td, _dt.timedelta, "timedelta/3", arg=3)


# ── date_add/3 — date + timedelta → result ────────────────────────────────


def _date_add_3(d, td, result, trail, k):
    """date_add/3: date_add(DateOrDatetime, Timedelta, Result).

    Result = D + TD.
    """
    d, td, result = deref(d), deref(td), deref(result)
    if not expect_type(d, _dt.date, "date_add/3", expected="date or datetime", arg=1):
        return
    if not expect_type(td, _dt.timedelta, "date_add/3", arg=2):
        return
    try:
        out = d + td
    except (TypeError, OverflowError) as exc:
        note_rejected_call("date_add/3", exc)
        return
    if unify(result, out, trail):
        yield None


# ── date_sub/3 — date - timedelta → result ────────────────────────────────


def _date_sub_3(d, td, result, trail, k):
    """date_sub/3: date_sub(DateOrDatetime, Timedelta, Result).

    Result = D - TD.
    """
    d, td, result = deref(d), deref(td), deref(result)
    if not expect_type(d, _dt.date, "date_sub/3", expected="date or datetime", arg=1):
        return
    if not expect_type(td, _dt.timedelta, "date_sub/3", arg=2):
        return
    try:
        out = d - td
    except (TypeError, OverflowError) as exc:
        note_rejected_call("date_sub/3", exc)
        return
    if unify(result, out, trail):
        yield None


# ── date_diff/3 — date - date → timedelta ─────────────────────────────────


def _date_diff_3(d1, d2, td, trail, k):
    """date_diff/3: date_diff(D1, D2, Timedelta).

    Timedelta = D1 - D2.
    """
    d1, d2, td = deref(d1), deref(d2), deref(td)
    if not expect_type(d1, _dt.date, "date_diff/3", expected="date or datetime", arg=1):
        return
    if not expect_type(d2, _dt.date, "date_diff/3", expected="date or datetime", arg=2):
        return
    try:
        out = d1 - d2
    except TypeError as exc:
        note_rejected_call("date_diff/3", exc)
        return
    if unify(td, out, trail):
        yield None


# ── datetime_string/3 — bidirectional strftime/strptime ──────────────────


def _datetime_string_3(dt_obj, s, fmt, trail, k):
    """datetime_string/3: bidirectional — datetime_string(DateTime, String, Format).

    Format mode (DateTime has ``strftime``): String = DateTime.strftime(Format);
    with String bound this is a check.
    Parse mode (DateTime unbound, String a string): DateTime =
    datetime.strptime(String, Format).

    Format must be ground TEXT in both modes -- a string or an ATOM, which is
    the same ``str`` (spec §9.4): a strftime format is a literal handed to a
    library, so ``'%Y-%m-%d'`` and ``"%Y-%m-%d"`` (a string under the chars
    default, an atom under ``-double_quotes(atom)``) both name it.  So is the
    String in parse mode.  Note:
    ``strftime`` accepts a ``date``/``time``/``datetime`` but ``strptime``
    always yields a ``datetime``, so a date round-trips to a midnight
    datetime.
    """
    dt_obj, s, fmt = deref(dt_obj), deref(s), deref(fmt)
    fmt_text = to_text(fmt)
    if fmt_text is None:
        expect_type(fmt, str, "datetime_string/3", arg=3)
        return
    fmt = fmt_text
    if hasattr(dt_obj, 'strftime'):
        try:
            out = dt_obj.strftime(fmt)
        except (TypeError, ValueError) as exc:
            note_rejected_call("datetime_string/3", exc)
            return
        if unify(s, text_result(out), trail):   # stage 1
            yield None
    elif _is_open(dt_obj) and (s_text := to_text(s)) is not None:
        s = s_text
        try:
            out = _dt.datetime.strptime(s, fmt)
        except (TypeError, ValueError) as exc:
            note_rejected_call("datetime_string/3", exc)
            return
        if unify(dt_obj, out, trail):
            yield None
    elif not is_var(dt_obj):
        expect_type(dt_obj, _dt.date, "datetime_string/3",
                    expected="date, time or datetime", arg=1)
    else:
        expect_type(s, str, "datetime_string/3", arg=2)


# ── date_of/2 — datetime ↔ date ──────────────────────────────────────────


def _date_of_2(dt_obj, d, trail, k):
    """date_of/2: bidirectional — date_of(DateTime, Date).

    The clean, declarative replacement for ``++DT.date()``:

    - **Forward** (DateTime is a ``datetime.datetime``): bind Date to its
      calendar date, ``DateTime.date()``.  With Date already bound this
      acts as a check (same date → succeeds).
    - **Inverse** (DateTime unbound, Date a ``datetime.date``): bind
      DateTime to that date at midnight,
      ``datetime.datetime(Y, Mo, D, 0, 0, 0)``.

    Fails if neither argument is usable (e.g. both unbound, or the first
    is a non-datetime value).
    """
    dt_obj, d = deref(dt_obj), deref(d)
    if isinstance(dt_obj, _dt.datetime):
        # forward (or check) — datetime → date
        if unify(d, dt_obj.date(), trail):
            yield None
        return
    if not _is_open(dt_obj):
        expect_type(dt_obj, _dt.datetime, "date_of/2", arg=1)
        return
    if isinstance(d, _dt.date):
        # inverse — date → midnight datetime.  ``datetime`` is a subclass
        # of ``date``; normalise through the calendar components so a
        # datetime passed here collapses to midnight of its day.
        out = _dt.datetime(d.year, d.month, d.day)
        if unify(dt_obj, out, trail):
            yield None
    elif not is_var(d):
        expect_type(d, _dt.date, "date_of/2", arg=2)
    elif not is_var(dt_obj):
        # A partial datetime term and no Date: nothing to compute from.
        raise LogicException(instantiation_error("date_of/2"))


# ── days_between/3 — integer day count ────────────────────────────────────


def _days_between_3(d1, d2, n, trail, k):
    """days_between/3: days_between(DateA, DateB, N).

    N = whole days in ``DateA - DateB`` (``(DateA - DateB).days``).  The
    one-goal form of ``date_diff(A, B, TD), timedelta(N, _, TD)`` — for
    datetimes the count is the timedelta's whole-day component, matching
    date_diff.  With N bound this acts as a check.
    """
    d1, d2, n = deref(d1), deref(d2), deref(n)
    if not expect_type(d1, _dt.date, "days_between/3", expected="date or datetime", arg=1):
        return
    if not expect_type(d2, _dt.date, "days_between/3", expected="date or datetime", arg=2):
        return
    try:
        days = (d1 - d2).days
    except TypeError as exc:
        # mixing naive date and datetime, etc.
        note_rejected_call("days_between/3", exc)
        return
    if unify(n, days, trail):
        yield None


# ── date_max/3, date_min/3 — later/earlier of two dates ──────────────────


def _date_max_3(d1, d2, m, trail, k):
    """date_max/3: date_max(DateA, DateB, Max).

    Max = the later of two dates (or datetimes) — the clean form of
    ``M is ++max(D1, D2)``.  With Max bound this acts as a check.  A naive
    date/datetime mix is not comparable in Python; the goal fails rather
    than leaking the TypeError.
    """
    d1, d2, m = deref(d1), deref(d2), deref(m)
    if not expect_type(d1, _dt.date, "date_max/3", expected="date or datetime", arg=1):
        return
    if not expect_type(d2, _dt.date, "date_max/3", expected="date or datetime", arg=2):
        return
    try:
        out = max(d1, d2)
    except TypeError as exc:
        note_rejected_call("date_max/3", exc)
        return
    if unify(m, out, trail):
        yield None


def _date_min_3(d1, d2, m, trail, k):
    """date_min/3: date_min(DateA, DateB, Min).

    Min = the earlier of two dates (or datetimes) — the clean form of
    ``M is ++min(D1, D2)``.  Same modes and failure behaviour as
    ``date_max/3``.
    """
    d1, d2, m = deref(d1), deref(d2), deref(m)
    if not expect_type(d1, _dt.date, "date_min/3", expected="date or datetime", arg=1):
        return
    if not expect_type(d2, _dt.date, "date_min/3", expected="date or datetime", arg=2):
        return
    try:
        out = min(d1, d2)
    except TypeError as exc:
        note_rejected_call("date_min/3", exc)
        return
    if unify(m, out, trail):
        yield None


# ── ordinal/2 — bidirectional proleptic-Gregorian ordinal ─────────────────


def _ordinal_2(d, n, trail, k):
    """ordinal/2: bidirectional — ordinal(Date, N).

    - **Forward** (Date is a ``datetime.date``): bind N to its
      proleptic-Gregorian ordinal, ``Date.toordinal()`` (the clean form of
      ``++D.toordinal()``).  A datetime contributes its calendar day's
      ordinal.  With N bound this acts as a check.
    - **Inverse** (Date unbound, N an integer): bind Date to
      ``date.fromordinal(N)`` — so "every calendar day in [CS, CE]" is
      ``ordinal(CS, A), ordinal(CE, B), numlist(A, B, Ns)`` mapped back
      through the inverse mode.  An out-of-range N fails the goal.

    Fails if neither argument is usable (both unbound, or wrong types).
    """
    d, n = deref(d), deref(n)
    if isinstance(d, _dt.date):
        # forward (or check) — date/datetime → ordinal
        if unify(n, d.toordinal(), trail):
            yield None
        return
    if not _is_open(d):
        expect_type(d, _dt.date, "ordinal/2", expected="date or datetime", arg=1)
        return
    if isinstance(n, int) and not isinstance(n, bool):
        try:
            out = _dt.date.fromordinal(n)
        except (ValueError, OverflowError) as exc:
            note_rejected_call("ordinal/2", exc)
            return
        if unify(d, out, trail):
            yield None
    elif not is_var(n):
        expect_type(n, int, "ordinal/2", arg=2)
    elif not is_var(d):
        # A partial date term (``date(Y, 3, 1)`` with Y unbound) and no N.
        raise LogicException(instantiation_error("ordinal/2"))


# ── weekday/2 — weekday ─────────────────────────────────────────────────


def _weekday_2(d, dow, trail, k):
    """weekday/2: weekday(DateOrDatetime, Weekday).

    Weekday = d.weekday() (0=Monday, 6=Sunday).
    """
    d, dow = deref(d), deref(dow)
    if not expect_type(d, _dt.date, "weekday/2", expected="date or datetime", arg=1):
        return
    if unify(dow, d.weekday(), trail):
        yield None


# ── date_between/3 — nondeterministic date range ─────────────────────────


def _date_between_3(this_generator, _proceed, _fail, _catcher, start, end, d, trail):
    """date_between/3: nondeterministic — generates each date from start to end.

    date_between(Start, End, D) succeeds once for each date D in [Start, End].
    """
    start, end = deref(start), deref(end)
    if (not expect_type(start, _dt.date, "date_between/3", expected="date or datetime", arg=1)
            or not expect_type(end, _dt.date, "date_between/3", expected="date or datetime", arg=2)):
        yield (_fail, DONE)
        return
    # A plain date and a datetime are not comparable (datetime subclasses
    # date, so the isinstance checks above both pass) — fail cleanly (F016).
    if isinstance(start, _dt.datetime) != isinstance(end, _dt.datetime):
        note_mismatch("date_between/3",
                      "was called with a plain date and a datetime — "
                      "not comparable")
        yield (_fail, DONE)
        return
    # Likewise a tz-naive and a tz-aware datetime are not comparable —
    # fail cleanly instead of raising TypeError at `current <= end` (F016).
    if (isinstance(start, _dt.datetime) and isinstance(end, _dt.datetime)
            and (start.tzinfo is None) != (end.tzinfo is None)):
        note_mismatch("date_between/3",
                      "was called with a tz-naive and a tz-aware datetime — "
                      "not comparable")
        yield (_fail, DONE)
        return
    current = start
    one_day = _dt.timedelta(days=1)
    while current <= end:
        mark = trail.mark()
        if unify(d, current, trail):
            yield (_proceed, None)
        trail.undo(mark)
        current += one_day
    yield (_fail, DONE)


# ── timestamp/2 — bidirectional datetime ↔ POSIX epoch ───────────────────


def _timestamp_2(dt_obj, stamp, trail, k):
    """timestamp/2: bidirectional — timestamp(DateTime, Stamp).

    Forward (DateTime is a ``datetime``): Stamp = DateTime.timestamp() (float
    epoch seconds); with Stamp bound this is a check.
    Inverse (DateTime unbound, Stamp a number): DateTime =
    datetime.fromtimestamp(Stamp).  A plain ``date`` has no ``timestamp()``, so
    the forward direction requires a ``datetime``.
    """
    dt_obj, stamp = deref(dt_obj), deref(stamp)
    if isinstance(dt_obj, _dt.datetime):
        try:
            out = dt_obj.timestamp()
        except (OverflowError, OSError, ValueError) as exc:
            note_rejected_call("timestamp/2", exc)
            return
        if unify(stamp, out, trail):
            yield None
    elif _is_open(dt_obj) and isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
        try:
            out = _dt.datetime.fromtimestamp(stamp)
        except (OverflowError, OSError, ValueError, TypeError) as exc:
            note_rejected_call("timestamp/2", exc)
            return
        if unify(dt_obj, out, trail):
            yield None
    elif not is_var(dt_obj):
        expect_type(dt_obj, _dt.datetime, "timestamp/2", arg=1)
    elif isinstance(stamp, bool):
        # bool passes isinstance(int), so expect_type below would pass it
        # silently — but the binding branch above excludes it on purpose.
        note_mismatch("timestamp/2",
                      "was called with bool where int or float is required "
                      "(argument 2)")
    else:
        expect_type(stamp, (int, float), "timestamp/2",
                    expected="int or float", arg=2)


# ── ISO-8601 helpers — bidirectional, via isoformat/fromisoformat ────────


def _datetime_string_iso_2(dt_obj, s, trail, k):
    """datetime_string_iso/2: bidirectional ISO-8601 datetime.

    Forward (DateTime is a ``datetime``): String = DateTime.isoformat().
    Inverse (DateTime unbound, String is TEXT -- a string or an ATOM, spec
    §9.4): DateTime = datetime.fromisoformat(String).
    """
    dt_obj, s = deref(dt_obj), deref(s)
    if isinstance(dt_obj, _dt.datetime):
        if unify(s, text_result(dt_obj.isoformat()), trail):   # stage 1
            yield None
    elif _is_open(dt_obj) and (s_text := to_text(s)) is not None:
        s = s_text
        try:
            out = _dt.datetime.fromisoformat(s)
        except (TypeError, ValueError) as exc:
            note_rejected_call("datetime_string_iso/2", exc)
            return
        if unify(dt_obj, out, trail):
            yield None
    elif not is_var(dt_obj):
        expect_type(dt_obj, _dt.datetime, "datetime_string_iso/2", arg=1)
    else:
        expect_type(s, str, "datetime_string_iso/2", arg=2)


def _date_string_iso_2(d_obj, s, trail, k):
    """date_string_iso/2: bidirectional ISO-8601 date (YYYY-MM-DD).

    Forward (Date is a ``date`` and not a ``datetime``): String = Date.isoformat().
    Inverse (Date unbound, String is TEXT -- a string or an ATOM, spec §9.4):
    Date = date.fromisoformat(String).
    """
    d_obj, s = deref(d_obj), deref(s)
    if isinstance(d_obj, _dt.date) and not isinstance(d_obj, _dt.datetime):
        if unify(s, text_result(d_obj.isoformat()), trail):   # stage 1
            yield None
    elif _is_open(d_obj) and (s_text := to_text(s)) is not None:
        s = s_text
        try:
            out = _dt.date.fromisoformat(s)
        except (TypeError, ValueError) as exc:
            note_rejected_call("date_string_iso/2", exc)
            return
        if unify(d_obj, out, trail):
            yield None
    elif isinstance(d_obj, _dt.datetime):
        note_mismatch("date_string_iso/2",
                      "was called with datetime where a plain date is "
                      "required (argument 1) — use datetime_string_iso/2")
    elif not is_var(d_obj):
        expect_type(d_obj, _dt.date, "date_string_iso/2", arg=1)
    else:
        expect_type(s, str, "date_string_iso/2", arg=2)


# ── Build and export predicate objects ───────────────────────────────────

now = ModulePredicate("now", module="datetime")
now._register(1, simple_to_trampoline(_now_1))

now_utc = ModulePredicate("now_utc", module="datetime")
now_utc._register(1, simple_to_trampoline(_now_utc_1))

today = ModulePredicate("today", module="datetime")
today._register(1, simple_to_trampoline(_today_1))


time = ModulePredicate("time", module="datetime")
time._register(4, simple_to_trampoline(_time_4))

datetime = ModulePredicate("datetime", module="datetime")
datetime._register(7, simple_to_trampoline(_datetime_7))

timedelta = ModulePredicate("timedelta", module="datetime")
timedelta._register(3, simple_to_trampoline(_timedelta_3))

date_add = ModulePredicate("date_add", module="datetime")
date_add._register(3, simple_to_trampoline(_date_add_3))

date_sub = ModulePredicate("date_sub", module="datetime")
date_sub._register(3, simple_to_trampoline(_date_sub_3))

date_diff = ModulePredicate("date_diff", module="datetime")
date_diff._register(3, simple_to_trampoline(_date_diff_3))

datetime_string = ModulePredicate("datetime_string", module="datetime")
datetime_string._register(3, simple_to_trampoline(_datetime_string_3))

date_of = ModulePredicate("date_of", module="datetime")
date_of._register(2, simple_to_trampoline(_date_of_2))

days_between = ModulePredicate("days_between", module="datetime")
days_between._register(3, simple_to_trampoline(_days_between_3))

date_max = ModulePredicate("date_max", module="datetime")
date_max._register(3, simple_to_trampoline(_date_max_3))

date_min = ModulePredicate("date_min", module="datetime")
date_min._register(3, simple_to_trampoline(_date_min_3))

ordinal = ModulePredicate("ordinal", module="datetime")
ordinal._register(2, simple_to_trampoline(_ordinal_2))

weekday = ModulePredicate("weekday", module="datetime")
weekday._register(2, simple_to_trampoline(_weekday_2))

date_between = ModulePredicate("date_between", module="datetime")
date_between._register(3, _date_between_3)

timestamp = ModulePredicate("timestamp", module="datetime")
timestamp._register(2, simple_to_trampoline(_timestamp_2))

datetime_string_iso = ModulePredicate("datetime_string_iso", module="datetime")
datetime_string_iso._register(2, simple_to_trampoline(_datetime_string_iso_2))

date_string_iso = ModulePredicate("date_string_iso", module="datetime")
date_string_iso._register(2, simple_to_trampoline(_date_string_iso_2))
