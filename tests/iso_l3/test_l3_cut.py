"""Native .pl: ISO 7.8.4 cut.  Every expected answer is Scryer's
(scratchpad/cut/sem2.pl, 2026-10-14); the row ids are the plan's Spec rows."""
from __future__ import annotations

import pytest

SRC = """\
:- use_module(library(lists)).
p(1). p(2). p(3).
a1(X) :- ( X = 1 ; X = 2 ), !.
a2(X) :- ( call(!) ; X = 2 ), X == 2.
a3(X) :- ( ! ; X = 2 ), X == 2.
a10 :- \\+ (!, fail).
a12(L) :- findall(X, (p(X), !), L).
a14(X) :- ( G = !, G ; X = 2 ), X == 2.
a18(X) :- once((p(X), !, X > 0)).
a25(X) :- ( p(X), ! ; X = 9 ).
a26(X) :- \\+ \\+ ( p(X), ! ), X = ok.
max(X, Y, X) :- X >= Y, !.
max(_, Y, Y).
cnt(N, N) :- !.
cnt(I, N) :- I1 is I + 1, cnt(I1, N).
deep :- cnt(0, 100000).
g --> [x], !, h.
g --> [y].
h --> [z].
q(X) :- p(X), !, X > 0.
q(9).
t(X) :- p(X), X > 1, !.
t(9).
u(X) :- q(X).
u(7).
w(X, Y) :- p(X), !, p(Y).
w(0, 0).
one(a, 1) :- !.
one(b, 2).
one(b, 3).
two(X) :- one(X, _), !, fail.
two(z).
sc(X) :- setup_call_cleanup(true, (member(X, [1,2,3]), !), true).
r_freeze(L) :- findall(X-Y, ( freeze(X, Y = woke(X)), ( X = 1 ; X = 2 ), ! ), L).
"""

ROWS = [
    ("a1", [1]), ("a2", [2]), ("a3", []), ("a12", [[1]]), ("a14", [2]),
    ("a18", [1]), ("a25", [1]), ("a26", ["ok"]), ("q", [1]), ("t", [2]),
    ("u", [1, 7]), ("two", []), ("sc", [1]),
    ("r_freeze", [[("-", 1, ("woke", 1))]]),
]


@pytest.mark.parametrize("name,want", ROWS)
def test_cut_rows_match_scryer(native, ans, name, want):
    mod = native.load("l3_cut", SRC)
    assert ans(mod, name) == want


# S33 needs `->`, which the .pl lowering still refuses until if-then-else
# lands; strict, so the row flips to a failure the day it starts passing.
NEST_SRC = SRC + """\
nest(X) :- ( ( X = 1 ; X = 2 ), ( X = 2 -> ! ; true ) ; X = 3 ).
nest(4).
"""


@pytest.mark.xfail(strict=True, reason="`->` is not lowered for .pl yet")
def test_cut_in_a_then_inside_a_disjunction_cuts_the_clause(native, ans):
    mod = native.load("l3_cut_nest", NEST_SRC)
    assert ans(mod, "nest") == [1, 2]


# S20: catch/3's trampoline-inline form has no cut exit yet (the compiler
# raises CompilerError); strict, as above.
CATCH_SRC = SRC + """\
a17(R) :- catch((p(X), !, throw(got(X))), got(Y), R = Y).
"""


@pytest.mark.xfail(strict=True, reason="catch/3's inline form is not a cut scope yet")
def test_exception_after_a_cut_in_a_catch_goal(native, ans):
    mod = native.load("l3_cut_catch", CATCH_SRC)
    assert ans(mod, "a17") == [1]


def test_zero_arity_and_multi_arity_rows(native, ans):
    mod = native.load("l3_cut_0", SRC)
    assert ans(mod, "a10", 0) == [()]
    assert ans(mod, "deep", 0) == [()]
    from clausal.logic.solve import query
    from clausal.logic.variables import Var
    m, x, y = Var(), Var(), Var()
    assert [r["M"] for r in query(("max", 3, 2, m), {"M": m}, mod)] == [3]
    assert list(query(("max", 3, 2, 2), {}, mod)) == [{}]
    assert [r["N"] for r in query(("cnt", 5, x), {"N": x}, mod)] == [5]
    assert list(query(("cnt", 0, 3), {}, mod)) == [{}]
    assert [(r["X"], r["Y"]) for r in query(("w", x, y), {"X": x, "Y": y}, mod)] == [(1, 1), (1, 2), (1, 3)]
    assert [r["X"] for r in query(("one", "a", x), {"X": x}, mod)] == [1]
    assert [r["X"] for r in query(("one", "b", x), {"X": x}, mod)] == [2, 3]
    assert [(r["X"], r["Y"]) for r in query(("one", x, y), {"X": x, "Y": y}, mod)] == [("a", 1)]
    assert list(query(("phrase", "g", ["x", "z"]), {}, mod)) == [{}]
    assert list(query(("phrase", "g", ["x", "y"]), {}, mod)) == []
    assert list(query(("phrase", "g", ["y"]), {}, mod)) == [{}]


@pytest.mark.parametrize("body", ["!", "q, !", "call(!)", "( q ; ! )"])
def test_a_clausal_file_keeps_the_cut_free_refusal(native, body):
    """The lowering is gated on the surface: the same clause in a
    ``.clausal`` file is refused with the existing ruling."""
    with pytest.raises(SyntaxError, match=r"`!` \(cut\) is refused: "
                       r"Clausal is cut-free"):
        native.load("l3_cut_cl", f"q.\np :- {body}.\n", suffix=".clausal")


def test_the_loader_counts_no_refusal(native):
    mod = native.load("l3_cut_stats", SRC)
    assert mod.__loader__.l3_stats["refused"] == 0
