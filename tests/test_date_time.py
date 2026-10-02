"""Tests for clausal.modules.date_time — Date/time predicates.

All predicates produce and consume real Python datetime objects
(datetime.date, datetime.time, datetime.datetime, datetime.timedelta).
"""

from __future__ import annotations

import datetime as dt
import pytest

from clausal.logic.cells import chars
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.datetime import (
    now, now_utc, today, date, time, datetime, timedelta,
    date_add, date_sub, date_diff, date_between, date_of, days_between,
    weekday, datetime_string, timestamp,
    datetime_string_iso, date_string_iso,
    _now_1, _now_utc_1, _today_1,
    _time_4, _datetime_7, _timedelta_3,
    _date_add_3, _date_sub_3, _date_diff_3,
    _datetime_string_3, _weekday_2,
    _date_of_2, _days_between_3, _timestamp_2,
    _datetime_string_iso_2, _date_string_iso_2,
    _date_max_3, _date_min_3, _ordinal_2,
)
from clausal.logic.trampoline import DONE
from clausal.modules.py.datetime import _dt_to_term as _T
from clausal.modules.py.datetime import _term_to_dt as _P  # py datetime -> its TERM


# ── Helpers ──────────────────────────────────────────────────────────────


def simple_solutions(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail


def trampoline_solutions(pred, *args):
    """Run a trampoline-protocol predicate and collect solution snapshots."""
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


def raised(fn, *args):
    """The error term a simple-mode builtin raises (RULED 2026-10-02: an
    argument of the wrong type raises type_error, an unbound required one
    instantiation_error -- neither fails the goal)."""
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException) as info:
        list(fn(*args, Trail(), None))
    return info.value.term


# ── now / now_utc / today ────────────────────────────────────────────────


class TestNow:
    def test_now_binds_datetime(self):
        # nv
        v = Var()
        results, trail = simple_solutions(_now_1, v)
        assert len(results) == 1
        val = deref(v)
        assert isinstance(_P(val), dt.datetime)

    def test_now_utc_binds_datetime(self):
        # nv
        v = Var()
        results, trail = simple_solutions(_now_utc_1, v)
        assert len(results) == 1
        val = deref(v)
        assert isinstance(_P(val), dt.datetime)
        assert _P(val).tzinfo is not None

    def test_today_binds_date(self):
        # nv
        v = Var()
        results, trail = simple_solutions(_today_1, v)
        assert len(results) == 1
        val = deref(v)
        assert isinstance(_P(val), dt.date)
        assert not isinstance(_P(val), dt.datetime)
        assert val == _T(dt.date.today())


# ── date/4 ──────────────────────────────────────────────────────────────


class TestTime:
    def test_construct(self):
        # nv
        t = Var()
        results, _ = simple_solutions(_time_4, 14, 30, 0, t)
        assert len(results) == 1
        assert deref(t) == _T(dt.time(14, 30, 0))

    def test_decompose(self):
        # nv
        h, m, s = Var(), Var(), Var()
        results, _ = simple_solutions(_time_4, h, m, s, _T(dt.time(14, 30, 45)))
        assert len(results) == 1
        assert deref(h) == 14
        assert deref(m) == 30
        assert deref(s) == 45

    def test_construct_invalid_fails(self):
        # nv
        t = Var()
        results, _ = simple_solutions(_time_4, 25, 0, 0, t)
        assert len(results) == 0

    def test_midnight(self):
        # nv
        t = Var()
        results, _ = simple_solutions(_time_4, 0, 0, 0, t)
        assert len(results) == 1
        assert deref(t) == _T(dt.time(0, 0, 0))


# ── datetime/7 ──────────────────────────────────────────────────────────


