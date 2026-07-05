"""Tests for clausal.modules.date_time — Date/time predicates.

All predicates produce and consume real Python datetime objects
(datetime.date, datetime.time, datetime.datetime, datetime.timedelta).
"""

from __future__ import annotations

import datetime as dt
import pytest

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.datetime import (
    now, now_utc, today, date, time, datetime, timedelta,
    date_add, date_sub, date_diff, date_between, date_of, days_between,
    weekday, datetime_string,
    _now_1, _now_utc_1, _today_1,
    _date_4, _time_4, _datetime_7, _timedelta_3,
    _date_add_3, _date_sub_3, _date_diff_3,
    _datetime_string_3, _weekday_2,
    _date_of_2, _days_between_3,
)
from clausal.logic.trampoline import DONE


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


# ── Now / NowUTC / Today ────────────────────────────────────────────────


class TestNow:
    def test_now_binds_datetime(self):
        # nv
        v = Var()
        results, trail = simple_solutions(_now_1, v)
        assert len(results) == 1
        val = deref(v)
        assert isinstance(val, dt.datetime)

    def test_now_utc_binds_datetime(self):
        # nv
        v = Var()
        results, trail = simple_solutions(_now_utc_1, v)
        assert len(results) == 1
        val = deref(v)
        assert isinstance(val, dt.datetime)
        assert val.tzinfo is not None

    def test_today_binds_date(self):
        # nv
        v = Var()
        results, trail = simple_solutions(_today_1, v)
        assert len(results) == 1
        val = deref(v)
        assert isinstance(val, dt.date)
        assert not isinstance(val, dt.datetime)
        assert val == dt.date.today()


# ── Date/4 ──────────────────────────────────────────────────────────────


class TestDate:
    def test_construct(self):
        """Date(2026, 3, 16, D_) → D_ = datetime.date(2026, 3, 16)."""
        # nv
        d = Var()
        results, trail = simple_solutions(_date_4, 2026, 3, 16, d)
        assert len(results) == 1
        val = deref(d)
        assert val == dt.date(2026, 3, 16)
        assert type(val) is dt.date

    def test_decompose(self):
        """Date(Y_, M_, D_, datetime.date(2026, 3, 16)) → Y_=2026, M_=3, D_=16."""
        # nv
        y, m, d = Var(), Var(), Var()
        results, trail = simple_solutions(_date_4, y, m, d, dt.date(2026, 3, 16))
        assert len(results) == 1
        assert deref(y) == 2026
        assert deref(m) == 3
        assert deref(d) == 16

    def test_decompose_datetime_object(self):
        """Date/4 can decompose a datetime.datetime too (extracts date components)."""
        # nv
        y, m, d = Var(), Var(), Var()
        results, _ = simple_solutions(
            _date_4, y, m, d, dt.datetime(2026, 3, 16, 10, 30, 0)
        )
        assert len(results) == 1
        assert deref(y) == 2026
        assert deref(m) == 3
        assert deref(d) == 16

    def test_construct_invalid_date_fails(self):
        """Date(2026, 13, 1, D_) fails — month 13 is invalid."""
        # nv
        d = Var()
        results, _ = simple_solutions(_date_4, 2026, 13, 1, d)
        assert len(results) == 0

    def test_construct_and_check(self):
        """Date(2026, 3, 16, datetime.date(2026, 3, 16)) succeeds."""
        # nv
        results, _ = simple_solutions(
            _date_4, 2026, 3, 16, dt.date(2026, 3, 16)
        )
        # decompose mode: ground date, ground components — unify must match
        assert len(results) == 1

    def test_construct_and_check_mismatch(self):
        """Date(2026, 3, 16, datetime.date(2026, 3, 17)) fails."""
        # nv
        results, _ = simple_solutions(
            _date_4, 2026, 3, 16, dt.date(2026, 3, 17)
        )
        # decompose: year=2026→2026 OK, month=3→3 OK, day=16→17 FAIL
        assert len(results) == 0

    def test_leap_year(self):
        """Date(2024, 2, 29, D_) succeeds — 2024 is a leap year."""
        # nv
        d = Var()
        results, _ = simple_solutions(_date_4, 2024, 2, 29, d)
        assert len(results) == 1
        assert deref(d) == dt.date(2024, 2, 29)

    def test_non_leap_year_feb29_fails(self):
        """Date(2025, 2, 29, D_) fails — 2025 is not a leap year."""
        # nv
        d = Var()
        results, _ = simple_solutions(_date_4, 2025, 2, 29, d)
        assert len(results) == 0


