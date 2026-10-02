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
from clausal.modules.py.datetime import _dt_to_term as _T
from clausal.modules.py.datetime import _term_to_dt as _P  # py datetime -> its TERM
from tests._suffix import SEAM


class TestConstruct:
    def test_ground_args_build_a_real_datetime_date(self):
        d = date(2026, 1, 15)
        assert isinstance(_P(d), dt.date)
        assert d == _T(dt.date(2026, 1, 15))

    def test_it_equals_and_hashes_as_a_plain_date(self):
        # so it unifies with engine-produced dates and works as a dict key
        d = date(2026, 1, 15)
        assert d == _T(dt.date(2026, 1, 15))
        assert hash(d) == hash(_T(dt.date(2026, 1, 15)))

    def test_python_date_api_is_available(self):
        d = date(2026, 1, 15)
        assert _P(d).isoformat() == "2026-01-15"
        assert _P(d).year == 2026 and _P(d).month == 1 and _P(d).day == 15

    def test_an_impossible_date_raises_an_ISO_domain_error(self):
        """A term constructor cannot FAIL the way date/4's goal could, so it
        raises — but as an ISO error term, not a bare Python ValueError. An
        impossible date is a fact about the PROGRAM, and ISO has a term for
        it; leaking ValueError would make the one case with a portable
        meaning the one case that does not translate."""
        with pytest.raises(LogicException) as exc:
            date(2025, 2, 29)          # not a leap year
        err = exc.value.args[0] if exc.value.args else None
        assert "domain_error" in err and "date(2025,2,29)" in err

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
        assert isinstance(_P(d), dt.date) and _P(d).isoformat() == "2024-02-29"

    def test_the_century_rule_both_ways(self):
        """2024 and 2025 prove the four-year rule and nothing else. The century
        rule has its own two branches: a year divisible by 100 is NOT a leap
        year (2100-02-29 does not exist) unless it is divisible by 400
        (2000-02-29 does). A leap-day test that picks an ordinary leap year
        reads as coverage of the recovery path and never reaches it — found
        the hard way in a corpus clamp rule on 2026-09-08."""
        with pytest.raises(LogicException) as exc:
            date(2100, 2, 29)          # century, not a leap year
        assert "domain_error" in repr(exc.value.args[0])
        d = date(2000, 2, 29)          # century divisible by 400: a leap year
        assert isinstance(_P(d), dt.date) and _P(d).isoformat() == "2000-02-29"

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
        assert date(2020, True, 5) == _T(dt.date(2020, 1, 5))


class TestDecompose:
    def test_pattern_unifies_against_a_real_date_and_binds_components(self):
        Y, M, D = Var(), Var(), Var()
        trail = Trail()
        assert unify(date(Y, M, D), _T(dt.date(2026, 1, 15)), trail)
        assert (deref(Y), deref(M), deref(D)) == (2026, 1, 15)

    def test_unification_is_symmetric(self):
        Y, M, D = Var(), Var(), Var()
        trail = Trail()
        assert unify(_T(dt.date(2026, 1, 15)), date(Y, M, D), trail)
        assert (deref(Y), deref(M), deref(D)) == (2026, 1, 15)

    def test_a_partially_bound_pattern_filters(self):
        D = Var()
        trail = Trail()
        assert unify(date(2026, 1, D), _T(dt.date(2026, 1, 15)), trail)
        assert deref(D) == 15
        assert not unify(date(2025, 1, Var()), _T(dt.date(2026, 1, 15)), Trail())

    def test_a_datetime_is_not_a_date(self):
        assert not unify(date(Var(), Var(), Var()),
                         _T(dt.datetime(2026, 1, 15, 9, 30)), Trail())


