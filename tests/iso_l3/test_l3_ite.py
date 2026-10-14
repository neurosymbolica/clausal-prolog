"""Native .pl: ISO 7.8.7 if-then and 7.8.8 if-then-else.  Expected answers
are Scryer's (scratchpad/cut/sem2.pl, ite1.pl)."""
from __future__ import annotations

import pytest

SRC = """\
p(1). p(2). p(3).
a4(X) :- ( (!, fail) -> X = t ; X = e ).
a5(X) :- ( true -> ! ; true ), X = 1.
a5(2).
a6(X) :- ( fail -> true ; ! ), X = 1.
a6(2).
a7(X) :- ( p(X) -> true ; true ).
a8 :- ( fail -> true ).
a9 :- ( true -> true ).
a13(X) :- ( p(X), X > 1 -> ! ; true ).
a13(9).
a19(X) :- ( call((p(X), !)) -> true ; X = none ).
a20(X, Y) :- ( X = 1 -> Y = one ; X = 2 -> Y = two ; Y = other ).
a23(L) :- findall(X-Y, ( p(X), ( X = 2 -> Y = yes ; Y = no ) ), L).
a24(L) :- findall(X, ( p(X), ( X >= 2 -> fail ; true ) ), L).
a27(X) :- ( p(X) -> ( X > 1 -> fail ; true ) ; X = z ).
a30(X) :- ( p(X) -> true ; true ), X > 1.
a31(L) :- findall(X, ( ( p(X) ; X = 4 ) -> true ; X = 5 ), L).
side(L) :- findall(X, ( ( p(X), X > 1 -> true ; true ) ), L).
"""

ROWS = [
    ("a4", ["e"]), ("a5", [1]), ("a6", [1]), ("a7", [1]), ("a13", [2]),
    # S22: call((p(X), !)) in the condition needs call/1 to run a cut in a
    # .pl body (Task 5); today it raises existence_error(procedure, !/0).
    pytest.param("a19", [1], marks=pytest.mark.xfail(
        strict=True, reason="call/1 does not run a cut in a .pl body yet")),
    ("a23", [[("-", 1, "no"), ("-", 2, "yes"), ("-", 3, "no")]]),
    ("a24", [[1]]), ("a27", [1]), ("a30", []), ("a31", [[1]]), ("side", [[2]]),
]


@pytest.mark.parametrize("name,want", ROWS)
def test_ite_rows_match_scryer(native, ans, name, want):
    mod = native.load("l3_ite", SRC)
    assert ans(mod, name) == want


def test_no_else_and_else_chain(native, ans):
    mod = native.load("l3_ite_2", SRC)
    from clausal.logic.solve import query
    from clausal.logic.variables import Var
    assert list(query("a8", {}, mod)) == []
    assert list(query("a9", {}, mod)) == [{}]
    y = Var()
    assert [r["Y"] for r in query(("a20", 2, y), {"Y": y}, mod)] == ["two"]
    assert [r["Y"] for r in query(("a20", 3, y), {"Y": y}, mod)] == ["other"]


def test_the_condition_runs_once(native, ans):
    """The condition's side effect happens exactly once (commit, not re-run)."""
    src = SRC + """
:- dynamic(hit/0).
once_only(N) :- ( (assertz(hit), fail ; true) -> true ; true ), findall(x, hit, L), length(L, N).
"""
    mod = native.load("l3_ite_3", src)
    assert ans(mod, "once_only") == [1]


@pytest.mark.parametrize("body", [
    "( q -> true ; true )", "( q -> true )", "( q ; ( q -> true ; true ) )",
])
def test_a_clausal_file_keeps_the_if_then_refusal(native, body):
    """The lowering is gated on the surface: `->` in a ``.clausal`` file is
    refused with the existing ruling."""
    with pytest.raises(SyntaxError, match=r"`->` \(if-then\) is refused"):
        native.load("l3_ite_cl", f"q.\np :- {body}.\n", suffix=".clausal")


def test_soft_cut_stays_refused_in_a_pl_file(native):
    """`*->` is not ISO; only `->` is lowered."""
    with pytest.raises(SyntaxError, match=r"`\*->` \(soft-cut\) is refused"):
        native.load("l3_ite_soft", "q.\np :- '*->'(q, true).\n")


def test_a_grammar_body_if_then_else_runs(native):
    """ISO 7.14.2: ``( [a] -> [b] ; [c] )`` in a grammar body translates to
    an if-then-else over the list threading, and now runs."""
    mod = native.load("l3_ite_dcg", "s --> ( [a] -> [b] ; [c] ).\n")
    from clausal.logic.solve import query
    assert list(query(("phrase", "s", ["a", "b"]), {}, mod)) == [{}]
    assert list(query(("phrase", "s", ["c"]), {}, mod)) == [{}]
    assert list(query(("phrase", "s", ["a", "c"]), {}, mod)) == []