# ── Time/4 ──────────────────────────────────────────────────────────────


class TestTime:
    def test_construct(self):
        # nv
        t = Var()
        results, _ = simple_solutions(_time_4, 14, 30, 0, t)
        assert len(results) == 1
        assert deref(t) == dt.time(14, 30, 0)

    def test_decompose(self):
        # nv
        h, m, s = Var(), Var(), Var()
        results, _ = simple_solutions(_time_4, h, m, s, dt.time(14, 30, 45))
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
        assert deref(t) == dt.time(0, 0, 0)


# ── DateTime/7 ──────────────────────────────────────────────────────────


class TestDateTime:
    def test_construct(self):
        # nv
        v = Var()
        results, _ = simple_solutions(
            _datetime_7, 2026, 3, 16, 14, 30, 0, v
        )
        assert len(results) == 1
        assert deref(v) == dt.datetime(2026, 3, 16, 14, 30, 0)
        assert type(deref(v)) is dt.datetime

    def test_decompose(self):
        # nv
        y, mo, d, h, mi, s = Var(), Var(), Var(), Var(), Var(), Var()
        results, _ = simple_solutions(
            _datetime_7, y, mo, d, h, mi, s,
            dt.datetime(2026, 3, 16, 14, 30, 45)
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


# ── TimeDelta/3 ─────────────────────────────────────────────────────────


class TestTimeDelta:
    def test_construct(self):
        # nv
        v = Var()
        results, _ = simple_solutions(_timedelta_3, 7, 3600, v)
        assert len(results) == 1
        assert deref(v) == dt.timedelta(days=7, seconds=3600)

    def test_construct_days_only(self):
        # nv
        v = Var()
        s = Var()  # seconds unbound → defaults to 0
        results, _ = simple_solutions(_timedelta_3, 7, s, v)
        assert len(results) == 1
        val = deref(v)
        assert val.days == 7

    def test_decompose(self):
        # nv
        days, secs = Var(), Var()
        td = dt.timedelta(days=5, seconds=1234)
        results, _ = simple_solutions(_timedelta_3, days, secs, td)
        assert len(results) == 1
        assert deref(days) == 5
        assert deref(secs) == 1234


# ── DateAdd/3 ───────────────────────────────────────────────────────────


class TestDateAdd:
    def test_add_days_to_date(self):
        # nv
        r = Var()
        results, _ = simple_solutions(
            _date_add_3, dt.date(2026, 3, 16), dt.timedelta(days=7), r
        )
        assert len(results) == 1
        assert deref(r) == dt.date(2026, 3, 23)

    def test_add_to_datetime(self):
        # nv
        r = Var()
        results, _ = simple_solutions(
            _date_add_3,
            dt.datetime(2026, 3, 16, 10, 0, 0),
            dt.timedelta(hours=3),
            r,
        )
        assert len(results) == 1
        assert deref(r) == dt.datetime(2026, 3, 16, 13, 0, 0)

    def test_add_non_date_fails(self):
        # nv
        r = Var()
        results, _ = simple_solutions(_date_add_3, "not-a-date", dt.timedelta(1), r)
        assert len(results) == 0

    def test_add_non_timedelta_fails(self):
        # nv
        r = Var()
        results, _ = simple_solutions(_date_add_3, dt.date(2026, 1, 1), 7, r)
        assert len(results) == 0


# ── DateSub/3 ───────────────────────────────────────────────────────────


class TestDateSub:
    def test_sub_days_from_date(self):
        # nv
        r = Var()
        results, _ = simple_solutions(
            _date_sub_3, dt.date(2026, 3, 16), dt.timedelta(days=10), r
        )
        assert len(results) == 1
        assert deref(r) == dt.date(2026, 3, 6)

    def test_sub_from_datetime(self):
        # nv
        r = Var()
        results, _ = simple_solutions(
            _date_sub_3,
            dt.datetime(2026, 3, 16, 10, 0, 0),
            dt.timedelta(hours=5),
            r,
        )
        assert len(results) == 1
        assert deref(r) == dt.datetime(2026, 3, 16, 5, 0, 0)


# ── DateDiff/3 ──────────────────────────────────────────────────────────


class TestDateDiff:
    def test_diff_dates(self):
        # nv
        td = Var()
        results, _ = simple_solutions(
            _date_diff_3, dt.date(2026, 3, 16), dt.date(2026, 3, 10), td
        )
        assert len(results) == 1
        assert deref(td) == dt.timedelta(days=6)

    def test_diff_datetimes(self):
        # nv
        td = Var()
        results, _ = simple_solutions(
            _date_diff_3,
            dt.datetime(2026, 3, 16, 12, 0, 0),
            dt.datetime(2026, 3, 16, 10, 0, 0),
            td,
        )
        assert len(results) == 1
        assert deref(td) == dt.timedelta(hours=2)

    def test_negative_diff(self):
        # nv
        td = Var()
        results, _ = simple_solutions(
            _date_diff_3, dt.date(2026, 3, 10), dt.date(2026, 3, 16), td
        )
        assert len(results) == 1
        assert deref(td) == dt.timedelta(days=-6)

    def test_diff_non_dates_fails(self):
        # nv
        td = Var()
        results, _ = simple_solutions(_date_diff_3, "a", "b", td)
        assert len(results) == 0


# ── datetime_string/3 — bidirectional strftime/strptime ─────────────────


class TestDatetimeString:
    def test_format_date(self):
        # nv — format mode
        s = Var()
        results, _ = simple_solutions(
            _datetime_string_3, dt.date(2026, 3, 16), s, "%Y-%m-%d"
        )
        assert len(results) == 1
        assert deref(s) == "2026-03-16"

    def test_format_datetime(self):
        # nv
        s = Var()
        results, _ = simple_solutions(
            _datetime_string_3,
            dt.datetime(2026, 3, 16, 14, 30, 0), s, "%Y-%m-%d %H:%M",
        )
        assert len(results) == 1
        assert deref(s) == "2026-03-16 14:30"

    def test_format_time(self):
        # nv
        s = Var()
        results, _ = simple_solutions(
            _datetime_string_3, dt.time(14, 30, 0), s, "%H:%M:%S"
        )
        assert len(results) == 1
        assert deref(s) == "14:30:00"

    def test_parse_to_datetime(self):
        # vn — parse mode
        v = Var()
        results, _ = simple_solutions(
            _datetime_string_3, v, "2026-03-16 14:30", "%Y-%m-%d %H:%M"
        )
        assert len(results) == 1
        assert deref(v) == dt.datetime(2026, 3, 16, 14, 30)

    def test_check_mode_matches(self):
        # nn — both ground, format matches
        results, _ = simple_solutions(
            _datetime_string_3, dt.date(2026, 3, 16), "2026-03-16", "%Y-%m-%d"
        )
        assert len(results) == 1

    def test_check_mode_mismatch_fails(self):
        # nn
        results, _ = simple_solutions(
            _datetime_string_3, dt.date(2026, 3, 16), "2026-03-17", "%Y-%m-%d"
        )
        assert len(results) == 0

    def test_parse_invalid_fails(self):
        # vn
        v = Var()
        results, _ = simple_solutions(
            _datetime_string_3, v, "not-a-date", "%Y-%m-%d"
        )
        assert len(results) == 0

    def test_both_unbound_fails(self):
        # vv
        results, _ = simple_solutions(_datetime_string_3, Var(), Var(), "%Y-%m-%d")
        assert len(results) == 0

    def test_unbound_format_fails(self):
        # format arg must be ground
        results, _ = simple_solutions(
            _datetime_string_3, dt.date(2026, 3, 16), Var(), Var()
        )
        assert len(results) == 0

    def test_date_roundtrips_to_midnight_datetime(self):
        """A date → string → back yields a midnight datetime (documented asymmetry)."""
        # nv then vn
        s = Var()
        simple_solutions(_datetime_string_3, dt.date(2026, 3, 16), s, "%Y-%m-%d")
        v = Var()
        simple_solutions(_datetime_string_3, v, deref(s), "%Y-%m-%d")
        assert deref(v) == dt.datetime(2026, 3, 16, 0, 0, 0)


# ── DayOfWeek/2 ─────────────────────────────────────────────────────────


class TestDayOfWeek:
    def test_weekday(self):
        # nv
        dow = Var()
        results, _ = simple_solutions(
            _weekday_2, dt.date(2026, 3, 16), dow  # Monday
        )
        assert len(results) == 1
        assert deref(dow) == 0  # Monday = 0

    def test_sunday(self):
        # nv
        dow = Var()
        results, _ = simple_solutions(
            _weekday_2, dt.date(2026, 3, 22), dow  # Sunday
        )
        assert len(results) == 1
        assert deref(dow) == 6

    def test_non_date_fails(self):
        # nv
        dow = Var()
        results, _ = simple_solutions(_weekday_2, "not-a-date", dow)
        assert len(results) == 0


# ── DateBetween/3 (nondeterministic) ────────────────────────────────────


class TestDateBetween:
    def test_range_three_days(self):
        """date_between generates each date in [start, end]."""
        # nv
        d = Var()
        solutions, trail = trampoline_solutions(
            date_between,
            dt.date(2026, 3, 14),
            dt.date(2026, 3, 16),
            d,
        )
        assert len(solutions) == 3

    def test_single_day(self):
        # nv
        d = Var()
        solutions, _ = trampoline_solutions(
            date_between,
            dt.date(2026, 3, 16),
            dt.date(2026, 3, 16),
            d,
        )
        assert len(solutions) == 1

    def test_empty_range(self):
        # nv
        d = Var()
        solutions, _ = trampoline_solutions(
            date_between,
            dt.date(2026, 3, 17),
            dt.date(2026, 3, 16),
            d,
        )
        assert len(solutions) == 0

    def test_week_range(self):
        # nv
        d = Var()
        solutions, _ = trampoline_solutions(
            date_between,
            dt.date(2026, 3, 10),
            dt.date(2026, 3, 16),
            d,
        )
        assert len(solutions) == 7

    def test_non_date_fails(self):
        # nv
        d = Var()
        solutions, _ = trampoline_solutions(
            date_between, "2026-03-10", "2026-03-16", d
        )
        assert len(solutions) == 0


# ── DateOf/2 (datetime ↔ date) ──────────────────────────────────────────


class TestDateOf:
    def test_extract_date_from_datetime(self):
        """Forward: datetime → date (covers ++DT.date())."""
        # nv
        d = Var()
        results, _ = simple_solutions(
            _date_of_2, dt.datetime(2026, 3, 16, 14, 30, 0), d
        )
        assert len(results) == 1
        out = deref(d)
        assert out == dt.date(2026, 3, 16)
        assert isinstance(out, dt.date) and not isinstance(out, dt.datetime)

    def test_inverse_midnight_datetime_from_date(self):
        """Inverse: date → midnight datetime."""
        # vn
        v = Var()
        results, _ = simple_solutions(_date_of_2, v, dt.date(2026, 3, 16))
        assert len(results) == 1
        out = deref(v)
        assert out == dt.datetime(2026, 3, 16, 0, 0, 0)
        assert isinstance(out, dt.datetime)

    def test_check_mode_matching(self):
        """Both ground, matching → one solution."""
        # nn
        results, _ = simple_solutions(
            _date_of_2, dt.datetime(2026, 3, 16, 9, 0, 0), dt.date(2026, 3, 16)
        )
        assert len(results) == 1

    def test_check_mode_non_matching_fails(self):
        # nn
        results, _ = simple_solutions(
            _date_of_2, dt.datetime(2026, 3, 16, 9, 0, 0), dt.date(2026, 3, 17)
        )
        assert len(results) == 0

    def test_both_unbound_fails(self):
        # vv
        results, _ = simple_solutions(_date_of_2, Var(), Var())
        assert len(results) == 0

    def test_non_datetime_first_arg_fails(self):
        # nv
        results, _ = simple_solutions(_date_of_2, "2026-03-16", Var())
        assert len(results) == 0


# ── DaysBetween/3 (integer day count) ───────────────────────────────────


class TestDaysBetween:
    def test_days_between_dates(self):
        """DaysBetween(A, B, N) → N = (A - B).days, no DateDiff+decompose."""
        # nnv
        n = Var()
        results, _ = simple_solutions(
            _days_between_3, dt.date(2026, 3, 23), dt.date(2026, 3, 16), n
        )
        assert len(results) == 1
        assert deref(n) == 7

    def test_negative_day_count(self):
        # nnv
        n = Var()
        results, _ = simple_solutions(
            _days_between_3, dt.date(2026, 3, 16), dt.date(2026, 3, 23), n
        )
        assert len(results) == 1
        assert deref(n) == -7

    def test_same_day_is_zero(self):
        # nnv
        n = Var()
        results, _ = simple_solutions(
            _days_between_3, dt.date(2026, 3, 16), dt.date(2026, 3, 16), n
        )
        assert len(results) == 1
        assert deref(n) == 0

    def test_datetimes_whole_days(self):
        """Whole-day count (timedelta.days), consistent with DateDiff."""
        # nnv
        n = Var()
        results, _ = simple_solutions(
            _days_between_3,
            dt.datetime(2026, 3, 23, 10, 0, 0),
            dt.datetime(2026, 3, 16, 12, 0, 0),
            n,
        )
        assert len(results) == 1
        # 6 days, 22 hours → timedelta.days == 6
        assert deref(n) == 6

    def test_check_mode(self):
        # nnn
        results, _ = simple_solutions(
            _days_between_3, dt.date(2026, 3, 23), dt.date(2026, 3, 16), 7
        )
        assert len(results) == 1

    def test_check_mode_wrong_fails(self):
        # nnn
        results, _ = simple_solutions(
            _days_between_3, dt.date(2026, 3, 23), dt.date(2026, 3, 16), 5
        )
        assert len(results) == 0

    def test_non_date_fails(self):
        # nnv
        n = Var()
        results, _ = simple_solutions(_days_between_3, "a", "b", n)
        assert len(results) == 0


# ── Unification of datetime objects ─────────────────────────────────────


class TestUnification:
    def test_same_date_unifies(self):
        # nv
        trail = Trail()
        v = Var()
        assert unify(v, dt.date(2026, 3, 16), trail)
        assert deref(v) == dt.date(2026, 3, 16)

    def test_different_dates_fail(self):
        # nv
        trail = Trail()
        v = Var()
        assert unify(v, dt.date(2026, 3, 16), trail)
        # v is now bound — unifying with a different date should fail
        assert not unify(v, dt.date(2026, 3, 17), trail)

    def test_datetime_unifies(self):
        # nv
        trail = Trail()
        v = Var()
        d = dt.datetime(2026, 3, 16, 14, 30, 0)
        assert unify(v, d, trail)
        assert deref(v) is d

    def test_timedelta_unifies(self):
        # nv
        trail = Trail()
        v = Var()
        td = dt.timedelta(days=7)
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

    def test_date_has_dispatch(self):
        # nv
        assert callable(date._get_dispatch())

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

    def test_repr(self):
        # nv
        assert "datetime.date" in repr(date)
        assert "datetime.date_between" in repr(date_between)