class TestDateTime:
    def test_construct(self):
        # nv
        v = Var()
        results, _ = simple_solutions(
            _datetime_7, 2026, 3, 16, 14, 30, 0, v
        )
        assert len(results) == 1
        assert deref(v) == _T(dt.datetime(2026, 3, 16, 14, 30, 0))
        assert type(_P(deref(v))) is dt.datetime

    def test_decompose(self):
        # nv
        y, mo, d, h, mi, s = Var(), Var(), Var(), Var(), Var(), Var()
        results, _ = simple_solutions(
            _datetime_7, y, mo, d, h, mi, s,
            _T(dt.datetime(2026, 3, 16, 14, 30, 45))
        )
        assert len(results) == 1
        assert deref(y) == 2026
        assert deref(mo) == 3
        assert deref(d) == 16
        assert deref(h) == 14
        assert deref(mi) == 30
        assert deref(s) == 45

    def test_construct_invalid_fails(self):
        # nv
        v = Var()
        results, _ = simple_solutions(_datetime_7, 2026, 13, 1, 0, 0, 0, v)
        assert len(results) == 0


# ── timedelta/3 ─────────────────────────────────────────────────────────


class TestTimeDelta:
    def test_construct(self):
        # nv
        v = Var()
        results, _ = simple_solutions(_timedelta_3, 7, 3600, v)
        assert len(results) == 1
        assert deref(v) == _T(dt.timedelta(days=7, seconds=3600))

    def test_construct_days_only(self):
        # nv
        v = Var()
        s = Var()  # seconds unbound → defaults to 0
        results, _ = simple_solutions(_timedelta_3, 7, s, v)
        assert len(results) == 1
        val = deref(v)
        assert _P(val).days == 7

    def test_decompose(self):
        # nv
        days, secs = Var(), Var()
        td = _T(dt.timedelta(days=5, seconds=1234))
        results, _ = simple_solutions(_timedelta_3, days, secs, td)
        assert len(results) == 1
        assert deref(days) == 5
        assert deref(secs) == 1234


# ── date_add/3 ───────────────────────────────────────────────────────────


class TestDateAdd:
    def test_add_days_to_date(self):
        # nv
        r = Var()
        results, _ = simple_solutions(
            _date_add_3, _T(dt.date(2026, 3, 16)), _T(dt.timedelta(days=7)), r
        )
        assert len(results) == 1
        assert deref(r) == _T(dt.date(2026, 3, 23))

    def test_add_to_datetime(self):
        # nv
        r = Var()
        results, _ = simple_solutions(
            _date_add_3,
            _T(dt.datetime(2026, 3, 16, 10, 0, 0)),
            _T(dt.timedelta(hours=3)),
            r,
        )
        assert len(results) == 1
        assert deref(r) == _T(dt.datetime(2026, 3, 16, 13, 0, 0))

    def test_add_non_date_raises(self):
        # nv
        assert raised(_date_add_3, "not-a-date", _T(dt.timedelta(1)), Var()) == \
            ('error', ('type_error', 'date', 'not-a-date'), ('/', 'date_add', 3))

    def test_add_non_timedelta_raises(self):
        # nv
        assert raised(_date_add_3, _T(dt.date(2026, 1, 1)), 7, Var()) == \
            ('error', ('type_error', 'timedelta', 7), ('/', 'date_add', 3))

    def test_add_unbound_timedelta_raises(self):
        # vv -- a required input, not an output
        assert raised(_date_add_3, _T(dt.date(2026, 1, 1)), Var(), Var()) == \
            ('error', 'instantiation_error', ('/', 'date_add', 3))


# ── date_sub/3 ───────────────────────────────────────────────────────────


class TestDateSub:
    def test_sub_days_from_date(self):
        # nv
        r = Var()
        results, _ = simple_solutions(
            _date_sub_3, _T(dt.date(2026, 3, 16)), _T(dt.timedelta(days=10)), r
        )
        assert len(results) == 1
        assert deref(r) == _T(dt.date(2026, 3, 6))

    def test_sub_from_datetime(self):
        # nv
        r = Var()
        results, _ = simple_solutions(
            _date_sub_3,
            _T(dt.datetime(2026, 3, 16, 10, 0, 0)),
            _T(dt.timedelta(hours=5)),
            r,
        )
        assert len(results) == 1
        assert deref(r) == _T(dt.datetime(2026, 3, 16, 5, 0, 0))


