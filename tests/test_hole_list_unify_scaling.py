"""`=`/2 and `==`/2 on two hole-built lists are linear in their length.

A list built forward through its open tail (``X = [N|T]``, then the same
for ``T``) is a chain of partial lists, one ``SegList`` link per element.
todo/done/hole-built-list-unify-and-eq-are-quadratic-2026-10-24.md suspected
that unifying or comparing two such chains re-walked the rest of the chain
at every link.  These tests pin that they do not: they count the Python and
C function calls one `=` or `==` makes (``sys.setprofile``) at two lengths,
four times apart, and require the count to grow about four times, not
sixteen.  A count, not a clock, so the test is deterministic on a loaded
machine.

The chains are built by the native front end (``mkf/3`` below), so they
are the shape a program makes, with every tail a program can give them:
the empty list, an atom (an improper list), and one shared unbound tail.
"""
from __future__ import annotations

import sys

import pytest

from clausal.logic.builtins.iso_compare import _iso_identical
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, deref, unify
from clausal.terms import SegList
from clausal.testing import load_clausal_module

_PROGRAM = """\
mkf(0, L, L).
mkf(N, L, X) :- N > 0, X = [N|T], N1 is N-1, mkf(N1, L, T).
pair(N, Z, A, B) :- mkf(N, Z, A), mkf(N, Z, B).
u(Z) :- mkf(300, Z, L), mkf(300, Z, L2), L = L2.
e(Z) :- mkf(300, Z, L), mkf(300, Z, L2), L == L2.
ud(Z) :- mkf(300, Z, L), mkf(299, Z, T), L2 = [301|T], L = L2.
ed(Z) :- mkf(300, Z, L), mkf(299, Z, T), L2 = [301|T], L == L2.
"""

SMALL, LARGE = 500, 2000          # LARGE / SMALL = 4
LINEAR_BOUND = 6                  # linear grows ~4x; quadratic ~16x


@pytest.fixture(scope="module")
def m(tmp_path_factory):
    path = tmp_path_factory.mktemp("hole_list") / "mkf.clausal"
    path.write_text(_PROGRAM)
    return load_clausal_module(path)


_KEEP: list = []


@pytest.fixture(autouse=True)
def _close_searches():
    """Each test's searches stay open while it runs and are closed after,
    so no binding outlives the test."""
    yield
    while _KEEP:
        _KEEP.pop().close()


def _two_chains(m, n, tail, last=None):
    """Two hole-built lists of *n* elements ending in *tail* (``"var"``:
    one unbound variable both share).  *last*, when given, replaces the
    last element of the second list, so the two differ only at the end."""
    z = Var() if tail == "var" else tail
    a, b = Var(), Var()
    # The search stays open (``_KEEP``): closing it would undo the bindings
    # that link the chain.
    search = solve(("pair", n, z, a, b), m)
    next(search)
    _KEEP.append(search)
    a, b = deref(a), deref(b)
    assert type(a) is SegList and type(b) is SegList   # a chain, not a flat list
    if last is not None:
        link = b
        for _ in range(n - 1):
            link = deref(link._segments[-1].var)
        link._segments[0].elements[0] = last
    return a, b


def _calls(fn):
    """The function calls (Python and C) *fn* makes, and its result."""
    count = 0

    def profile(frame, event, arg):
        nonlocal count
        if event in ("call", "c_call"):
            count += 1

    sys.setprofile(profile)
    try:
        result = fn()
    finally:
        sys.setprofile(None)
    return count, result


def _unify(a, b):
    trail = Trail()
    mark = trail.mark()
    try:
        return unify(a, b, trail)
    finally:
        trail.undo(mark)


_OPS = {
    "=": _unify,
    "==": _iso_identical,
}

_TAILS = ["nil", "foo", "var"]


def _tail(name):
    return {"nil": [], "foo": "foo", "var": "var"}[name]


@pytest.mark.parametrize("tail", _TAILS)
@pytest.mark.parametrize("op", sorted(_OPS))
def test_two_equal_chains_take_linear_work(m, op, tail):
    fn = _OPS[op]
    small = _two_chains(m, SMALL, _tail(tail))
    large = _two_chains(m, LARGE, _tail(tail))
    c_small, r_small = _calls(lambda: fn(*small))
    c_large, r_large = _calls(lambda: fn(*large))
    assert r_small is True and r_large is True
    assert c_large < LINEAR_BOUND * c_small, (
        f"{op} on two {tail}-tailed chains: {c_small} calls at {SMALL}, "
        f"{c_large} at {LARGE} (x{c_large / c_small:.1f}; linear is ~x4)")


@pytest.mark.parametrize("tail", _TAILS)
@pytest.mark.parametrize("op", sorted(_OPS))
def test_two_chains_differing_at_the_end_take_linear_work(m, op, tail):
    fn = _OPS[op]
    small = _two_chains(m, SMALL, _tail(tail), last=-1)
    large = _two_chains(m, LARGE, _tail(tail), last=-1)
    c_small, r_small = _calls(lambda: fn(*small))
    c_large, r_large = _calls(lambda: fn(*large))
    assert r_small is False and r_large is False
    assert c_large < LINEAR_BOUND * c_small, (
        f"{op} on two {tail}-tailed chains differing at the end: "
        f"{c_small} calls at {SMALL}, {c_large} at {LARGE} "
        f"(x{c_large / c_small:.1f}; linear is ~x4)")


@pytest.mark.parametrize("tail", _TAILS)
def test_the_answers_through_the_engine(m, tail):
    """The same goals as a program writes them: `=` and `==` succeed on two
    equal chains and fail on two that differ in one element."""
    def count(name):
        return sum(1 for _ in solve((name, Var() if tail == "var" else _tail(tail)), m))
    assert [count(g) for g in ("u", "e", "ud", "ed")] == [1, 1, 0, 0]
