"""clausal.modules.py.datetime — Date and time predicates for Clausal.

Provides relational predicates for constructing, decomposing, and
manipulating dates and times.  Import via::

    -import_from(date_time, [now, today, date, time, datetime,
                             timedelta, date_add, date_sub, date_diff,
                             days_between, datetime_string,
                             date_of, weekday, date_between])

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
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline
_dt = _import_stdlib("datetime")

from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── now / today ──────────────────────────────────────────────────────────


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


# ── date/4 — construct or decompose datetime.date ───────────────────────


def _date_4(year, month, day, dt, trail, k):
    """date/4: bidirectional — date(Y, M, D, DateObj).

    If DateObj is unbound: construct datetime.date(Y, M, D) → DateObj.
    If DateObj is a datetime.date: decompose → Y, M, D.
    """
    year, month, day, dt = deref(year), deref(month), deref(day), deref(dt)
    if is_var(dt):
        # construct mode — all components must be ground
        try:
            d = _dt.date(int(year), int(month), int(day))
        except (TypeError, ValueError):
            return
        if unify(dt, d, trail):
            yield None
    elif isinstance(dt, _dt.date) and not isinstance(dt, _dt.datetime):
        # decompose mode
        mark = trail.mark()
        if (unify(year, dt.year, trail)
                and unify(month, dt.month, trail)
                and unify(day, dt.day, trail)):
            yield None
        else:
            trail.undo(mark)
    elif isinstance(dt, _dt.datetime):
        # decompose datetime → date components
        mark = trail.mark()
        if (unify(year, dt.year, trail)
                and unify(month, dt.month, trail)
                and unify(day, dt.day, trail)):
            yield None
        else:
            trail.undo(mark)


# ── time/4 — construct or decompose datetime.time ───────────────────────


def _time_4(hour, minute, second, t, trail, k):
    """time/4: bidirectional — time(H, M, S, TimeObj).

    If TimeObj is unbound: construct datetime.time(H, M, S) → TimeObj.
    If TimeObj is a datetime.time: decompose → H, M, S.
    """
    hour, minute, second, t = deref(hour), deref(minute), deref(second), deref(t)
    if is_var(t):
        try:
            tm = _dt.time(int(hour), int(minute), int(second))
        except (TypeError, ValueError):
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


# ── datetime/7 — construct or decompose datetime.datetime ────────────────


def _datetime_7(year, month, day, hour, minute, second, dt, trail, k):
    """datetime/7: bidirectional — datetime(Y, Mo, D, H, Mi, S, DtObj).

    If DtObj is unbound: construct datetime.datetime(Y, Mo, D, H, Mi, S) → DtObj.
    If DtObj is a datetime.datetime: decompose → Y, Mo, D, H, Mi, S.
    """
    year, month, day = deref(year), deref(month), deref(day)
    hour, minute, second, dt = deref(hour), deref(minute), deref(second), deref(dt)
    if is_var(dt):
        try:
            obj = _dt.datetime(int(year), int(month), int(day),
                               int(hour), int(minute), int(second))
        except (TypeError, ValueError):
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


# ── timedelta/3 — construct or decompose datetime.timedelta ──────────────


def _timedelta_3(days, seconds, td, trail, k):
    """timedelta/3: bidirectional — timedelta(Days, Seconds, TdObj).

    If TdObj is unbound: construct datetime.timedelta(days, seconds) → TdObj.
    If TdObj is a datetime.timedelta: decompose → Days, Seconds.
    """
    days, seconds, td = deref(days), deref(seconds), deref(td)
    if is_var(td):
        try:
            obj = _dt.timedelta(days=int(days),
                                seconds=int(seconds) if not is_var(seconds) else 0)
        except (TypeError, ValueError):
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


# ── date_add/3 — date + timedelta → result ────────────────────────────────


def _date_add_3(d, td, result, trail, k):
    """date_add/3: date_add(DateOrDatetime, Timedelta, Result).

    Result = D + TD.
    """
    d, td, result = deref(d), deref(td), deref(result)
    if not isinstance(d, (_dt.date, _dt.datetime)):
        return
    if not isinstance(td, _dt.timedelta):
        return
    try:
        out = d + td
    except (TypeError, OverflowError):
        return
    if unify(result, out, trail):
        yield None


# ── date_sub/3 — date - timedelta → result ────────────────────────────────


def _date_sub_3(d, td, result, trail, k):
    """date_sub/3: date_sub(DateOrDatetime, Timedelta, Result).

    Result = D - TD.
    """
    d, td, result = deref(d), deref(td), deref(result)
    if not isinstance(d, (_dt.date, _dt.datetime)):
        return
    if not isinstance(td, _dt.timedelta):
        return
    try:
        out = d - td
    except (TypeError, OverflowError):
        return
    if unify(result, out, trail):
        yield None


# ── date_diff/3 — date - date → timedelta ─────────────────────────────────


def _date_diff_3(d1, d2, td, trail, k):
    """date_diff/3: date_diff(D1, D2, Timedelta).

    Timedelta = D1 - D2.
    """
    d1, d2, td = deref(d1), deref(d2), deref(td)
    if not isinstance(d1, (_dt.date, _dt.datetime)):
        return
    if not isinstance(d2, (_dt.date, _dt.datetime)):
        return
    try:
        out = d1 - d2
    except TypeError:
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

    Format must be a ground string in both modes.  Note: ``strftime`` accepts a
    ``date``/``time``/``datetime`` but ``strptime`` always yields a ``datetime``,
    so a date round-trips to a midnight datetime.
    """
    dt_obj, s, fmt = deref(dt_obj), deref(s), deref(fmt)
    if not isinstance(fmt, str):
        return
    if hasattr(dt_obj, 'strftime'):
        try:
            out = dt_obj.strftime(fmt)
        except (TypeError, ValueError):
            return
        if unify(s, out, trail):
            yield None
    elif is_var(dt_obj) and isinstance(s, str):
        try:
            out = _dt.datetime.strptime(s, fmt)
        except (TypeError, ValueError):
            return
        if unify(dt_obj, out, trail):
            yield None


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
    elif is_var(dt_obj) and isinstance(d, _dt.date):
        # inverse — date → midnight datetime.  ``datetime`` is a subclass
        # of ``date``; normalise through the calendar components so a
        # datetime passed here collapses to midnight of its day.
        out = _dt.datetime(d.year, d.month, d.day)
        if unify(dt_obj, out, trail):
            yield None