# ── date_diff/3 ──────────────────────────────────────────────────────────


class TestDateDiff:
    def test_diff_dates(self):
        # nv
        td = Var()
        results, _ = simple_solutions(
            _date_diff_3, _T(dt.date(2026, 3, 16)), _T(dt.date(2026, 3, 10)), td
        )
        assert len(results) == 1
        assert deref(td) == _T(dt.timedelta(days=6))

    def test_diff_datetimes(self):
        # nv
        td = Var()
        results, _ = simple_solutions(
            _date_diff_3,
            _T(dt.datetime(2026, 3, 16, 12, 0, 0)),
            _T(dt.datetime(2026, 3, 16, 10, 0, 0)),
            td,
        )
        assert len(results) == 1
        assert deref(td) == _T(dt.timedelta(hours=2))

    def test_negative_diff(self):
        # nv
        td = Var()
        results, _ = simple_solutions(
            _date_diff_3, _T(dt.date(2026, 3, 10)), _T(dt.date(2026, 3, 16)), td
        )
        assert len(results) == 1
        assert deref(td) == _T(dt.timedelta(days=-6))

    def test_diff_non_dates_raises(self):
        # nv
        assert raised(_date_diff_3, "a", "b", Var()) == \
            ('error', ('type_error', 'date', 'a'), ('/', 'date_diff', 3))


# ── datetime_string/3 — bidirectional strftime/strptime ─────────────────


class TestDatetimeString:
    def test_format_date(self):
        # nv — format mode
        s = Var()
        results, _ = simple_solutions(
            _datetime_string_3, _T(dt.date(2026, 3, 16)), s, chars("%Y-%m-%d")
        )
        assert len(results) == 1
        assert deref(s) == chars("2026-03-16")

    def test_format_datetime(self):
        # nv
        s = Var()
        results, _ = simple_solutions(
            _datetime_string_3,
            _T(dt.datetime(2026, 3, 16, 14, 30, 0)), s, chars("%Y-%m-%d %H:%M"),
        )
        assert len(results) == 1
        assert deref(s) == chars("2026-03-16 14:30")

    def test_format_time(self):
        # nv
        s = Var()
        results, _ = simple_solutions(
            _datetime_string_3, _T(dt.time(14, 30, 0)), s, chars("%H:%M:%S")
        )
        assert len(results) == 1
        assert deref(s) == chars("14:30:00")

    def test_parse_to_datetime(self):
        # vn — parse mode
        v = Var()
        results, _ = simple_solutions(
            _datetime_string_3, v, chars("2026-03-16 14:30"), chars("%Y-%m-%d %H:%M")
        )
        assert len(results) == 1
        assert deref(v) == _T(dt.datetime(2026, 3, 16, 14, 30))

    def test_check_mode_matches(self):
        # nn — both ground, format matches
        results, _ = simple_solutions(
            _datetime_string_3, _T(dt.date(2026, 3, 16)), chars("2026-03-16"), chars("%Y-%m-%d")
        )
        assert len(results) == 1

    def test_check_mode_mismatch_fails(self):
        # nn
        results, _ = simple_solutions(
            _datetime_string_3, _T(dt.date(2026, 3, 16)), chars("2026-03-17"), chars("%Y-%m-%d")
        )
        assert len(results) == 0

    def test_parse_invalid_fails(self):
        # vn
        v = Var()
        results, _ = simple_solutions(
            _datetime_string_3, v, chars("not-a-date"), chars("%Y-%m-%d")
        )
        assert len(results) == 0

    def test_both_unbound_raises(self):
        # vv
        assert raised(_datetime_string_3, Var(), Var(), chars("%Y-%m-%d")) == \
            ('error', 'instantiation_error', ('/', 'datetime_string', 3))

    def test_unbound_format_raises(self):
        # format arg must be ground
        assert raised(
            _datetime_string_3, _T(dt.date(2026, 3, 16)), Var(), Var()
        ) == ('error', 'instantiation_error', ('/', 'datetime_string', 3))

    def test_date_roundtrips_to_midnight_datetime(self):
        """A date → string → back yields a midnight datetime (documented asymmetry)."""
        # nv then vn
        s = Var()
        simple_solutions(_datetime_string_3, _T(dt.date(2026, 3, 16)), s, chars("%Y-%m-%d"))
        v = Var()
        simple_solutions(_datetime_string_3, v, deref(s), chars("%Y-%m-%d"))
        assert deref(v) == _T(dt.datetime(2026, 3, 16, 0, 0, 0))


