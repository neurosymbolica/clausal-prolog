"""clausal.modules.py.datetime — Date and time predicates for Clausal.

Provides relational predicates for constructing, decomposing, and
manipulating dates and times.  Import via::

    -import_from(py.datetime, [Now, Today, Date, Time, DateTime,
                             TimeDelta, DateAdd, DateSub, DateDiff,
                             DaysBetween, FormatDate, ParseDate,
                             DateOf, DayOfWeek, DateBetween])

Or via module import::

    -import_module(py.datetime)
    # then use py.datetime.Now(...), py.datetime.Date(...), etc.

Python interop
--------------
All predicates produce and consume **real Python datetime objects**:

- ``Date/4``      ↔ ``datetime.date``
- ``Time/4``      ↔ ``datetime.time``
- ``DateTime/7``  ↔ ``datetime.datetime``
- ``TimeDelta/3`` ↔ ``datetime.timedelta``

These are not custom term types — they are the actual Python classes from
the ``datetime`` module.  Unification uses Python's native ``==``.  Any
``datetime`` method can be called via ``++()`` interop on the resulting
values, e.g. ``S_ is ++D_.isoformat()`` or ``++D_.strftime("%Y-%m-%d")``.

Bidirectional predicates
------------------------
``Date/4``, ``Time/4``, ``DateTime/7``, ``TimeDelta/3``, and ``DateOf/2``
are bidirectional: pass ground components to construct, or pass a ground
datetime object to decompose into components.

Prefer these declarative predicates over ``++`` Python escapes:
``DateOf(DT, D)`` instead of ``D is ++DT.date()``; ``TimeDelta(N, _, TD)``
instead of ``N is ++TD.days``; ``FormatDate(DT, "%Y-%m-%d", S)`` instead
of ``S is ++DT.isoformat()``; and ``DaysBetween(A, B, N)`` for a direct
integer day count instead of ``DateDiff(A, B, TD), TimeDelta(N, _, TD)``.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline
_dt = _import_stdlib("datetime")

from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Now / Today ──────────────────────────────────────────────────────────


def _now_1(dt, trail, k):
    """Now/1: bind dt to datetime.datetime.now()."""
    if unify(dt, _dt.datetime.now(), trail):
        yield None


def _now_utc_1(dt, trail, k):
    """NowUTC/1: bind dt to datetime.datetime.now(datetime.timezone.utc)."""
    if unify(dt, _dt.datetime.now(_dt.timezone.utc), trail):
        yield None


def _today_1(d, trail, k):
    """Today/1: bind d to datetime.date.today()."""
    if unify(d, _dt.date.today(), trail):
        yield None


# ── Date/4 — construct or decompose datetime.date ───────────────────────


def _date_4(year, month, day, dt, trail, k):
    """Date/4: bidirectional — Date(Y, M, D, DateObj).

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


# ── Time/4 — construct or decompose datetime.time ───────────────────────


def _time_4(hour, minute, second, t, trail, k):
    """Time/4: bidirectional — Time(H, M, S, TimeObj).

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


# ── DateTime/7 — construct or decompose datetime.datetime ────────────────


def _datetime_7(year, month, day, hour, minute, second, dt, trail, k):
    """DateTime/7: bidirectional — DateTime(Y, Mo, D, H, Mi, S, DtObj).

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


# ── TimeDelta/3 — construct or decompose datetime.timedelta ──────────────


def _timedelta_3(days, seconds, td, trail, k):
    """TimeDelta/3: bidirectional — TimeDelta(Days, Seconds, TdObj).

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


# ── DateAdd/3 — date + timedelta → result ────────────────────────────────


def _date_add_3(d, td, result, trail, k):
    """DateAdd/3: DateAdd(DateOrDatetime, Timedelta, Result).

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


# ── DateSub/3 — date - timedelta → result ────────────────────────────────


def _date_sub_3(d, td, result, trail, k):
    """DateSub/3: DateSub(DateOrDatetime, Timedelta, Result).

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


# ── DateDiff/3 — date - date → timedelta ─────────────────────────────────


def _date_diff_3(d1, d2, td, trail, k):
    """DateDiff/3: DateDiff(D1, D2, Timedelta).

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


# ── FormatDate/3 — strftime ──────────────────────────────────────────────


def _format_date_3(dt, fmt, s, trail, k):
    """FormatDate/3: FormatDate(DateOrDatetime, FormatStr, ResultStr).

    ResultStr = dt.strftime(fmt).
    """
    dt, fmt, s = deref(dt), deref(fmt), deref(s)
    if not hasattr(dt, 'strftime'):
        return
    try:
        out = dt.strftime(str(fmt))
    except (TypeError, ValueError):
        return
    if unify(s, out, trail):
        yield None


