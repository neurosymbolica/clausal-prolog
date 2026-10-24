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


def test_an_opaque_value_in_an_if_then_else_node_is_parameterised(native):
    """solve's ``_parameterize_opaque`` rebuilds an IfThenElse node whose
    arms hold an opaque value (a Decimal), keeping ``orelse=None`` for the
    no-else form; the query then runs on a ``.pl`` module.

    The fact the Decimal must match holds a Decimal itself, asserted from
    Python: since 2026-10-23 ``Decimal('2')`` and ``2`` are distinct terms
    (ISO 7.3, every numeric kind its own), so a source fact ``w(2)`` would
    no longer answer it."""
    from decimal import Decimal
    from clausal.logic.solve import _deref_walk, _parameterize_opaque, solve, call
    from clausal.logic.variables import Var
    from clausal.pythonic_ast.nodes import IfThenElse
    mod = native.load("l3_ite_opaque", ":- dynamic(w/1).\nw(2).\nok(1).\n")
    for _ in call("assertz", ("w", Decimal("2")), module=mod):
        break
    else:
        pytest.fail("assertz(w(Decimal('2'))) failed")
    y = Var()
    ite = IfThenElse(test=("w", Decimal("2")), body=("ok", y), orelse=None)
    params: list = []
    out = _parameterize_opaque(ite, params)
    assert out is not ite and type(out) is IfThenElse
    assert out.orelse is None and len(params) == 1
    assert params[0][1] == Decimal("2")
    for orelse in (False, True):
        y = Var()
        ite = IfThenElse(test=("w", Decimal("2")), body=("ok", y),
                         orelse=("ok", y) if orelse else None)
        assert [_deref_walk(y) for _ in solve(ite, mod)] == [1], orelse
    # The else arm taken, with the Decimal in it.
    ite = IfThenElse(test=("w", 99), body=("ok", 7),
                     orelse=("w", Decimal("2")))
    assert len(list(solve(ite, mod))) == 1


# ── Recursion through a condition (final review I-1) ────────────────────────
#
# A condition runs as a nested Python generator (like once/1's goal), so
# recursion THROUGH it is bounded by Python's stack: about 330-400 levels.
# Scryer answers every row below without error.

DEEP = """\
all_pos([]).
all_pos([X|Xs]) :- ( X > 0, all_pos(Xs) -> true ; fail ).
ite(N, R) :- numlist(1, N, L), ( all_pos(L) -> R = yes ; R = no ).
ite_err(N, E) :- numlist(1, N, L), catch((all_pos(L), E = none), error(E0, _), E = E0).
ite_quiet(N, R) :- numlist(1, N, L), ( catch(all_pos(L), _, fail) -> R = yes ; R = no ).
r(0) :- !.
r(N) :- N1 is N-1, catch(r(N1), _, true).
rk(0).
rk(N) :- N > 0, N1 is N-1, catch((rk(N1), !), _, true).
o(0).
o(N) :- N > 0, N1 is N-1, once(o(N1)).
o_err(N, E) :- catch((o(N), E = none), E, true).
o_after_ite(N, E) :- catch(((true -> true ; true), o(N), E = none), E, true).
o_in_then(N, E) :- catch((true -> o(N), E = none ; true), E, true).
rec(0).
rec(N) :- N > 0, N1 is N-1, catch(throw(x), x, (!, rec(N1))).
rec_err(N, E) :- catch((rec(N), E = none), E, true).
"""


def test_recursion_through_a_condition_overflows_as_an_iso_resource_error(native, ans):
    """Past the limit the RecursionError leaves the condition as
    error(resource_error(stack), _), so a catch/3 can see what happened.
    Scryer: yes / none for both depths."""
    mod = native.load("l3_ite_deep", DEEP)
    assert ans(mod, "ite", 2, 100) == ["yes"]
    assert ans(mod, "ite_err", 2, 100) == ["none"]
    assert ans(mod, "ite_err", 2, 2000) == [("resource_error", "stack")]


def test_a_catch_all_still_turns_the_overflow_into_failure(native, ans):
    """PINNED, not a target: catch(G, _, fail) catches the resource error
    like any other, so the deep row answers ``no`` where Scryer answers
    ``yes`` (todo/ite-condition-recursion-is-bounded-by-the-python-stack-2026-10-16.md)."""
    mod = native.load("l3_ite_deep_quiet", DEEP)
    assert ans(mod, "ite_quiet", 2, 2000) == ["no"]           # Scryer: [yes]


def test_cut_free_catch_and_a_catch_whose_goal_cuts_are_not_bounded(native, ans):
    """catch/3 stays in the trampoline (a cut-free Goal inline, a cutting
    Goal as a sub-generator the trampoline drives), so 2000 levels run.
    Scryer: the same."""
    mod = native.load("l3_ite_deep_catch", DEEP)
    assert ans(mod, "r", 1, 2000) == [()]
    assert ans(mod, "rk", 1, 2000) == [()]


def test_once_and_a_cutting_recovery_still_overflow_as_a_resource_error(native, ans):
    """PINNED, not a target: recursion through once/1 (pre-existing, cut or
    no cut) and through a catch/3 Recovery that cuts still overflows
    Python's stack.  Since 2026-10-24 the RecursionError reaches the
    program as the ISO ``error(resource_error(stack), _)`` (the term the
    condition's own overflow always had; ``python_error_term``), never as
    the transliterated ``'RecursionError'(Message)``.  once/1's lowering is
    shared with cut-free code, whose codegen is pinned byte-identical
    (tests/test_cut_codegen.py).  Scryer: none, none."""
    mod = native.load("l3_ite_deep_once", DEEP)
    stack = ("error", ("resource_error", "stack"))
    [e] = ans(mod, "o_err", 2, 2000)
    assert e[:2] == stack, e
    # The condition's try covers the CONDITION only: an if-then-else before
    # the recursion, or around it in Then, does not reclassify it.
    [e] = ans(mod, "o_after_ite", 2, 2000)
    assert e[:2] == stack, e
    [e] = ans(mod, "o_in_then", 2, 2000)
    assert e[:2] == stack, e
    [e] = ans(mod, "rec_err", 2, 2000)
    assert e[:2] == stack, e