# ── weekday/2 ─────────────────────────────────────────────────────────


class TestWeekday:
    def test_weekday(self):
        # nv
        dow = Var()
        results, _ = simple_solutions(
            _weekday_2, _T(dt.date(2026, 3, 16)), dow  # Monday
        )
        assert len(results) == 1
        assert deref(dow) == 0  # Monday = 0

    def test_sunday(self):
        # nv
        dow = Var()
        results, _ = simple_solutions(
            _weekday_2, _T(dt.date(2026, 3, 22)), dow  # Sunday
        )
        assert len(results) == 1
        assert deref(dow) == 6

    def test_non_date_raises(self):
        # nv
        assert raised(_weekday_2, "not-a-date", Var()) == \
            ('error', ('type_error', 'date', 'not-a-date'), ('/', 'weekday', 2))


# ── date_between/3 (nondeterministic) ────────────────────────────────────


class TestDateBetween:
    def test_range_three_days(self):
        """date_between generates each date in [start, end]."""
        # nv
        d = Var()
        solutions, trail = trampoline_solutions(
            date_between,
            _T(dt.date(2026, 3, 14)),
            _T(dt.date(2026, 3, 16)),
            d,
        )
        assert len(solutions) == 3

    def test_single_day(self):
        # nv
        d = Var()
        solutions, _ = trampoline_solutions(
            date_between,
            _T(dt.date(2026, 3, 16)),
            _T(dt.date(2026, 3, 16)),
            d,
        )
        assert len(solutions) == 1

    def test_empty_range(self):
        # nv
        d = Var()
        solutions, _ = trampoline_solutions(
            date_between,
            _T(dt.date(2026, 3, 17)),
            _T(dt.date(2026, 3, 16)),
            d,
        )
        assert len(solutions) == 0

    def test_week_range(self):
        # nv
        d = Var()
        solutions, _ = trampoline_solutions(
            date_between,
            _T(dt.date(2026, 3, 10)),
            _T(dt.date(2026, 3, 16)),
            d,
        )
        assert len(solutions) == 7

    def test_non_date_raises(self):
        # nv
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as info:
            trampoline_solutions(date_between, "2026-03-10", "2026-03-16", Var())
        assert info.value.term == \
            ('error', ('type_error', 'date', '2026-03-10'), ('/', 'date_between', 3))


# ── date_of/2 (datetime ↔ date) ──────────────────────────────────────────


class TestDateOf:
    def test_extract_date_from_datetime(self):
        """Forward: datetime → date (covers ++DT.date())."""
        # nv
        d = Var()
        results, _ = simple_solutions(
            _date_of_2, _T(dt.datetime(2026, 3, 16, 14, 30, 0)), d
        )
        assert len(results) == 1
        out = deref(d)
        assert out == _T(dt.date(2026, 3, 16))
        assert isinstance(_P(out), dt.date) and not isinstance(_P(out), dt.datetime)

    def test_inverse_midnight_datetime_from_date(self):
        """Inverse: date → midnight datetime."""
        # vn
        v = Var()
        results, _ = simple_solutions(_date_of_2, v, _T(dt.date(2026, 3, 16)))
        assert len(results) == 1
        out = deref(v)
        assert out == _T(dt.datetime(2026, 3, 16, 0, 0, 0))
        assert isinstance(_P(out), dt.datetime)

    def test_check_mode_matching(self):
        """Both ground, matching → one solution."""
        # nn
        results, _ = simple_solutions(
            _date_of_2, _T(dt.datetime(2026, 3, 16, 9, 0, 0)), _T(dt.date(2026, 3, 16))
        )
        assert len(results) == 1

    def test_check_mode_non_matching_fails(self):
        # nn
        results, _ = simple_solutions(
            _date_of_2, _T(dt.datetime(2026, 3, 16, 9, 0, 0)), _T(dt.date(2026, 3, 17))
        )
        assert len(results) == 0

    def test_both_unbound_fails(self):
        # vv
        results, _ = simple_solutions(_date_of_2, Var(), Var())
        assert len(results) == 0

    def test_non_datetime_first_arg_raises(self):
        # nv
        assert raised(_date_of_2, "2026-03-16", Var()) == \
            ('error', ('type_error', 'datetime', '2026-03-16'), ('/', 'date_of', 2))


