"""A date TERM whose component is bound in the BODY reaches the datetime
predicates as a date, and a date term that is not a date RAISES.

``Y = 2025, ordinal(date(Y, 3, 1), N)`` builds the cell ``('date', Y, 3, 1)``
while Y is unbound and binds Y afterwards, so the predicate receives the cell
holding a BOUND variable.  ``clausal.modules.py.datetime`` converts an incoming
date term to the Python value at one choke point, which dereferenced only the
outer term: ``datetime.date(<Var>, 3, 1)`` raised TypeError, the cell passed
through as "not a date", and every date predicate FAILED the goal -- a silent
``[]`` where the answer is 739311 (``date(2025, 3, 1).toordinal()``).  The
literal ``date(2025, 3, 1)`` and a head-bound Y were unaffected, which is why
it went unseen.

Errors (ISO): a date term with an unbound component where a date is required
is ``instantiation_error``; an ill-typed component is
``type_error(integer, date(...))`` and an impossible date
``domain_error(date, date(...))`` -- the terms ``date/3`` already raises.
A partial term where the predicate can compute the date (the inverse modes)
is unified instead: ``ordinal(date(Y, M, D), 739311)`` binds Y, M, D.
"""
from __future__ import annotations

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from tests._suffix import SEAM

PL = """\
:- module({name}, [s/2]).
:- use_module(library(datetime), [ordinal/2, date_add/3, timedelta/3,
                                  days_between/3, weekday/2,
                                  date_string_iso/2, time/4, date_of/2,
                                  timestamp/2, datetime_string/3,
                                  datetime_string_iso/2]).
s(literal, N) :- ordinal(date(2025, 3, 1), N).
s(head_y, N) :- h(2025, N).
s(body_y, N) :- Y = 2025, ordinal(date(Y, 3, 1), N).
s(body_is, N) :- Y is 2025, ordinal(date(Y, 3, 1), N).
s(body_md, N) :- M = 3, D = 1, ordinal(date(2025, M, D), N).
s(late_bind, N) :- X = date(Y, 3, 1), Y = 2025, ordinal(X, N).
s(nested, N) :- L = [p(date(Y, 3, 1))], Y = 2025, L = [p(Dt)], ordinal(Dt, N).
s(add, R) :- Y = 2026, timedelta(30, 0, TD), date_add(date(Y, 1, 15), TD, R).
s(between, N) :- D = 15, days_between(date(2026, 3, 1), date(2026, 1, D), N).
s(weekday, W) :- Y = 2025, weekday(date(Y, 3, 1), W).
s(iso, S) :- Y = 2025, date_string_iso(date(Y, 3, 1), S).
s(inverse, [Y, M, D]) :- ordinal(date(Y, M, D), 739311).
s(unbound, N) :- ordinal(date(_, 3, 1), N).
s(add_unbound, R) :- timedelta(1, 0, TD), date_add(date(_, 1, 15), TD, R).
s(bad, N) :- Y = foo, ordinal(date(Y, 3, 1), N).
s(impossible, N) :- D = 30, ordinal(date(2025, 2, D), N).
s(inv_timedelta, [D, S]) :- timedelta(3, 0, timedelta(D, S)).
s(inv_time, [H]) :- time(10, 30, 0, time(H, 30, 0)).
s(inv_date_of, [Y]) :- date_of(datetime(Y, 3, 1, 0, 0, 0), date(2025, 3, 1)).
s(inv_timestamp, [Y]) :- timestamp(datetime(Y, _, _, _, _, _), 34560000).
s(inv_date_iso, [Y, M, D]) :- date_string_iso(date(Y, M, D), '2025-03-01').
s(inv_datetime_iso, [Y, H]) :-
    datetime_string_iso(datetime(Y, 3, 1, H, 0, 0), '2025-03-01T10:00:00').
s(inv_datetime_string, [Y]) :-
    datetime_string(datetime(Y, _, _, _, _, _), '2025-01-01', '%Y-%m-%d').
s(i_time, T) :- time(_, 30, 0, time(_, 30, 0)), T = x.
s(i_date_of, D) :- date_of(datetime(_, 3, 1, 0, 0, 0), D).
s(i_timestamp, S) :- timestamp(datetime(_, 1, 1, 0, 0, 0), S).
s(i_date_iso, S) :- date_string_iso(date(_, 3, 1), S).
s(i_days_between, N) :- days_between(date(_, 1, 1), date(2025, 1, 1), N).
s(i_weekday, W) :- weekday(date(_, 1, 1), W).
s(e_arity, N) :- ordinal(date(2025, 3), N).
s(e_timedelta_type, R) :- X = a, date_add(date(2025, 1, 1), timedelta(X, 0), R).
s(e_time_domain, H) :- T = time(25, 0, 0), time(H, _, _, T).
h(Y, N) :- ordinal(date(Y, 3, 1), N).
:- end_module({name}).
"""

