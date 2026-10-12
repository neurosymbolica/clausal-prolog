"""append/3 with L1 and L3 known UNIFIES L1's elements with L3's prefix.

The prologue's clause ``append([H|T], L, [H|R]) :- append(T, L, R)`` makes
``append([X], R, [a, b, c])`` answer ``X = a, R = [b, c]``.  The builtin's
(+, -, +) branch compared the prefix with Python's ``==`` instead, so an
unbound or partly bound element of L1 never matched (the goal FAILED), and
``append([1], R, [true, 2])`` succeeded (``1 == True`` in Python).  Every
expected answer below is Scryer's (library(lists), library(freeze),
library(dif); double_quotes chars).

The same audit found split_with/3 and group_by/3 comparing elements with
Python's ``==``: ``true`` split or grouped as 1, and 1 as 1.0.  They now
compare by ==/2, as group_pairs_by_key/2 does.
"""

from __future__ import annotations

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import Var
from clausal.testing import load_clausal_module
from tests._suffix import SEAM as SEAM_EXT

PL = """\
:- set_prolog_flag(double_quotes, chars).
rest([_|T], T).
t1(X, R) :- append([X], R, [a, b, c]).
t2(X, R) :- append([X, b], R, [a, b, c]).
t3(X, R) :- append([X, X], R, [a, a, c]).
t4(X, R) :- append([X, X], R, [a, b, c]).
t5(X, R, Y) :- freeze(X, Y = woke), append([X], R, [a, b, c]).
t6(X, R) :- freeze(X, X == z), append([X], R, [a, b, c]).
t7(X, R) :- dif(X, a), append([X], R, [a, b]).
t8(X, R) :- append([X], R, "abc").
t9(X, R) :- append("ab", R, [X, b, c]).
t10(X, Y, R) :- numlist(0, 100, L), rest(L, T), append([X, Y], R, T).
t11(R) :- append([1], R, [true, 2]).
t12(X, R) :- append([[X], R], [a, b, c]).
t13(X, R) :- append([f(X)], R, [f(a), b]).
s1(P) :- split_with(1, [a, true, b, 1, c, 1.0], P).
key(X, X).
g1(G) :- group_by(key, [1, true, 1.0, 1, 1], G).
"""

SEAM = """\
-private([woke, z])
rest([_, *T], T),
t1(X, R) <- append([X], R, ['a', 'b', 'c'])
t2(X, R) <- append([X, 'b'], R, ['a', 'b', 'c'])
t3(X, R) <- append([X, X], R, ['a', 'a', 'c'])
t4(X, R) <- append([X, X], R, ['a', 'b', 'c'])
t5(X, R, Y) <- (freeze(X, Y is woke), append([X], R, ['a', 'b', 'c']))
t6(X, R) <- (freeze(X, X == z), append([X], R, ['a', 'b', 'c']))
t7(X, R) <- (dif(X, 'a'), append([X], R, ['a', 'b']))
t8(X, R) <- append([X], R, "abc")
t9(X, R) <- append("ab", R, [X, 'b', 'c'])
t10(X, Y, R) <- (numlist(0, 100, L), rest(L, T), append([X, Y], R, T))
t11(R) <- append([1], R, [True, 2])
t12(X, R) <- append([[X], R], ['a', 'b', 'c'])
t13(X, R) <- append([('f', X)], R, [('f', 'a'), 'b'])
s1(P) <- split_with(1, ['a', True, 'b', 1, 'c', 1.0], P)
key(X, X),
g1(G) <- group_by(key, [1, True, 1.0, 1, 1], G)
"""


@pytest.fixture(scope="module", params=[("p.pl", PL), ("p.clausal", PL),
                                        ("p" + SEAM_EXT, SEAM)],
                ids=["pl", "clausal", "seam"])
def mod(request, tmp_path_factory):
    name, text = request.param
    p = tmp_path_factory.mktemp("append_prefix") / name
    p.write_text(text)
    return load_clausal_module(p)


def _plain(v):
    """An answer as plain Python data: a text or a list view is its list of
    chars / elements, so every front end's answer compares alike."""
    from clausal.logic.cells import chars_text, is_chars
    if is_chars(v):
        return list(chars_text(v))
    if isinstance(v, (list, tuple)) or type(v).__name__ == "SegListView":
        out = [_plain(x) for x in v]
        return tuple(out) if isinstance(v, tuple) else out
    return v


def _answers(mod, name, arity):
    vs = [Var() for _ in range(arity)]
    return [tuple(_plain(v.value) for v in vs) for _ in solve((name, *vs), mod)]


@pytest.mark.parametrize("name, arity, expected", [
    ("t1", 2, [("a", ["b", "c"])]),
    ("t2", 2, [("a", ["c"])]),
    ("t3", 2, [("a", ["c"])]),
    ("t4", 2, []),
    ("t5", 3, [("a", ["b", "c"], "woke")]),
    ("t6", 2, []),
    ("t7", 2, []),
    ("t8", 2, [("a", ["b", "c"])]),
    ("t9", 2, [("a", ["c"])]),
    ("t10", 3, [(1, 2, list(range(3, 101)))]),
    ("t11", 1, []),
    ("t12", 2, [("a", ["b", "c"])]),
    ("t13", 2, [("a", ["b"])]),
])
def test_append_unifies_the_prefix(mod, name, arity, expected):
    assert _answers(mod, name, arity) == expected


def test_split_with_finds_the_separator_by_identity(mod):
    assert _answers(mod, "s1", 1) == [([["a", True, "b"], ["c", 1.0]],)]


def test_group_by_keys_are_equal_by_identity(mod):
    assert _answers(mod, "g1", 1) == [([[1], [True], [1.0], [1, 1]],)]


def test_append_on_a_list_view_binds_through_it():
    """L3 a long list VIEW (the rest of a list after a head match) answers
    like the list it stands for, and the bindings go when the call is done."""
    from clausal.terms import SegListView
    from clausal.logic.builtins.lists import _append__3
    from clausal.logic.variables import Trail, deref, is_var
    base = [Var() for _ in range(3)] + list(range(3, 101))
    view = SegListView(base, 1, 101)
    x, r = Var(), Var()
    trail = Trail()
    seen = []
    for sig, _ in _append__3(None, "ok", "no", None, [x, 7], r, view, trail):
        if sig == "ok":
            seen.append((deref(x) is deref(base[1]), deref(base[2]),
                         _plain(deref(r))))
    assert seen == [(True, 7, list(range(3, 101)))]
    assert all(is_var(deref(v)) for v in (x, r, *base[:3]))