# ── days_between/3 (integer day count) ───────────────────────────────────


class TestDaysBetween:
    def test_days_between_dates(self):
        """DaysBetween(A, B, N) → N = (A - B).days, no DateDiff+decompose."""
        # nnv
        n = Var()
        results, _ = simple_solutions(
            _days_between_3, _T(dt.date(2026, 3, 23)), _T(dt.date(2026, 3, 16)), n
        )
        assert len(results) == 1
        assert deref(n) == 7

    def test_negative_day_count(self):
        # nnv
        n = Var()
        results, _ = simple_solutions(
            _days_between_3, _T(dt.date(2026, 3, 16)), _T(dt.date(2026, 3, 23)), n
        )
        assert len(results) == 1
        assert deref(n) == -7

    def test_same_day_is_zero(self):
        # nnv
        n = Var()
        results, _ = simple_solutions(
            _days_between_3, _T(dt.date(2026, 3, 16)), _T(dt.date(2026, 3, 16)), n
        )
        assert len(results) == 1
        assert deref(n) == 0

    def test_datetimes_whole_days(self):
        """Whole-day count (_P(timedelta).days), consistent with DateDiff."""
        # nnv
        n = Var()
        results, _ = simple_solutions(
            _days_between_3,
            _T(dt.datetime(2026, 3, 23, 10, 0, 0)),
            _T(dt.datetime(2026, 3, 16, 12, 0, 0)),
            n,
        )
        assert len(results) == 1
        # 6 days, 22 hours → _P(timedelta).days == 6
        assert deref(n) == 6

    def test_check_mode(self):
        # nnn
        results, _ = simple_solutions(
            _days_between_3, _T(dt.date(2026, 3, 23)), _T(dt.date(2026, 3, 16)), 7
        )
        assert len(results) == 1

    def test_check_mode_wrong_fails(self):
        # nnn
        results, _ = simple_solutions(
            _days_between_3, _T(dt.date(2026, 3, 23)), _T(dt.date(2026, 3, 16)), 5
        )
        assert len(results) == 0

    def test_non_date_raises(self):
        # nnv
        assert raised(_days_between_3, "a", "b", Var()) == \
            ('error', ('type_error', 'date', 'a'), ('/', 'days_between', 3))


# ── timestamp/2 (bidirectional datetime ↔ POSIX epoch) ──────────────────