SEAM_SRC = """\
-module({name}, [s])
-private([body_y, body_md, late_bind, add, between, inverse, unbound, bad, foo])
-import_from(py.datetime, [date, ordinal, date_add, timedelta, days_between])
s(body_y, N) <- (Y is 2025, ordinal(date(Y, 3, 1), N)),
s(body_md, N) <- (M is 3, D is 1, ordinal(date(2025, M, D), N)),
s(late_bind, N) <- (X is date(Y, 3, 1), Y is 2025, ordinal(X, N)),
s(add, R) <- (Y is 2026, timedelta(30, 0, TD), date_add(date(Y, 1, 15), TD, R)),
s(between, N) <- (D is 15, days_between(date(2026, 3, 1), date(2026, 1, D), N)),
s(inverse, (Y, M, D)) <- (ordinal(date(Y, M, D), 739311)),
s(unbound, N) <- (X is date(_G, 3, 1), ordinal(X, N)),
s(bad, N) <- (X is date(Y, 3, 1), Y is foo, ordinal(X, N)),
"""


def _all(mod, case):
    v = Var()
    return [walk(deref(v)) for _ in call("s", case, v, module=mod)]


def _error(mod, case):
    with pytest.raises(LogicException) as ei:
        _all(mod, case)
    return ei.value.term[1]


@pytest.fixture(params=["native", "translator"])
def pl(request, native):
    name = f"dtbody_{request.param}"
    return native.load(name, PL.format(name=name), frontend=request.param)


@pytest.fixture
def seam(native):
    return native.load("dtbody_seam", SEAM_SRC.format(name="dtbody_seam"),
                       suffix=SEAM, frontend=None)


@pytest.mark.parametrize("case", ["literal", "head_y", "body_y", "body_is",
                                  "body_md", "late_bind", "nested"])
def test_ordinal_of_a_date_term_answers_whenever_its_components_bind(pl, case):
    assert _all(pl, case) == [739311]


def test_the_other_date_predicates_see_the_body_bound_date(pl):
    assert _all(pl, "add") == [("date", 2026, 2, 14)]
    assert _all(pl, "between") == [45]
    assert _all(pl, "weekday") == [5]
    assert _all(pl, "iso") == [("$chars", "2025-03-01")]


def test_a_partial_date_term_is_an_inverse_mode_target(pl):
    assert _all(pl, "inverse") == [[2025, 3, 1]]


def test_an_unbound_component_is_an_instantiation_error(pl):
    assert _error(pl, "unbound") == "instantiation_error"
    assert _error(pl, "add_unbound") == "instantiation_error"


@pytest.mark.parametrize("case, want", [
    ("inv_timedelta", [[3, 0]]),
    ("inv_time", [[10]]),
    ("inv_date_of", [[2025]]),
    ("inv_timestamp", [[1971]]),       # 400 days after the epoch, any zone
    ("inv_date_iso", [[2025, 3, 1]]),
    ("inv_datetime_iso", [[2025, 10]]),
    ("inv_datetime_string", [[2025]]),
])
def test_a_partial_short_form_term_is_an_output_target(pl, case, want):
    assert _all(pl, case) == want


@pytest.mark.parametrize("case", ["i_time", "i_date_of", "i_timestamp",
                                  "i_date_iso", "i_days_between", "i_weekday"])
def test_a_partial_term_with_nothing_to_compute_from_raises(pl, case):
    assert _error(pl, case) == "instantiation_error"


def test_the_wrong_shape_type_and_value_raise(pl):
    assert _error(pl, "e_arity") == ("type_error", "date", ("date", 2025, 3))
    assert _error(pl, "e_timedelta_type") == (
        "type_error", "number", ("timedelta", "a", 0))
    assert _error(pl, "e_time_domain") == (
        "domain_error", "time", ("time", 25, 0, 0))


def test_an_ill_typed_or_impossible_date_term_raises(pl):
    assert _error(pl, "bad") == ("type_error", "integer", ("date", "foo", 3, 1))
    assert _error(pl, "impossible") == ("domain_error", "date",
                                        ("date", 2025, 2, 30))


@pytest.mark.parametrize("case", ["body_y", "body_md", "late_bind"])
def test_seam_body_bound_date_term(seam, case):
    assert _all(seam, case) == [739311]


def test_seam_other_predicates_and_modes(seam):
    assert _all(seam, "add") == [("date", 2026, 2, 14)]
    assert _all(seam, "between") == [45]
    assert _all(seam, "inverse") == [(2025, 3, 1)]
    assert _error(seam, "unbound") == "instantiation_error"
    assert _error(seam, "bad") == ("type_error", "integer",
                                   ("date", "foo", 3, 1))
