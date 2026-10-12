"""append/3 builds ``[L1's elements | L2]`` for ANY L2, as the prologue's
two clauses do -- ``append([], L, L)`` never looks at L.  The builtin
answered nothing when L2 was not a list, a partial list or a variable:
``append([x], foo, L)`` failed where ISO, Scryer and Trealla answer
``L = [x|foo]`` (an improper list, the cons cell ``'.'(x, foo)``, D50).
Every expected line below is what Scryer and Trealla print for the goal
(``writeq`` of each answer, failure-driven)."""
from __future__ import annotations

import pytest

SRC = """\
a1(L) :- append([x], foo, L).
a2(X-T) :- append([X], foo, [a|T]).
a3(L) :- append([], foo, L).
a4(L) :- append(L, foo, [a|foo]).
a5(L) :- append(L, foo, [a, b|foo]).
a6(L-R) :- append(L, R, [a|foo]).
a7(L) :- append([x], foo, [x|L]).
a8(yes) :- append([x], foo, [x|foo]).
a9(L) :- append([x, y], [z|foo], L).
a10(L-R) :- append(L, R, foo).
a11(L) :- append([x], f(1), L).
a12(R) :- append([], R, foo).
a13(yes) :- append([x], foo, [x]).
a14(L) :- append(L, foo, [a]).
a15(L) :- append([x], 1, L).
show(G) :- ( call(G, A), writeq(A), nl, fail ; true ).
"""

# Scryer (/workspace/scryer-prolog) and Trealla agree on every line.
EXPECTED = {
    "a1": ["[x|foo]"],
    "a2": ["a-foo"],
    "a3": ["foo"],
    "a4": ["[a]"],
    "a5": ["[a,b]"],
    "a6": ["[]-[a|foo]", "[a]-foo"],
    "a7": ["foo"],
    "a8": ["yes"],
    "a9": ["[x,y,z|foo]"],
    "a10": ["[]-foo"],
    "a11": ["[x|f(1)]"],
    "a12": ["foo"],
    "a13": [],
    "a14": [],
    "a15": ["[x|1]"],
}


@pytest.fixture
def mod(native):
    return native.load("append_any_tail", SRC)


@pytest.mark.parametrize("name", sorted(EXPECTED, key=lambda n: int(n[1:])))
def test_append_takes_any_tail(mod, ans, capsys, name):
    assert ans(mod, "show", 1, name) == [()]
    assert capsys.readouterr().out.splitlines() == EXPECTED[name]
