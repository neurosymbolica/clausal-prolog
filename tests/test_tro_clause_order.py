"""Last-call optimisation (TRO) keeps the order of answers.

A tail-recursive clause restarts its predicate in place: it records the tail
call's arguments, the clauses after it still run, and only then does the
predicate start over.  Where a later clause answers the same call, its
answer came out before every answer of the tail call -- clause order
reversed: ``p(N, X) :- N > 0, M is N - 1, p(M, X).  p(N, N).`` gave
``p(3, X)`` as X = 3, 2, 1, 0, where ISO Prolog gives 0, 1, 2, 3.

A clause now restarts in place only where no later clause can answer first:
the last clause, a clause that cuts before its tail, a later head that
cannot unify with this one, a later clause an arithmetic comparison made
before the tail rules out, or a later clause keyed out by the call's bound
argument (a runtime test).  Elsewhere the tail is an ordinary call.  The
fixtures hold the same predicates in the three source surfaces.
"""
from __future__ import annotations

import os
import tracemalloc

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_SURFACES = ["tro_clause_order.pl", "tro_clause_order.clausal",
             "tro_clause_order.seam"]


@pytest.fixture(scope="module", params=_SURFACES)
def mod(request):
    name = "tests.fixtures." + request.param.replace(".", "_")
    return _load_module(name, os.path.join(_FIXTURES, request.param))


def _answers(mod, name, *args):
    """The answers of ``name(*args, Out)``, the last argument's values."""
    lm = mod.__dict__["$module"]
    out = Var()
    return [deref(out) for _ in call(name, *args, out, module=lm)]


def _succeeds(mod, name, *args):
    lm = mod.__dict__["$module"]
    return sum(1 for _ in call(name, *args, module=lm))


def _restarts_in_place(mod, name, arity):
    fn = mod.__dict__["$module"].db.get_dispatch(name, arity)
    return "commit_fresh" in fn.__code__.co_names


def test_answers_come_in_clause_order(mod):
    assert _answers(mod, "p", 3) == [0, 1, 2, 3]
    assert _answers(mod, "p", 0) == [0]
    assert _answers(mod, "p", -1) == [-1]


def test_the_first_answer_is_the_deepest(mod):
    lm = mod.__dict__["$module"]
    out = Var()
    for _ in call("p", 5, out, module=lm):
        assert deref(out) == 0
        break
    else:
        pytest.fail("p(5, X) has no answer")


def test_a_clause_whose_later_clause_answers_makes_the_ordinary_call(mod):
    assert not _restarts_in_place(mod, "p", 2)


@pytest.mark.parametrize("name,arity", [
    ("cnt", 1), ("len", 3), ("down", 1), ("up", 2)])
def test_a_clause_no_later_clause_can_answer_after_restarts(mod, name, arity):
    assert _restarts_in_place(mod, name, arity)


def test_answers_of_the_restarting_loops(mod):
    assert _succeeds(mod, "cnt", 3) == 1
    assert _succeeds(mod, "cnt", 0) == 1
    assert _succeeds(mod, "cnt", -1) == 0
    assert _answers(mod, "len", ["a", "b", "c"], 0) == [3]
    assert _answers(mod, "len", [], 4) == [4]
    assert _succeeds(mod, "down", 3) == 1
    assert _succeeds(mod, "down", -2) == 1
    assert _succeeds(mod, "up", 0, 3) == 1
    assert _succeeds(mod, "up", 4, 3) == 0


@pytest.mark.parametrize("name", ["cnt", "len", "down", "up"])
def test_a_long_loop_runs_in_bounded_memory(mod, name):
    n = 30000
    args = {"cnt": (n,), "len": ([0] * n, 0, Var()), "down": (n,),
            "up": (0, n)}[name]
    lm = mod.__dict__["$module"]
    tracemalloc.start()
    try:
        assert sum(1 for _ in call(name, *args, module=lm)) == 1
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8_000_000, f"{name}: peak {peak / 1e6:.1f} MB for {n} iterations"
