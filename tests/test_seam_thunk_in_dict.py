"""A ``++`` escape inside a dict (or set) in a goal-position seam goal.

The thunk collectors used to skip ``DictTerm`` members, so the compiled
query called a ``_pyt_<id>`` global that was never injected (NameError), and
the query-cache key hashed the dict by identity instead of walking it.
Every case runs the same goal with different Python values: a cached query
must read each call's own value.
"""
import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from tests._suffix import SEAM

SRC = '''-module(dtk, [p(X), r(X), n(X), l(X), c(X), kk(X), ss(X), s2(X), d2(X)])
-private([w(X), k, j])
p(X) <- (X == 1)
r({'k': X}) <- (X == 1)
n({'k': {'j': 1}})
l([{'k': 1}])
c(w({'k': X})) <- (X == 1)
kk({1: 5})
ss({1, 2})
s2({1, 2})
d2({'k': 1, 'j': 2})
def flat(a):
    if --p(++a):
        return True
    return False
def indict(a):
    if --r({'k': ++a}):
        return True
    return False
def nested(a):
    if --n({'k': {'j': ++a}}):
        return True
    return False
def inlist(a):
    if --l([{'k': ++a}]):
        return True
    return False
def incompound(a):
    if --c(w({'k': ++a})):
        return True
    return False
def inkey(a):
    if --kk({++a: 5}):
        return True
    return False
def inset(a):
    if --ss({++a, 2}):
        return True
    return False
def inset2(a, b):
    if --s2({++a, ++b}):
        return True
    return False
def indict2(a, b):
    if --d2({'k': ++a, 'j': ++b}):
        return True
    return False
def twice(a, b):
    if --(r({'k': ++a}), r({'k': ++b})):
        return True
    return False
'''


@pytest.fixture(scope="module")
def mod():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, f"dtk{SEAM}")
        with open(path, "w") as fh:
            fh.write(SRC)
        return _load_module("dtk", path)


@pytest.mark.parametrize("fn", ["flat", "indict", "nested", "inlist",
                                "incompound", "inkey", "inset"])
def test_each_call_reads_its_own_value(mod, fn):
    f = getattr(mod, fn)
    # alternating values through one cached query: a stale thunk would repeat
    assert [f(x) for x in (1, 2, 1, 2, 2, 1)] == [
        True, False, True, False, False, True]


def test_two_thunks_in_one_dict_keep_their_slots(mod):
    assert [mod.indict2(*x) for x in ((1, 2), (2, 1), (1, 3), (1, 2))] == [
        True, False, False, True]


def test_two_thunks_in_one_set_are_not_swapped(mod):
    assert [mod.inset2(*x) for x in
            ((1, 2), (2, 1), (1, 3), (3, 1), (2, 2), (1, 2))] == [
        True, True, False, False, False, True]


def test_two_dict_thunks_in_one_conjunction(mod):
    assert [mod.twice(*x) for x in ((1, 1), (1, 2), (2, 1), (1, 1))] == [
        True, False, False, True]


def test_the_cache_key_sees_a_thunk_inside_a_dict():
    from clausal.terms import DictTerm
    from clausal.terms import PyThunk
    from clausal.logic.solve import _structural_key
    seen: list = []
    t = PyThunk(lambda: 1, [])
    _structural_key(DictTerm({"k": DictTerm({"j": t})}), {}, seen)
    assert seen == [t]


def _load_pl(name, src):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, f"{name}.pl")
        with open(path, "w") as fh:
            fh.write(src)
        return _load_module(name, path)


def test_prolog_source_still_refuses_a_plus_plus_escape():
    # ``++`` is a seam-only escape: the Prolog reader never produces a thunk,
    # so the dict fix has no way in.  The message is the reader's own.
    with pytest.raises(SyntaxError) as e:
        _load_pl("dtk_pl", "r(1).\nt :- r(f(++a)).\n")
    assert "Expected ')'" in str(e.value)