class TestTimestamp:
    def test_forward_datetime_to_float(self):
        # nv
        v = Var()
        d = _T(dt.datetime(2026, 3, 16, 12, 0, 0))
        results, _ = simple_solutions(_timestamp_2, d, v)
        assert len(results) == 1
        assert deref(v) == _P(d).timestamp()

    def test_inverse_float_to_datetime(self):
        # vn
        d = _T(dt.datetime(2026, 3, 16, 12, 0, 0))
        v = Var()
        results, _ = simple_solutions(_timestamp_2, v, _P(d).timestamp())
        assert len(results) == 1
        assert deref(v) == d

    def test_inverse_int_stamp(self):
        # vn
        v = Var()
        results, _ = simple_solutions(_timestamp_2, v, 0)
        assert len(results) == 1
        assert isinstance(_P(deref(v)), dt.datetime)

    def test_check_mode_matches(self):
        # nn
        d = _T(dt.datetime(2026, 3, 16, 12, 0, 0))
        results, _ = simple_solutions(_timestamp_2, d, _P(d).timestamp())
        assert len(results) == 1

    def test_date_has_no_timestamp_raises(self):
        # a plain date is not a datetime → type_error, culprit the TERM
        assert raised(_timestamp_2, _T(dt.date(2026, 3, 16)), Var()) == \
            ('error', ('type_error', 'datetime', ('date', 2026, 3, 16)), ('/', 'timestamp', 2))

    def test_both_unbound_raises(self):
        # vv
        assert raised(_timestamp_2, Var(), Var()) == ('error', 'instantiation_error', ('/', 'timestamp', 2))


# ── Unification of datetime objects ─────────────────────────────────────


class TestUnification:
    def test_same_date_unifies(self):
        # nv
        trail = Trail()
        v = Var()
        assert unify(v, _T(dt.date(2026, 3, 16)), trail)
        assert deref(v) == _T(dt.date(2026, 3, 16))

    def test_different_dates_fail(self):
        # nv
        trail = Trail()
        v = Var()
        assert unify(v, _T(dt.date(2026, 3, 16)), trail)
        # v is now bound — unifying with a different date should fail
        assert not unify(v, _T(dt.date(2026, 3, 17)), trail)

    def test_datetime_unifies(self):
        # nv
        trail = Trail()
        v = Var()
        d = _T(dt.datetime(2026, 3, 16, 14, 30, 0))
        assert unify(v, d, trail)
        assert deref(v) is d

    def test_timedelta_unifies(self):
        # nv
        trail = Trail()
        v = Var()
        td = _T(dt.timedelta(days=7))
        assert unify(v, td, trail)
        assert deref(v) == td


# ── Predicate adapter objects ───────────────────────────────────────────


class TestAdapters:
    def test_now_has_dispatch(self):
        # nv
        assert callable(now._get_dispatch())

    def test_today_has_dispatch(self):
        # nv
        assert callable(today._get_dispatch())

    def test_date_is_a_term_constructor_not_a_predicate(self):
        """date/3 replaced date/4: `date` is now the TERM, so it has no goal
        dispatch. Construct and decompose are unification, not a call."""
        # nv
        assert not hasattr(date, "_get_dispatch")
        assert date(2026, 3, 16) == _T(dt.date(2026, 3, 16))

    def test_time_has_dispatch(self):
        # nv
        assert callable(time._get_dispatch())

    def test_datetime_has_dispatch(self):
        # nv
        assert callable(datetime._get_dispatch())

    def test_timedelta_has_dispatch(self):
        # nv
        assert callable(timedelta._get_dispatch())

    def test_date_add_has_dispatch(self):
        # nv
        assert callable(date_add._get_dispatch())

    def test_date_sub_has_dispatch(self):
        # nv
        assert callable(date_sub._get_dispatch())

    def test_date_diff_has_dispatch(self):
        # nv
        assert callable(date_diff._get_dispatch())

    def test_datetime_string_has_dispatch(self):
        # nv
        assert callable(datetime_string._get_dispatch())

    def test_weekday_has_dispatch(self):
        # nv
        assert callable(weekday._get_dispatch())

    def test_date_between_has_dispatch(self):
        # nv
        assert callable(date_between._get_dispatch())

    def test_date_of_has_dispatch(self):
        # nv
        assert callable(date_of._get_dispatch())

    def test_days_between_has_dispatch(self):
        # nv
        assert callable(days_between._get_dispatch())

    def test_timestamp_has_dispatch(self):
        # nv
        assert callable(timestamp._get_dispatch())

    def test_repr(self):
        # nv
        # `date` is a term constructor, not a ModulePredicate, so it has no
        # module-qualified predicate repr; date_between is still a predicate.
        assert "datetime.date_between" in repr(date_between)

    def test_datetime_string_iso_has_dispatch(self):
        # nv
        assert callable(datetime_string_iso._get_dispatch())

    def test_date_string_iso_has_dispatch(self):
        # nv
        assert callable(date_string_iso._get_dispatch())


