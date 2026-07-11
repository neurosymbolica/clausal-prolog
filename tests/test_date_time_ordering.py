"""Ordering of date/datetime/time via the comparison operators and the
sort/collection predicates, plus the incomparable-comparison error path.

date/datetime/time are real Python objects; the comparison operators reach
clpfd.fd_lt/fd_le/fd_gt/fd_ge, which order any comparable ground values.
"""

from __future__ import annotations

import datetime as dt
from fractions import Fraction

import pytest

from clausal.logic.variables import Var, Trail, deref
from clausal.logic.clpfd import (
    fd_lt, fd_le, fd_gt, fd_ge, _incomparable_order_error,
)
from clausal.logic.builtins.lists import (
    _sort__2, _msort__2, _min_list__2, _max_list__2,
)
from clausal.logic.exceptions import LogicException
from clausal.logic.trampoline import DONE


# ── Helpers ──────────────────────────────────────────────────────────────

def _run_list_builtin(fn, in_list):
    """Drive a (this_generator, _proceed, _fail, _catcher, lst, out, trail)
    list builtin; return one dereferenced output list per solution.

    Assumes a single deterministic solution — appropriate for deterministic
    list builtins (sort, msort, min_list, max_list) which yield at most one
    solution for a ground input list.

    For builtins that unify *out* with a single scalar (min_list, max_list)
    the scalar is wrapped in a one-element list so callers always see a
    uniform ``[[value, ...], ...]`` shape.
    """
    trail = Trail()
    out = Var()
    results = []
    for _cont, val in fn(None, "proceed", "fail", None, in_list, out, trail):
        if val is DONE:
            break
        resolved = deref(out)
        try:
            results.append([deref(x) for x in resolved])
        except TypeError as exc:
            # out was unified to a scalar (e.g. min_list/max_list): the
            # iteration above raised "object is not iterable".  Any other
            # TypeError (e.g. from a bad deref of a malformed term) is an
            # unrelated failure and must propagate, not produce a false green.
            if "iterable" not in str(exc):
                raise
            results.append([resolved])
    return results


def _assert_orderable_error(exc_info, context):
    term = exc_info.value.term
    assert term.functor == "error"
    inner = term.args[0]
    assert inner.functor == "type_error"
    assert inner.args[0] == "orderable"
    assert term.args[1] == context


# ── Comparison operators order dates/datetimes/times ─────────────────────

class TestComparisonOperators:
    def test_date_lt(self):
        assert fd_lt(dt.date(2020, 1, 1), dt.date(2021, 1, 1), Trail()) is True
        assert fd_lt(dt.date(2021, 1, 1), dt.date(2020, 1, 1), Trail()) is False

    def test_date_le_equal(self):
        assert fd_le(dt.date(2021, 1, 1), dt.date(2021, 1, 1), Trail()) is True
        assert fd_lt(dt.date(2021, 1, 1), dt.date(2021, 1, 1), Trail()) is False

    def test_date_gt_ge(self):
        assert fd_gt(dt.date(2022, 1, 1), dt.date(2021, 1, 1), Trail()) is True
        assert fd_ge(dt.date(2021, 1, 1), dt.date(2021, 1, 1), Trail()) is True

    def test_datetime_lt(self):
        a = dt.datetime(2020, 1, 1, 10, 0, 0)
        b = dt.datetime(2020, 1, 1, 11, 0, 0)
        assert fd_lt(a, b, Trail()) is True

    def test_time_lt(self):
        assert fd_lt(dt.time(9, 0, 0), dt.time(17, 0, 0), Trail()) is True


# ── Sort / collection predicates order dates ─────────────────────────────

class TestCollectionOrdering:
    def test_msort_orders_dates(self):
        a, b, c = dt.date(2021, 1, 1), dt.date(2019, 5, 5), dt.date(2020, 3, 3)
        assert _run_list_builtin(_msort__2, [a, b, c]) == [[b, c, a]]

    def test_sort_dedups_and_orders_dates(self):
        a, b, a2 = dt.date(2021, 1, 1), dt.date(2019, 5, 5), dt.date(2021, 1, 1)
        assert _run_list_builtin(_sort__2, [a, b, a2]) == [[b, a]]

    def test_min_list_dates(self):
        a, b = dt.date(2021, 1, 1), dt.date(2019, 5, 5)
        assert _run_list_builtin(_min_list__2, [a, b]) == [[b]]

    def test_max_list_dates(self):
        a, b = dt.date(2021, 1, 1), dt.date(2019, 5, 5)
        assert _run_list_builtin(_max_list__2, [a, b]) == [[a]]


# ── Incomparable comparisons raise a catchable type_error ────────────────

class TestIncomparableRaises:
    def test_date_vs_datetime(self):
        with pytest.raises(LogicException) as ei:
            fd_lt(dt.date(2020, 1, 1), dt.datetime(2020, 1, 1, 0, 0, 0), Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_naive_vs_aware(self):
        naive = dt.datetime(2020, 1, 1)
        aware = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
        with pytest.raises(LogicException) as ei:
            fd_le(naive, aware, Trail())
        _assert_orderable_error(ei, "(=<)/2")

    def test_date_vs_int(self):
        with pytest.raises(LogicException) as ei:
            fd_lt(dt.date(2020, 1, 1), 5, Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_gt_surfaces_lt_context(self):
        # fd_gt(l, r) delegates to fd_lt(r, l), so the context is (<)/2 and
        # the culprit is the original left operand (dt.date here).
        with pytest.raises(LogicException) as ei:
            fd_gt(dt.date(2020, 1, 1), dt.datetime(2020, 1, 1), Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_culprit_is_second_operand(self):
        target = dt.datetime(2020, 1, 1, 0, 0, 0)
        with pytest.raises(LogicException) as ei:
            fd_lt(dt.date(2020, 1, 1), target, Trail())
        assert ei.value.term.args[0].args[1] == target


class TestLegitimateTypeErrorPreserved:
    def test_mixed_rational_real_not_swallowed(self):
        # This must stay a plain TypeError with its "cannot mix" message,
        # NOT be converted to a type_error(orderable, ...).
        with pytest.raises(TypeError) as ei:
            fd_lt(Fraction(1, 2), 0.9, Trail())
        assert "mix" in str(ei.value).lower()


class TestHelper:
    def test_incomparable_order_error(self):
        culprit = dt.datetime(2020, 1, 1)
        exc = _incomparable_order_error(culprit, "(<)/2")
        assert isinstance(exc, LogicException)
        assert exc.term.functor == "error"
        assert exc.term.args[0].functor == "type_error"
        assert exc.term.args[0].args[0] == "orderable"
        assert exc.term.args[0].args[1] == culprit
        assert exc.term.args[1] == "(<)/2"
