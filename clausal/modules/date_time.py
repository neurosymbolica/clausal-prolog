"""clausal.modules.date_time — Date and time predicates for Clausal.

Provides relational predicates for constructing, decomposing, and
manipulating dates and times.  Import via::

    -import_from(date_time, [Now, Today, Date, Time, DateTime,
                             TimeDelta, DateAdd, DateSub, DateDiff,
                             FormatDate, ParseDate, DayOfWeek,
                             DateBetween])

Or via module import::

    -import_module(date_time)
    # then use date_time.Now(...), date_time.Date(...), etc.

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
``Date/4``, ``Time/4``, ``DateTime/7``, and ``TimeDelta/3`` are
bidirectional: pass ground components to construct, or pass a ground
datetime object to decompose into components.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Callable

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Dispatch adapter (same pattern as regex.py) ───────────────────────────


class _DateTimePredicate:
    """Adapter with ``_get_dispatch()`` for a date_time predicate."""

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"date_time.{self._name}/{arities}"


# ── Simple-mode wrapper ──────────────────────────────────────────────────


def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode fn(*args, trail, k) → trampoline protocol."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


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


def _date_between_3(this_generator, parent, start, end, d, trail):
    """DateBetween/3: nondeterministic — generates each date from start to end.

    DateBetween(Start, End, D) succeeds once for each date D in [Start, End].
    """
    start, end = deref(start), deref(end)
    if not isinstance(start, _dt.date) or not isinstance(end, _dt.date):
        yield (parent, DONE)
        return
    current = start
    one_day = _dt.timedelta(days=1)
    while current <= end:
        mark = trail.mark()
        if unify(d, current, trail):
            yield (parent, None)
        trail.undo(mark)
        current += one_day
    yield (parent, DONE)


# ── Build and export predicate objects ───────────────────────────────────

Now = _DateTimePredicate("Now")
Now._register(1, _simple_to_trampoline(_now_1))

NowUTC = _DateTimePredicate("NowUTC")
NowUTC._register(1, _simple_to_trampoline(_now_utc_1))

Today = _DateTimePredicate("Today")
Today._register(1, _simple_to_trampoline(_today_1))

Date = _DateTimePredicate("Date")
Date._register(4, _simple_to_trampoline(_date_4))

Time = _DateTimePredicate("Time")
Time._register(4, _simple_to_trampoline(_time_4))

DateTime = _DateTimePredicate("DateTime")
DateTime._register(7, _simple_to_trampoline(_datetime_7))

TimeDelta = _DateTimePredicate("TimeDelta")
TimeDelta._register(3, _simple_to_trampoline(_timedelta_3))

DateAdd = _DateTimePredicate("DateAdd")
DateAdd._register(3, _simple_to_trampoline(_date_add_3))

DateSub = _DateTimePredicate("DateSub")
DateSub._register(3, _simple_to_trampoline(_date_sub_3))

DateDiff = _DateTimePredicate("DateDiff")
DateDiff._register(3, _simple_to_trampoline(_date_diff_3))

FormatDate = _DateTimePredicate("FormatDate")
FormatDate._register(3, _simple_to_trampoline(_format_date_3))

ParseDate = _DateTimePredicate("ParseDate")
ParseDate._register(3, _simple_to_trampoline(_parse_date_3))

DayOfWeek = _DateTimePredicate("DayOfWeek")
DayOfWeek._register(2, _simple_to_trampoline(_day_of_week_2))

DateBetween = _DateTimePredicate("DateBetween")
DateBetween._register(3, _date_between_3)