# ── datetime_string_iso/2 (bidirectional ISO-8601 datetime) ───────────────


class TestDatetimeStringIso:
    def test_forward(self):
        # nv
        s = Var()
        d = _T(dt.datetime(2026, 3, 16, 14, 30, 0))
        results, _ = simple_solutions(_datetime_string_iso_2, d, s)
        assert len(results) == 1
        assert deref(s) == chars("2026-03-16T14:30:00")

    def test_inverse(self):
        # vn
        v = Var()
        results, _ = simple_solutions(
            _datetime_string_iso_2, v, chars("2026-03-16T14:30:00")
        )
        assert len(results) == 1
        assert deref(v) == _T(dt.datetime(2026, 3, 16, 14, 30, 0))

    def test_inverse_invalid_fails(self):
        # vn
        v = Var()
        results, _ = simple_solutions(_datetime_string_iso_2, v, chars("nope"))
        assert len(results) == 0

    def test_both_unbound_raises(self):
        # vv
        assert raised(_datetime_string_iso_2, Var(), Var()) == \
            ('error', 'instantiation_error', ('/', 'datetime_string_iso', 2))


# ── date_string_iso/2 (bidirectional ISO-8601 date) ───────────────────────


class TestDateStringIso:
    def test_forward(self):
        # nv
        s = Var()
        results, _ = simple_solutions(_date_string_iso_2, _T(dt.date(2026, 3, 16)), s)
        assert len(results) == 1
        assert deref(s) == chars("2026-03-16")

    def test_inverse(self):
        # vn
        v = Var()
        results, _ = simple_solutions(_date_string_iso_2, v, chars("2026-03-16"))
        assert len(results) == 1
        out = deref(v)
        assert out == _T(dt.date(2026, 3, 16))
        assert isinstance(_P(out), dt.date) and not isinstance(_P(out), dt.datetime)

    def test_forward_rejects_datetime(self):
        """A datetime is not a plain date → type_error(date, Culprit)."""
        # nv
        assert raised(
            _date_string_iso_2, _T(dt.datetime(2026, 3, 16, 1, 2, 3)), Var()
        ) == ('error', ('type_error', 'date', ('datetime', 2026, 3, 16, 1, 2, 3, 0)), ('/', 'date_string_iso', 2))

    def test_inverse_invalid_fails(self):
        # vn
        v = Var()
        results, _ = simple_solutions(_date_string_iso_2, v, chars("2026-03-16T00:00:00"))
        assert len(results) == 0

    def test_both_unbound_raises(self):
        # vv
        assert raised(_date_string_iso_2, Var(), Var()) == \
            ('error', 'instantiation_error', ('/', 'date_string_iso', 2))


# ── date_max/3, date_min/3 — earlier/later of two dates ──────────────────


