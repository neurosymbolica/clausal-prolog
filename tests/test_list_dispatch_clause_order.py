"""A predicate dispatched on the structure of a list argument answers in
clause order.

The list dispatch runs the clauses whose head has ``[]`` there, or a
variable, when the argument is ``[]`` (and the ``[_|_]`` and variable ones
for a non-empty list, all of them for an unbound one).  It collected the
``[]`` (``[_|_]``) clauses first and the variable-headed ones after, so a
variable-headed clause written first answered after them:
``lo(_, any).  lo([], nil).`` gave ``lo([], X)`` as nil, any where ISO and
Scryer give any, nil.  The fixtures hold the same predicates in the three
source surfaces; ``gz/4`` has a tail-recursive clause besides.
"""
from __future__ import annotations

import os

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_SURFACES = ["list_dispatch_order.pl", "list_dispatch_order.clausal",
             "list_dispatch_order.seam"]


@pytest.fixture(scope="module", params=_SURFACES)
def mod(request):
    name = "tests.fixtures." + request.param.replace(".", "_")
    return _load_module(name, os.path.join(_FIXTURES, request.param))


def _answers(mod, name, *args):
    lm = mod.__dict__["$module"]
    out = Var()
    vals = [Var() if a is None else a for a in args]
    return [deref(out) for _ in call(name, *vals, out, module=lm)]


def test_the_list_argument_dispatches():
    """lo/2 (in .pl) is compiled with the list dispatch this file is about."""
    mod = _load_module("tests.fixtures.list_dispatch_order_pl_probe",
                       os.path.join(_FIXTURES, "list_dispatch_order.pl"))
    fn = mod.__dict__["$module"].db.get_dispatch("lo", 2)
    assert "$isinstance" in fn.__code__.co_names


def test_answers_in_clause_order(mod):
    assert _answers(mod, "lo", []) == ["any", "nil", "last"]
    assert _answers(mod, "lo", ["a"]) == ["any", "cons", "last"]
    assert _answers(mod, "lo", None) == ["any", "nil", "cons", "last"]
    assert _answers(mod, "lo", 3) == ["any", "last"]


def test_a_tail_recursive_clause_beside_the_dispatch(mod):
    # Scryer: seven(2), seven(1), seven(0), zero(0).
    assert _answers(mod, "gz", [], 2, 7) == [
        ("seven", 2), ("seven", 1), ("seven", 0), ("zero", 0)]
    assert _answers(mod, "gz", ["a"], 1, 7) == [
        ("seven", 1), ("seven", 1), ("seven", 0), ("zero", 0)]
    assert _answers(mod, "gz", [], 2, 0) == [("zero", 0)]
