"""A TRO restart waits for a head's deferred list binding.

A clause head with a list pattern meets an unbound argument by binding it
only at the answer (``$head_list_unify_output``), so a call with that
argument unbound had nothing on the trail yet when its tail call came, and
``trail.commit_fresh`` let the in-place restart through: the restart skips
the answer, and the binding with it.  ``pq([], N) :- N > 0, M is N - 1,
pq([], M).  pq([], 0).`` answered ``pq(L, 2)`` with L unbound, where ISO
and Scryer give L = [].  The restart now also needs the list pattern to
have matched an argument that was already a list; otherwise the tail is
an ordinary call.  The fixtures hold the same predicates in the three
source surfaces.
"""
from __future__ import annotations

import os
import tracemalloc

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import term_str

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_SURFACES = ["tro_deferred_list.pl", "tro_deferred_list.clausal",
             "tro_deferred_list.seam"]


@pytest.fixture(scope="module", params=_SURFACES)
def mod(request):
    name = "tests.fixtures." + request.param.replace(".", "_")
    return _load_module(name, os.path.join(_FIXTURES, request.param))


def _first_args(mod, name, *args):
    lm = mod.__dict__["$module"]
    vals = [Var() if a is None else a for a in args]
    return [term_str(deref(vals[0])) for _ in call(name, *vals, module=lm)]


def test_an_unbound_list_argument_is_bound(mod):
    assert _first_args(mod, "pq", None, 2) == ["[]"]
    assert _first_args(mod, "pq", None, 0) == ["[]"]
    lm = mod.__dict__["$module"]
    lst = Var()
    heads = [deref(lst)[0] for _ in call("pc", lst, 2, module=lm)]
    assert heads == ["a"]


def test_a_bound_list_argument_still_restarts(mod):
    lm = mod.__dict__["$module"]
    tracemalloc.start()
    try:
        assert sum(1 for _ in call("pq", [], 30000, module=lm)) == 1
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8_000_000, f"peak {peak / 1e6:.1f} MB"
