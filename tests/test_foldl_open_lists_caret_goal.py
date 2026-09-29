"""ISO answers (checked on Scryer 2026-09-28) for:

* foldl/4-6 backtrack into every call, as maplist does (Scryer's
  library(lists) defines them by call/N); foldl/5 and foldl/6 exist;
* maplist/2,3, foldl and the ``in`` goal on an OPEN list (unbound, or
  partial) enumerate as the prologue's recursion does;
* ``call(Y^G)`` is existence_error(procedure, (^)/2): ``^`` is a goal only
  inside bagof/setof's iterated goal; with an extra argument it is
  library(lambda)'s (^)/3, a builtin.
"""

from __future__ import annotations

import itertools
import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException, render_error_term
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var, is_var
from clausal.terms import ConcreteSeg, SegList

_SRC = """\
-allow_singletons
-private([a, b, c])
p(1),
p(2),
add(X, A0, A) <- (A == A0 + X)
alt(X, A0, A) <- (p(Y), A == A0 + X * Y)
alt5(X, Y, A0, A) <- (p(Z), A == A0 + X * Y * Z)
f4(S) <- foldl(alt, [1, 10], 0, S)
f5(S) <- foldl(alt5, [1, 10], [1, 1], 0, S)
f5_builds(Y, S) <- foldl(alt5, [1, 10], Y, 0, S)
f6(S) <- foldl(((X, Y, Z, A0, A) <- (A == A0 + X + Y + Z)), [1, 2], [3, 4], [5, 6], 0, S)
f_open(L, S) <- foldl(add, L, 0, S)
m_open(L) <- maplist(p, L)
m_partial(L) <- (L is [2, *T], maplist(p, L))
m3_open(L) <- maplist(((X, Y) <- (Y == X + 1)), L, [5, 6])
in_open(L) <- (1 in L)
in_partial(L) <- (L is [a, *T], b in L)
not_in_partial(L) <- (L is [a, *T], b not in L)
not_in_closed(L) <- (L is [a, b], c not in L)
caret(Y) <- call(Y^p(Y))
caret_cell(Y) <- call('^'(Y, p(Y)))
caret_extra(Y) <- call(Y^p(Y), 1)
caret_cell_extra(Y) <- call('^'(Y, p(Y)), 1)
bagof_caret(L) <- bagof(X, Y^p(X), L)
"""


@pytest.fixture(scope="module")
def mod():
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                     delete=False) as f:
        f.write(_SRC)
        path = f.name
    try:
        return _load_module("_foldl_open_lists_caret_goal", path)
    finally:
        os.unlink(path)


def _shape(t):
    """A walked answer with each unbound variable as ``_``; a partial list
    is its known elements followed by ``"|_"``."""
    t = _deref_walk(t)
    if is_var(t):
        return "_"
    if isinstance(t, list):
        return [_shape(e) for e in t]
    if isinstance(t, SegList):
        out = []
        for seg in t.segments:
            if isinstance(seg, ConcreteSeg):
                out.extend(_shape(e) for e in seg.elements)
            else:
                out.append("|_")
        return out
    return t


def _answers(mod, name, n=1, limit=6):
    vs = [Var() for _ in range(n)]
    out = []
    for _ in itertools.islice(solve((name, *vs), mod), limit):
        got = tuple(_shape(v) for v in vs)
        out.append(got[0] if n == 1 else got)
    return out


def _error(mod, name):
    try:
        for _ in solve((name, Var()), mod):
            return "succeeds"
    except LogicException as exc:
        return render_error_term(exc.term)
    return "fails"


# Scryer: findall(S, foldl(alt, [1, 10], 0, S), L) -> [11, 21, 12, 22]
def test_foldl4_backtracks_into_every_call(mod):
    assert _answers(mod, "f4") == [11, 21, 12, 22]


def test_foldl5_backtracks_into_every_call(mod):
    assert _answers(mod, "f5") == [11, 21, 12, 22]


def test_foldl5_builds_an_unbound_list(mod):
    got = _answers(mod, "f5_builds", 2)
    assert len(got) == 4 and all(y == ["_", "_"] for y, _ in got)


def test_foldl6(mod):
    assert _answers(mod, "f6") == [21]


# Scryer: foldl(add, L, 0, S) -> L = [], S = 0 ; L = [_A], S = _A ; ...
def test_foldl_on_an_open_list_enumerates(mod):
    got = _answers(mod, "f_open", 2, limit=3)
    assert [l for l, _ in got] == [[], ["_"], ["_", "_"]]
    assert got[0][1] == 0


# Scryer: maplist(p, L) -> [] ; [1] ; [1, 1] ; ... (depth first)
def test_maplist_on_an_unbound_list_enumerates(mod):
    assert _answers(mod, "m_open", limit=4) == [[], [1], [1, 1], [1, 1, 1]]


def test_maplist_on_a_partial_list_enumerates(mod):
    assert _answers(mod, "m_partial", limit=3) == [[2], [2, 1], [2, 1, 1]]


def test_maplist3_open_first_list_bounded_by_the_second(mod):
    assert _answers(mod, "m3_open") == [[4, 5]]


# Scryer: member(1, L) -> [1|_] ; [_, 1|_] ; ...
def test_in_on_an_unbound_list_enumerates(mod):
    assert _answers(mod, "in_open", limit=3) == [
        [1, "|_"], ["_", 1, "|_"], ["_", "_", 1, "|_"]]


def test_in_on_a_partial_list_enumerates(mod):
    assert _answers(mod, "in_partial", limit=2) == [
        ["a", "b", "|_"], ["a", "_", "b", "|_"]]


def test_not_in_on_an_open_list_fails_and_binds_nothing(mod):
    assert _answers(mod, "not_in_partial") == []
    assert _answers(mod, "not_in_closed") == [["a", "b"]]


# Scryer: call(Y^p(Y)) -> error(existence_error(procedure, (^)/2), (^)/2)
@pytest.mark.parametrize("name, want", [
    ("caret", "error(existence_error(procedure,(^)/2),(^)/2)"),
    ("caret_cell", "error(existence_error(procedure,(^)/2),(^)/2)"),
])
def test_call_of_a_caret_goal_is_an_existence_error(mod, name, want):
    assert _error(mod, name) == want


# With an extra argument the fold is library(lambda)'s (^)/3, a builtin:
# Scryer (library(lambda) loaded): call(Y^p(Y), 1) -> Y = 1.  The operator
# node and the cell spelling answer alike.
@pytest.mark.parametrize("name", ["caret_extra", "caret_cell_extra"])
def test_call_of_a_caret_goal_with_an_extra_is_the_lambda_hat(mod, name):
    assert _answers(mod, name) == [1]


def test_bagof_still_reads_the_caret(mod):
    assert _answers(mod, "bagof_caret") == [[1, 2]]
