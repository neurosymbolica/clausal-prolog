"""Contract for date/3 — the date TERM.

`date(Y, M, D)` is the standard representation: a real ``datetime.date``,
bidirectional by UNIFICATION rather than by a constructor predicate.
Ground args construct; unbound args pattern-match against a real date.

This is what makes date/4 redundant (`DATE = date(Y, M, D)` does both
modes) and what makes msort correct — a bare Compound named `date`
compares its args as strings and silently mis-sorts.
"""

from __future__ import annotations

import datetime as dt
import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.datetime import date


class TestConstruct:
    def test_ground_args_build_a_real_datetime_date(self):
        d = date(2026, 1, 15)
        assert isinstance(d, dt.date)
        assert d == dt.date(2026, 1, 15)

    def test_it_equals_and_hashes_as_a_plain_date(self):
        # so it unifies with engine-produced dates and works as a dict key
        d = date(2026, 1, 15)
        assert d == dt.date(2026, 1, 15)
        assert hash(d) == hash(dt.date(2026, 1, 15))

    def test_python_date_api_is_available(self):
        d = date(2026, 1, 15)
        assert d.isoformat() == "2026-01-15"
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_an_impossible_date_raises_an_ISO_domain_error(self):
        """A term constructor cannot FAIL the way date/4's goal could, so it
        raises — but as an ISO error term, not a bare Python ValueError. An
        impossible date is a fact about the PROGRAM, and ISO has a term for
        it; leaking ValueError would make the one case with a portable
        meaning the one case that does not translate."""
        with pytest.raises(LogicException) as exc:
            date(2025, 2, 29)          # not a leap year
        err = exc.value.args[0] if exc.value.args else None
        assert "domain_error" in repr(err) and "2025, 2, 29" in repr(err)

    def test_a_wrong_typed_component_is_a_type_error_not_a_domain_error(self):
        """ISO's distinction, and the one a reader needs: a typo in the SHAPE
        versus a date that is not a day."""
        with pytest.raises(LogicException) as exc:
            date(2020.9, 1, 1)
        assert "type_error" in repr(exc.value.args[0])

    def test_the_culprit_is_carried_not_just_a_message(self):
        """date/4 recorded a note naming the predicate; the term must not be
        less informative than the thing it replaces."""
        with pytest.raises(LogicException) as exc:
            date(2024, 13, 1)
        assert "date/3" in repr(exc.value.args[0])

    # --- coverage ported from _date_4's tests (todo, 2026-09-01) -------------
    # These were written while `_date_4` was still live, then became its ONLY
    # home: `_date_4` and the `ymd_date/4` alias were deleted the same day, once
    # the last caller migrated. Rejection of 2025-02-29 and of a float YEAR were
    # already covered above; these are the parts that were not, and without them
    # the deletion would have dropped real coverage silently.

    def test_a_real_leap_day_constructs(self):
        """The rejection case above only proves date/3 says NO. Without the
        acceptance case a constructor that rejected EVERY 29 February would
        pass — a gate needs a test that it says YES."""
        d = date(2024, 2, 29)
        assert isinstance(d, dt.date) and d.isoformat() == "2024-02-29"

    def test_a_float_is_rejected_in_every_component_not_just_the_year(self):
        """Audit finding F015: a float component must be REJECTED, never
        int()-truncated, or 2020.9 silently becomes 2020. The existing test
        pins the year; a truncation bug in the month or day slot would have
        gone unseen."""
        for args in ((2020.9, 1, 5), (2020, 1.9, 5), (2020, 1, 5.9)):
            with pytest.raises(LogicException) as exc:
                date(*args)
            assert "type_error" in repr(exc.value.args[0]), args

    def test_a_bool_component_follows_python_and_is_not_an_error(self):
        """PINNED BEHAVIOUR, not an endorsement. `bool` is a subclass of `int`,
        so date(2020, True, 5) is 2020-01-05 — exactly what datetime.date does.
        The corpus's own gold harnesses take the opposite view and exclude bool
        explicitly (`isinstance(x, int) and not isinstance(x, bool)`), so the
        two disagree. Recorded here so that if date/3 is ever made stricter it
        is a decision someone took, not a silent divergence discovered later."""
        assert date(2020, True, 5) == dt.date(2020, 1, 5)


class TestDecompose:
    def test_pattern_unifies_against_a_real_date_and_binds_components(self):
        Y, M, D = Var(), Var(), Var()
        trail = Trail()
        assert unify(date(Y, M, D), dt.date(2026, 1, 15), trail)
        assert (deref(Y), deref(M), deref(D)) == (2026, 1, 15)

    def test_unification_is_symmetric(self):
        Y, M, D = Var(), Var(), Var()
        trail = Trail()
        assert unify(dt.date(2026, 1, 15), date(Y, M, D), trail)
        assert (deref(Y), deref(M), deref(D)) == (2026, 1, 15)

    def test_a_partially_bound_pattern_filters(self):
        D = Var()
        trail = Trail()
        assert unify(date(2026, 1, D), dt.date(2026, 1, 15), trail)
        assert deref(D) == 15
        assert not unify(date(2025, 1, Var()), dt.date(2026, 1, 15), Trail())

    def test_a_datetime_is_not_a_date(self):
        assert not unify(date(Var(), Var(), Var()),
                         dt.datetime(2026, 1, 15, 9, 30), Trail())


class TestOrdering:
    """The regression that motivated this: a Compound named `date` sorts
    its args as STRINGS, so "15" < "2" < "9" and msort returns a wrong
    chronological order without raising."""

    def test_dates_order_chronologically(self):
        assert date(2026, 1, 2) < date(2026, 1, 15)
        assert date(2025, 12, 31) < date(2026, 1, 1)

    def test_sorted_is_chronological_not_lexicographic(self):
        got = sorted([date(2026, 1, 15), date(2026, 1, 2), date(2026, 1, 9)])
        assert got == [dt.date(2026, 1, 2), dt.date(2026, 1, 9), dt.date(2026, 1, 15)]