# ── days_between/3 — integer day count ────────────────────────────────────


def _days_between_3(d1, d2, n, trail, k):
    """days_between/3: days_between(DateA, DateB, N).

    N = whole days in ``DateA - DateB`` (``(DateA - DateB).days``).  The
    one-goal form of ``date_diff(A, B, TD), timedelta(N, _, TD)`` — for
    datetimes the count is the timedelta's whole-day component, matching
    date_diff.  With N bound this acts as a check.
    """
    d1, d2, n = deref(d1), deref(d2), deref(n)
    if not isinstance(d1, (_dt.date, _dt.datetime)):
        return
    if not isinstance(d2, (_dt.date, _dt.datetime)):
        return
    try:
        days = (d1 - d2).days
    except TypeError:
        # mixing naive date and datetime, etc.
        return
    if unify(n, days, trail):
        yield None


# ── weekday/2 — weekday ─────────────────────────────────────────────────


def _weekday_2(d, dow, trail, k):
    """weekday/2: weekday(DateOrDatetime, Weekday).

    Weekday = d.weekday() (0=Monday, 6=Sunday).
    """
    d, dow = deref(d), deref(dow)
    if not isinstance(d, (_dt.date, _dt.datetime)):
        return
    if unify(dow, d.weekday(), trail):
        yield None


# ── date_between/3 — nondeterministic date range ─────────────────────────


def _date_between_3(this_generator, _proceed, _fail, _catcher, start, end, d, trail):
    """date_between/3: nondeterministic — generates each date from start to end.

    date_between(Start, End, D) succeeds once for each date D in [Start, End].
    """
    start, end = deref(start), deref(end)
    if not isinstance(start, _dt.date) or not isinstance(end, _dt.date):
        yield (_fail, DONE)
        return
    # A plain date and a datetime are not comparable (datetime subclasses
    # date, so the isinstance checks above both pass) — fail cleanly (F016).
    if isinstance(start, _dt.datetime) != isinstance(end, _dt.datetime):
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
        except (OverflowError, OSError, ValueError):
            return
        if unify(stamp, out, trail):
            yield None
    elif is_var(dt_obj) and isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
        try:
            out = _dt.datetime.fromtimestamp(stamp)
        except (OverflowError, OSError, ValueError, TypeError):
            return
        if unify(dt_obj, out, trail):
            yield None


# ── ISO-8601 helpers — bidirectional, via isoformat/fromisoformat ────────


def _datetime_string_iso_2(dt_obj, s, trail, k):
    """datetime_string_iso/2: bidirectional ISO-8601 datetime.

    Forward (DateTime is a ``datetime``): String = DateTime.isoformat().
    Inverse (DateTime unbound, String a string): DateTime =
    datetime.fromisoformat(String).
    """
    dt_obj, s = deref(dt_obj), deref(s)
    if isinstance(dt_obj, _dt.datetime):
        if unify(s, dt_obj.isoformat(), trail):
            yield None
    elif is_var(dt_obj) and isinstance(s, str):
        try:
            out = _dt.datetime.fromisoformat(s)
        except (TypeError, ValueError):
            return
        if unify(dt_obj, out, trail):
            yield None


def _date_string_iso_2(d_obj, s, trail, k):
    """date_string_iso/2: bidirectional ISO-8601 date (YYYY-MM-DD).

    Forward (Date is a ``date`` and not a ``datetime``): String = Date.isoformat().
    Inverse (Date unbound, String a string): Date = date.fromisoformat(String).
    """
    d_obj, s = deref(d_obj), deref(s)
    if isinstance(d_obj, _dt.date) and not isinstance(d_obj, _dt.datetime):
        if unify(s, d_obj.isoformat(), trail):
            yield None
    elif is_var(d_obj) and isinstance(s, str):
        try:
            out = _dt.date.fromisoformat(s)
        except (TypeError, ValueError):
            return
        if unify(d_obj, out, trail):
            yield None


# ── Build and export predicate objects ───────────────────────────────────

now = ModulePredicate("now", module="datetime")
now._register(1, simple_to_trampoline(_now_1))

now_utc = ModulePredicate("now_utc", module="datetime")
now_utc._register(1, simple_to_trampoline(_now_utc_1))

today = ModulePredicate("today", module="datetime")
today._register(1, simple_to_trampoline(_today_1))

date = ModulePredicate("date", module="datetime")
date._register(4, simple_to_trampoline(_date_4))

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
