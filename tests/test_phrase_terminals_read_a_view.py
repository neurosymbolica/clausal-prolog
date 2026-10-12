"""A terminal in a phrase/2,3 body is ISO's ``S0 = [T|S]`` (7.14.2), and
append(L1, L2, L3) with L1 and L3 known reads only len(L1) elements of L3.

Both used to copy the whole rest of L3 at every call: the run-time
translation of a terminal was ``append(T, S, S0)``, and append/3 turned all
of L3 into one list entry per element.  So walking a long text with
``phrase((anything, [X]), S)`` copied about n^2/2 chars, and each copy stayed
cached on a text view that a choice point kept alive.  These tests count the
chars copied out of text views and check the answers, so they do not depend
on time.
"""
from __future__ import annotations

import pytest

from clausal.logic import cells
from clausal.logic.cells import chars, text_slice, CHARS_TAG
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.terms import SegListView, list_rest
from clausal.testing import load_clausal_module

_SRC = """\
anything --> [].
anything --> [_], anything.
last(S, X) :- phrase((anything, [X]), S).
one(S, X) :- phrase([X], S).
two(S, X, R) :- phrase([X, b], S, R).
gen(S0, X) :- phrase([X], S0, "bc").
app(L1, R, L3) :- append(L1, R, L3).
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("terminals") / "terminals.clausal"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _answers(mod, name, *args):
    out = [Var() for _ in range(sum(a is None for a in args))]
    it = iter(out)
    goal = (name, *[next(it) if a is None else a for a in args])
    return [tuple(deref(v) for v in out) for _ in solve(goal, mod)]


@pytest.fixture
def copied(monkeypatch):
    """Chars copied out of text views (a view's whole text built as a str)."""
    count = [0]
    orig = cells._Text.flat.fget

    def flat(self):
        if self._flat is None:
            count[0] += self.hi - self.lo
        return orig(self)
    monkeypatch.setattr(cells._Text, "flat", property(flat))
    return count


@pytest.mark.parametrize("seq, last", [
    (chars("abc"), "c"), (["a", "b", "c"], "c"), (chars("a"), "a"),
    (["a"], "a"), (b"ab", 98), (chars("ab" * 100), "b"),
])
def test_phrase_body_terminal_answers(mod, seq, last):
    assert [x for (x,) in _answers(mod, "last", seq, None)] == [last]


def test_phrase_body_terminal_with_the_end_given(mod):
    assert _answers(mod, "one", chars("a"), None) == [("a",)]
    assert _answers(mod, "one", chars("ab"), None) == []
    assert _answers(mod, "one", chars(""), None) == []
    (x, r), = _answers(mod, "two", chars("abc"), None, None)
    assert x == "a" and r == chars("c")


def test_phrase_body_terminal_builds_s0(mod):
    (s0, x), = _answers(mod, "gen", None, None)
    assert s0 == [x, "b", "c"]


def test_walking_a_long_text_with_a_phrase_body_copies_none_of_it(mod, copied):
    n = 3000
    assert [x for (x,) in _answers(mod, "last", chars("ab" * (n // 2)), None)] == ["b"]
    assert copied[0] < n           # was about n*n/2


def test_append_reads_only_the_prefix_of_a_long_list(mod):
    base = list(range(1000))
    (r,), = [(deref(v),) for v in [Var()]
             for _ in solve(("app", [0, 1], v, base), mod)]
    assert type(r) is SegListView and r == base[2:]
    view = list_rest(base, 10, 1000)
    (r,), = [(deref(v),) for v in [Var()]
             for _ in solve(("app", [10], v, view), mod)]
    assert type(r) is SegListView and r == base[11:]
    X, R = Var(), Var()
    assert [(deref(X), len(deref(R))) for _ in solve(("app", [X], R, base), mod)] == [(0, 999)]


def _append_answers(l1, l2, l3):
    """append/3's own answers, without solve()'s query cache (which keys a
    text argument by its whole text)."""
    from clausal.logic.builtins.lists import _append__3
    from clausal.logic.variables import Trail
    proceed, out = object(), []
    for sig, _ in _append__3(None, proceed, None, None, l1, l2, l3, Trail()):
        if sig is proceed:
            out.append((deref(l1), deref(l2)))
    return out


def test_append_reads_only_the_prefix_of_a_long_text(copied):
    n = 5000
    text = (CHARS_TAG, text_slice("ab" * n, 0, 2 * n))
    R = Var()
    (_, r), = _append_answers(chars("ab"), R, text)             # text L1: text rest
    assert copied[0] == 0 and type(r[1]) is cells._Text
    X, R = Var(), Var()
    l1 = [X]
    (got_l1, r2), = _append_answers(l1, R, text)                # list L1: list rest
    assert copied[0] <= 2 * n      # the rest, once, from a slice; never L3's view itself
    assert text[1]._flat is None
    assert r == chars("ab" * (n - 1)) and r2 == list("b" + "ab" * (n - 1))