class TestARawPythonDateIsNotATerm:
    """What the deleted ``_DatePattern.__unify__`` claimed to cover: a date
    PATTERN meeting a raw ``datetime.date`` binds Y/M/D, and a raw
    ``datetime.datetime`` is excluded.  No pattern object ever reached that
    hook (a pattern is the cell ``("date", Y, M, D)``), so on the tree before
    W4b-3 slice 7a as on this one, a raw Python date is NOT a term: it does not
    unify with a pattern, and a goal holding one is refused with a pointer to
    the term.  The date TERM (``_dt_to_term``) is the one that binds -- see
    ``TestDecompose``, which pins bind / symmetric / partial / datetime
    excluded on it.  Measured identical on 3a8697c2 (before) and after."""

    @pytest.mark.parametrize("raw", [dt.date(2026, 1, 15),
                                     dt.datetime(2026, 1, 15, 9, 30)])
    def test_a_pattern_cell_does_not_unify_with_a_raw_value(self, raw):
        Y, M, D = Var(), Var(), Var()
        assert not unify(date(Y, M, D), raw, Trail())
        assert not unify(raw, ("date", Var(), Var(), Var()), Trail())
        assert all(deref(v) is v for v in (Y, M, D))

    def test_converted_to_the_term_it_binds_and_a_datetime_is_still_excluded(self):
        Y, M, D = Var(), Var(), Var()
        assert unify(("date", Y, M, D), _T(dt.date(2026, 1, 15)), Trail())
        assert (deref(Y), deref(M), deref(D)) == (2026, 1, 15)
        assert _T(dt.datetime(2026, 1, 15, 9, 30))[0] == "datetime"
        assert not unify(("date", Var(), Var(), Var()),
                         _T(dt.datetime(2026, 1, 15, 9, 30)), Trail())

    @pytest.mark.parametrize("raw, kind", [(dt.date(2026, 1, 15), "date"),
                                           (dt.datetime(2026, 1, 15, 9, 30),
                                            "datetime")])
    def test_a_goal_holding_a_raw_value_is_refused_with_the_term_spelled(
            self, tmp_path, raw, kind):
        import sys
        from clausal.import_hook import _load_module
        from clausal.logic.solve import solve
        path = tmp_path / f"s7_raw_dates{SEAM}"
        path.write_text(
            "-import_from(date_time, [date])\n"
            "-module(s7_raw_dates, [parts(D, Y, M, DD)])\n"
            "parts(D, Y, M, DD) <- (date(Y, M, DD) is D)\n")
        sys.modules.pop("s7_raw_dates", None)
        try:
            mod = _load_module("s7_raw_dates", str(path)).__dict__["$module"]
            with pytest.raises(NotImplementedError) as info:
                list(solve(("parts", raw, Var(), Var(), Var()), module=mod))
        finally:
            sys.modules.pop("s7_raw_dates", None)
        assert f"a Python {kind} is not a term" in str(info.value)
        assert f"('{kind}', 2026, 1, 15" in str(info.value)


class TestOrdering:
    """The regression that motivated this: a Compound named `date` sorts
    its args as STRINGS, so "15" < "2" < "9" and msort returns a wrong
    chronological order without raising."""

    def test_dates_order_chronologically(self):
        assert date(2026, 1, 2) < date(2026, 1, 15)
        assert date(2025, 12, 31) < date(2026, 1, 1)

    def test_sorted_is_chronological_not_lexicographic(self):
        got = sorted([date(2026, 1, 15), date(2026, 1, 2), date(2026, 1, 9)])
        assert got == [_T(dt.date(2026, 1, 2)), _T(dt.date(2026, 1, 9)), _T(dt.date(2026, 1, 15))]


class TestDateTermShapesInAModule:
    """The shapes a date-consuming module relies on, end to end in a loaded
    module (W4b-3 slice 7 deleted the unused ``_DatePattern`` class; these
    pin that the date TERM behaves as before), one test each: construct,
    decompose a real date term, the ``ground(V), date(_, _, _) is V`` test
    REFUSING an unbound ``V``, and -- why that guard is needed -- the same
    test without it BINDING an unbound ``V`` to a pattern."""

    SRC = (
        "-import_from(date_time, [date])\n"
        "-module(s7_dates, [mk(D), parts(D, Y, M, DD), is_day(V), shape(V)])\n"
        "mk(D) <- (D is date(2026, 1, 15))\n"
        "parts(D, Y, M, DD) <- (date(Y, M, DD) is D)\n"
        "is_day(V) <- (ground(V), date(_, _, _) is V)\n"
        "shape(V) <- (date(_, _, _) is V)\n"
    )

    @pytest.fixture
    def mod(self, tmp_path):
        import sys
        from clausal.import_hook import _load_module
        path = tmp_path / f"s7_dates{SEAM}"
        path.write_text(self.SRC)
        sys.modules.pop("s7_dates", None)
        try:
            yield _load_module("s7_dates", str(path)).__dict__["$module"]
        finally:
            sys.modules.pop("s7_dates", None)

    def _all(self, mod, goal, *args):
        from clausal.logic.solve import solve
        from clausal.logic.variables import walk
        return [tuple(walk(a) for a in args)
                for _ in solve((goal, *args), module=mod)]

    def test_construct(self, mod):
        D = Var()
        assert self._all(mod, "mk", D) == [(("date", 2026, 1, 15),)]

    def test_decompose_a_real_date_term(self, mod):
        Y, M, DD = Var(), Var(), Var()
        got = self._all(mod, "parts", ("date", 2026, 1, 15), Y, M, DD)
        assert [g[1:] for g in got] == [(2026, 1, 15)]

    def test_the_ground_guard_refuses_an_unbound_value(self, mod):
        assert self._all(mod, "is_day", Var()) == []
        assert len(self._all(mod, "is_day", ("date", 2026, 1, 15))) == 1
        assert self._all(mod, "is_day", [2026, 1, 15]) == []

    def test_without_the_guard_an_unbound_value_is_BOUND_to_a_pattern(self, mod):
        """Why the guard is load-bearing: ``date(_, _, _) is V`` on an unbound
        V does not test, it binds V to a pattern cell."""
        (v,), = self._all(mod, "shape", Var())
        assert v[0] == "date" and len(v) == 4
