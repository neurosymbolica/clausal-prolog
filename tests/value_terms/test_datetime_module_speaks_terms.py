"""py.datetime produces and consumes TERMS, not Python datetime objects.

Ruled 2026-09-15: "We don't need to use Python date and datetime classes any
more, that ruling comes from before the functor-first-tuple representation.
Internally, we can call back to Python, but the seam shouldn't need dates."

The module's own justification for the Python object was ordering -- that a
compound would sort "15" < "2" < "9". Measured false: the components are
INTEGERS and Y/M/D is most-significant-first, so element-wise standard order IS
chronological order. That is pinned here so it cannot regress silently.
"""
import datetime as _dt
import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from clausal import Var
from clausal.logic.seam import once_bind, each, export

SRC = """-module({name}, [d_today, d_add, d_between, d_sorted, d_weekday,
                        date(Y, M, D), timedelta(Days, Secs)])
-import_from(py.datetime, [today, date_add, days_between, weekday])
d_today(T) <- (today(T)),
d_add(D, N, R) <- (date_add(D, timedelta(N, 0), R)),
d_between(A, B, N) <- (days_between(A, B, N)),
d_weekday(D, W) <- (weekday(D, W)),
d_sorted(S) <- (msort([date(2026,1,15), date(2026,1,2), date(2025,12,31)], S)),
"""


@pytest.fixture(scope="module")
def mod():
    d = tempfile.mkdtemp()
    name = "dtterm"
    p = os.path.join(d, f"{name}.clausal")
    with open(p, "w") as fh:
        fh.write(SRC.format(name=name))
    return _load_module(name, p)


def _one(mod, goal):
    V = Var()
    assert once_bind(goal + (V,), mod.__dict__), f"goal failed: {goal}"
    return export(V)


def test_date_slash_3_is_the_term_not_a_python_date(mod):
    got = _one(mod, ("d_add", ("date", 2026, 1, 15), 0))
    assert got == ("date", 2026, 1, 15)
    assert not isinstance(got, _dt.date)


def test_today_binds_a_term(mod):
    got = _one(mod, ("d_today",))
    assert isinstance(got, tuple) and got[0] == "date" and len(got) == 4
    assert not isinstance(got, _dt.date)


def test_date_arithmetic_consumes_and_produces_terms(mod):
    assert _one(mod, ("d_add", ("date", 2026, 1, 30), 3)) == ("date", 2026, 2, 2)


def test_days_between_consumes_terms(mod):
    # N = whole days in DateA - DateB, per the predicate's own docstring, so
    # the earlier date first gives a NEGATIVE count. Both directions pinned so
    # the sign convention cannot drift with the representation.
    assert _one(mod, ("d_between", ("date", 2026, 1, 31), ("date", 2026, 1, 1))) == 30
    assert _one(mod, ("d_between", ("date", 2026, 1, 1), ("date", 2026, 1, 31))) == -30


def test_weekday_consumes_a_term(mod):
    # 2026-01-15 is a Thursday; whatever the module's encoding, it must not raise
    assert _one(mod, ("d_weekday", ("date", 2026, 1, 15))) is not None


def test_msort_orders_date_terms_CHRONOLOGICALLY(mod):
    """The objection that justified the Python object, pinned as false."""
    assert _one(mod, ("d_sorted",)) == [
        ("date", 2025, 12, 31), ("date", 2026, 1, 2), ("date", 2026, 1, 15)]