class TestDateMaxMin:
    def test_date_max_binds_later(self):
        """date_max(D1, D2, M) → M is the later date (covers ++max(D1, D2))."""
        # nnv
        m = Var()
        results, _ = simple_solutions(
            _date_max_3, _T(dt.date(2026, 3, 16)), _T(dt.date(2026, 3, 23)), m
        )
        assert len(results) == 1
        assert deref(m) == _T(dt.date(2026, 3, 23))

    def test_date_min_binds_earlier(self):
        # nnv
        m = Var()
        results, _ = simple_solutions(
            _date_min_3, _T(dt.date(2026, 3, 16)), _T(dt.date(2026, 3, 23)), m
        )
        assert len(results) == 1
        assert deref(m) == _T(dt.date(2026, 3, 16))

    def test_equal_dates_bind_that_date(self):
        # nnv
        m = Var()
        results, _ = simple_solutions(
            _date_max_3, _T(dt.date(2026, 3, 16)), _T(dt.date(2026, 3, 16)), m
        )
        assert len(results) == 1
        assert deref(m) == _T(dt.date(2026, 3, 16))

    def test_datetimes_compare_too(self):
        # nnv
        m = Var()
        a = _T(dt.datetime(2026, 3, 16, 9, 0))
        b = _T(dt.datetime(2026, 3, 16, 17, 30))
        results, _ = simple_solutions(_date_max_3, a, b, m)
        assert len(results) == 1
        assert deref(m) == b

    def test_check_mode(self):
        # nnn
        results, _ = simple_solutions(
            _date_max_3, _T(dt.date(2026, 3, 16)), _T(dt.date(2026, 3, 23)),
            _T(dt.date(2026, 3, 23))
        )
        assert len(results) == 1
        results, _ = simple_solutions(
            _date_max_3, _T(dt.date(2026, 3, 16)), _T(dt.date(2026, 3, 23)),
            _T(dt.date(2026, 3, 16))
        )
        assert len(results) == 0

    def test_mixed_date_and_datetime_fails_cleanly(self):
        """date < datetime comparison raises TypeError in Python — the
        builtin fails the goal rather than leaking the exception."""
        # nnv
        results, _ = simple_solutions(
            _date_max_3, _T(dt.date(2026, 3, 16)),
            _T(dt.datetime(2026, 3, 16, 9, 0)), Var()
        )
        assert len(results) == 0

    def test_non_date_arg_raises(self):
        # nnv
        assert raised(
            _date_min_3, "2026-03-16", _T(dt.date(2026, 3, 23)), Var()
        ) == ('error', ('type_error', 'date', '2026-03-16'), ('/', 'date_min', 3))


# ── ordinal/2 — bidirectional proleptic-Gregorian ordinal ─────────────────


class TestOrdinal:
    def test_forward_date_to_ordinal(self):
        """ordinal(Date, N) → N = Date.toordinal() (covers ++D.toordinal())."""
        # nv
        n = Var()
        d = _T(dt.date(2026, 3, 16))
        results, _ = simple_solutions(_ordinal_2, d, n)
        assert len(results) == 1
        assert deref(n) == _P(d).toordinal()

    def test_reverse_ordinal_to_date(self):
        """ordinal(D, N) with D unbound builds date.fromordinal(N) — the
        numlist-over-ordinals day-enumeration pattern maps back to dates."""
        # vn
        v = Var()
        d = _T(dt.date(2026, 3, 16))
        results, _ = simple_solutions(_ordinal_2, v, _P(d).toordinal())
        assert len(results) == 1
        out = deref(v)
        assert out == d
        assert isinstance(_P(out), dt.date) and not isinstance(_P(out), dt.datetime)

    def test_check_mode(self):
        # nn
        d = _T(dt.date(2026, 3, 16))
        results, _ = simple_solutions(_ordinal_2, d, _P(d).toordinal())
        assert len(results) == 1
        results, _ = simple_solutions(_ordinal_2, d, _P(d).toordinal() + 1)
        assert len(results) == 0

    def test_datetime_forward_uses_its_calendar_day(self):
        # nv
        n = Var()
        results, _ = simple_solutions(
            _ordinal_2, _T(dt.datetime(2026, 3, 16, 14, 30)), n
        )
        assert len(results) == 1
        assert deref(n) == dt.date(2026, 3, 16).toordinal()

    def test_reverse_out_of_range_fails(self):
        """date.fromordinal raises ValueError for ordinal < 1 — the builtin
        fails the goal rather than leaking the exception."""
        # vn
        results, _ = simple_solutions(_ordinal_2, Var(), 0)
        assert len(results) == 0

    def test_both_unbound_fails(self):
        # vv
        results, _ = simple_solutions(_ordinal_2, Var(), Var())
        assert len(results) == 0

    def test_non_integer_reverse_raises(self):
        # vn
        assert raised(_ordinal_2, Var(), "737000") == \
            ('error', ('type_error', 'integer', '737000'), ('/', 'ordinal', 2))