# ── ParseDate/3 — strptime ──────────────────────────────────────────────


def _parse_date_3(s, fmt, dt, trail, k):
    """ParseDate/3: ParseDate(String, FormatStr, DatetimeObj).

    DatetimeObj = datetime.datetime.strptime(s, fmt).
    """
    s, fmt, dt = deref(s), deref(fmt), deref(dt)
    try:
        out = _dt.datetime.strptime(str(s), str(fmt))
    except (TypeError, ValueError):
        return
    if unify(dt, out, trail):
        yield None


# ── DateOf/2 — datetime ↔ date ──────────────────────────────────────────


def _date_of_2(dt_obj, d, trail, k):
    """DateOf/2: bidirectional — DateOf(DateTime, Date).

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


# ── DaysBetween/3 — integer day count ────────────────────────────────────


def _days_between_3(d1, d2, n, trail, k):
    """DaysBetween/3: DaysBetween(DateA, DateB, N).

    N = whole days in ``DateA - DateB`` (``(DateA - DateB).days``).  The
    one-goal form of ``DateDiff(A, B, TD), TimeDelta(N, _, TD)`` — for
    datetimes the count is the timedelta's whole-day component, matching
    DateDiff.  With N bound this acts as a check.
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


# ── DayOfWeek/2 — weekday ───────────────────────────────────────────────


def _day_of_week_2(d, dow, trail, k):
    """DayOfWeek/2: DayOfWeek(DateOrDatetime, Weekday).

    Weekday = d.weekday() (0=Monday, 6=Sunday).
    """
    d, dow = deref(d), deref(dow)
    if not isinstance(d, (_dt.date, _dt.datetime)):
        return
    if unify(dow, d.weekday(), trail):
        yield None


# ── DateBetween/3 — nondeterministic date range ─────────────────────────


def _date_between_3(this_generator, _proceed, _fail, _catcher, start, end, d, trail):
    """DateBetween/3: nondeterministic — generates each date from start to end.

    DateBetween(Start, End, D) succeeds once for each date D in [Start, End].
    """
    start, end = deref(start), deref(end)
    if not isinstance(start, _dt.date) or not isinstance(end, _dt.date):
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


# ── Build and export predicate objects ───────────────────────────────────

Now = ModulePredicate("Now", module="datetime")
Now._register(1, simple_to_trampoline(_now_1))

NowUTC = ModulePredicate("NowUTC", module="datetime")
NowUTC._register(1, simple_to_trampoline(_now_utc_1))

Today = ModulePredicate("Today", module="datetime")
Today._register(1, simple_to_trampoline(_today_1))

Date = ModulePredicate("Date", module="datetime")
Date._register(4, simple_to_trampoline(_date_4))

Time = ModulePredicate("Time", module="datetime")
Time._register(4, simple_to_trampoline(_time_4))

DateTime = ModulePredicate("DateTime", module="datetime")
DateTime._register(7, simple_to_trampoline(_datetime_7))

TimeDelta = ModulePredicate("TimeDelta", module="datetime")
TimeDelta._register(3, simple_to_trampoline(_timedelta_3))

DateAdd = ModulePredicate("DateAdd", module="datetime")
DateAdd._register(3, simple_to_trampoline(_date_add_3))

DateSub = ModulePredicate("DateSub", module="datetime")
DateSub._register(3, simple_to_trampoline(_date_sub_3))

DateDiff = ModulePredicate("DateDiff", module="datetime")
DateDiff._register(3, simple_to_trampoline(_date_diff_3))

FormatDate = ModulePredicate("FormatDate", module="datetime")
FormatDate._register(3, simple_to_trampoline(_format_date_3))

ParseDate = ModulePredicate("ParseDate", module="datetime")
ParseDate._register(3, simple_to_trampoline(_parse_date_3))

DateOf = ModulePredicate("DateOf", module="datetime")
DateOf._register(2, simple_to_trampoline(_date_of_2))

DaysBetween = ModulePredicate("DaysBetween", module="datetime")
DaysBetween._register(3, simple_to_trampoline(_days_between_3))

DayOfWeek = ModulePredicate("DayOfWeek", module="datetime")
DayOfWeek._register(2, simple_to_trampoline(_day_of_week_2))

DateBetween = ModulePredicate("DateBetween", module="datetime")
DateBetween._register(3, _date_between_3)
