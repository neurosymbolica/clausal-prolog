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
bv(X) :- ( Y = f(1) -> X = Y ; X = no ).
ex(R) :- catch(( ( X = 1, throw(e) ) -> true ; true ), e, true),
         ( var(X) -> R = unbound ; R = bound ).
tb(R) :- ( ( X = 1 -> fail ; true ) ; true ), ( var(X) -> R = unbound ; R = X ).
d6(R-Y) :- atom_chars(ab, L0), append(L0, [c], R), ( true -> Y = L0 ; Y = no ).
d7(R-Y) :- atom_chars(ab, L0), reverse(L0, R), ( true -> Y = L0 ; Y = no ).
q(1, a). q(2, b). q(2, c). q(3, d).
t1(X) :- ( true -> p(X) ; X = 9 ).
t2(X) :- ( fail -> X = 0 ; p(X) ).
t3(X-Y) :- ( p(Y), Y > 1 -> q(Y, X) ; X = none ).
t4(X) :- ( true -> !, p(X) ; true ).
t4(9).
t5(L) :- findall(X, t1(X), L1), findall(X, t3(X), L2), append(L1, L2, L).
d8(R-Y) :- atom_chars(ab, L0), append(L0, [c], R), ( L0 = [_, _] -> Y = yes ; Y = no ).
"""

ROWS = [
    ("a4", ["e"]), ("a5", [1]), ("a6", [1]), ("a7", [1]), ("a13", [2]),
    # S22: call((p(X), !)) in the condition -- call/1 runs a cut in a .pl
    # caller's body, local to the call (Task 5).
    ("a19", [1]),
    ("a23", [[("-", 1, "no"), ("-", 2, "yes"), ("-", 3, "no")]]),
    ("a24", [[1]]), ("a27", [1]), ("a30", []), ("a31", [[1]]), ("side", [[2]]),
    # A binding made in C is visible in T.
    ("bv", [("f", 1)]),
    # An exception out of C restores the trail: X is unbound in the handler.
    ("ex", ["unbound"]),
    # Trail balance: a failed then-branch leaves no binding for the next
    # disjunct.
    ("tb", ["unbound"]),
    # Destructive reuse must see the variables read inside an ITE: L0 is
    # still live after append/3 / reverse/2 when T, E or C reads it.
    ("d6", [("-", ["a", "b", "c"], ["a", "b"])]),
    ("d7", [("-", ["b", "a"], ["a", "b"])]),
    ("d8", [("-", ["a", "b", "c"], "yes")]),
    # Tail calls in then/else (continuation-TCO marks them): every answer
    # of the tail call reaches the caller, and the else never runs after T.
    ("t1", [1, 2, 3]), ("t2", [1, 2, 3]),
    ("t3", [("-", "b", 2), ("-", "c", 2)]), ("t4", [1, 2, 3]),
    ("t5", [[1, 2, 3, ("-", "b", 2), ("-", "c", 2)]]),
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


def test_continuation_tco_marks_tail_calls_in_then_and_else():
    """A SubCall ending T or E is in tail position; one in C is not."""
    from clausal.logic.compiler import ir
    from clausal.logic.compiler.optimisations import continuation_tco
    c, t, e = (ir.SubCall(fname=n, arity=0, args=[]) for n in "cte")
    body = ir.Sequence(ops=[ir.IfThenElse(test=ir.Sequence(ops=[c]),
                                          then=ir.Sequence(ops=[t]),
                                          else_=ir.Sequence(ops=[e]))])
    plan = continuation_tco.analyse(body)
    assert plan.marks == frozenset({id(t), id(e)})
    out = continuation_tco.apply(body, plan)
    ite = out.ops[0]
    assert ite.then.ops[0].tail_position and ite.else_.ops[0].tail_position
    assert not ite.test.ops[0].tail_position
