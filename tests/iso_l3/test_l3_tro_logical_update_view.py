"""Tail-recursion optimisation keeps the logical update view (ISO 7.5.4).

A tail call of a dynamic predicate is a new call, so it sees every clause
asserted or retracted before it -- including by the clause's own prefix.  The
in-place restart TRO compiles a tail call into re-enters the clause set the
activation was compiled with, so it used to miss those clauses: a prefix of
``\\+ \\+ assertz(...)``, ``once(assertz(...))`` or ``findall(_, assertz(...),
_)`` (each counts as deterministic, so the clause is TRO-eligible) lost every
answer of the asserted clauses.  The restart is now taken only when the
predicate's clause set is unchanged since the activation began; otherwise the
tail is an ordinary call.

Every expected answer is Scryer's for the same program (2026-11-04).
"""
from __future__ import annotations

PREFIX_SRC = """\
:- module(NAME, [t/1, touch/0]).
:- dynamic(q1/1).
:- dynamic(q2/1).
:- dynamic(q3/1).
:- dynamic(q4/1).
:- dynamic(q5/1).
q1(N) :- N > 0, N1 is N - 1, \\+ \\+ assertz(q1(N1)), q1(N1).
q2(N) :- N > 0, N1 is N - 1, once(assertz(q2(N1))), q2(N1).
q3(N) :- N > 0, N1 is N - 1, findall(x, assertz(q3(N1)), _), q3(N1).
q4(N) :- N > 0, N1 is N - 1, ( assertz(q4(N1)) -> true ; true ), q4(N1).
q5(N) :- N > 0, N1 is N - 1, catch(assertz(q5(N1)), _, true), q5(N1).
t([A, B, C, D, E]) :-
    findall(x, q1(2), A), findall(x, q2(2), B), findall(x, q3(2), C),
    findall(x, q4(2), D), findall(x, q5(2), E).
touch :-
    assertz(q1(-5)), retract(q1(-5)), assertz(q2(-5)), retract(q2(-5)),
    assertz(q3(-5)), retract(q3(-5)), assertz(q4(-5)), retract(q4(-5)),
    assertz(q5(-5)), retract(q5(-5)).
"""

_TWO_EACH = [["x", "x"]] * 5


def test_a_tail_call_sees_the_clause_its_prefix_asserted(native, ans):
    mod = native.load("tluv_fresh", PREFIX_SRC.replace("NAME", "tluv_fresh"))
    assert ans(mod, "t") == [_TWO_EACH]


def test_the_same_after_the_predicates_were_recompiled(native, ans):
    """``touch`` asserts and retracts a clause of each, so ``t`` runs the
    predicates' second compile."""
    from clausal.logic.solve import call
    mod = native.load("tluv_recomp", PREFIX_SRC.replace("NAME", "tluv_recomp"))
    assert len(list(call("touch", module=mod))) == 1
    assert ans(mod, "t") == [_TWO_EACH]


INDEXED_SRC = """\
:- module(tluv_idx, [t/1, t2/1, t3/1]).
:- dynamic(r/2).
r(N, x) :- N > 0, N1 is N - 1, \\+ \\+ assertz(r(N1, x)), r(N1, x).
r(a, y). r(b, y). r(c, y). r(d, y). r(e, y).
t(L) :- findall(x, r(2, x), L).
:- dynamic(k/2).
k(go, N) :- N > 0, N1 is N - 1, once(assertz(k(go, N1))), k(go, N1).
k(p1, _). k(p2, _). k(p3, _). k(p4, _). k(p5, _).
t2(L) :- findall(x, k(go, 2), L).
:- dynamic(m/2).
m(_, N) :- N > 0, N1 is N - 1, once(assertz(m(go, N1))), m(_, N1).
m(p1, _). m(p2, _). m(p3, _). m(p4, _). m(p5, _).
t3(L) :- findall(x, m(_, 2), L).
"""


def test_an_indexed_predicate_restarting_through_its_dispatch_loop(native,
                                                                   ans):
    """The index buckets signal the tail to the dispatch loop instead of
    restarting in place; the same check guards them."""
    mod = native.load("tluv_idx", INDEXED_SRC)
    assert ans(mod, "t") == [["x", "x"]]
    assert ans(mod, "t2") == [["x", "x"]]
    assert ans(mod, "t3") == [["x"] * 17]


SELF_SRC = """\
:- module(tluv_self, [t/1, n/1]).
:- dynamic(s/2).
s(0, done).
s(N, R) :- N > 0, N1 is N - 1, once(assertz(s(N1, extra(N1)))), s(N1, R).
t(L) :- findall(R, s(3, R), L).
n(C) :- findall(X, clause(s(X, _), _), L), length(L, C).
"""


def test_a_clause_asserted_mid_loop_answers_at_the_next_iteration(native, ans):
    mod = native.load("tluv_self", SELF_SRC)
    assert ans(mod, "t") == [["done", ("extra", 0), ("extra", 1),
                              ("extra", 2)]]
    assert ans(mod, "n") == [5]


RETRACT_SRC = """\
:- module(tluv_ret, [t/1]).
:- dynamic(w/1).
w(N) :- N > 0, N1 is N - 1, once(retract(w(0))), w(N1).
w(0).
t(L) :- findall(x, w(2), L).
"""


def test_a_clause_retracted_by_the_prefix_is_gone_for_the_tail_call(native,
                                                                    ans):
    """The other direction: the activation's own clause set still holds
    ``w(0)``; the tail call ``w(1)`` -- and its ``w(0)`` -- must not."""
    mod = native.load("tluv_ret", RETRACT_SRC)
    assert ans(mod, "t") == [[]]


LOOP_SRC = """\
:- module(tluv_loop, [run/2]).
:- dynamic(count/1).
:- dynamic(loop/1).
count(0).
loop(0).
loop(N) :-
    N > 0, once(retract(count(C))), C1 is C + 1, once(assertz(count(C1))),
    N1 is N - 1, loop(N1).
run(N, C) :- loop(N), count(C).
"""


def test_a_dynamic_loop_that_writes_another_predicate_keeps_its_restart(
        native, ans):
    """The check is per predicate: ``loop/1`` writes ``count/1`` only, so its
    tail still restarts in place (constant space) -- and answers."""
    import ast

    from clausal.logic.compiler import predicate as cp
    mod = native.load("tluv_loop", LOOP_SRC)
    assert ans(mod, "run", 2, 3000) == [3000]
    db = vars(mod)["$module"].db
    db.row("loop", 1).invalidate()
    seen = []
    real = cp.functiondef_to_function

    def spy(fd, globals_=None, **kw):
        seen.append(ast.unparse(fd))
        return real(fd, globals_=globals_, **kw)

    cp.functiondef_to_function = spy
    try:
        db.get_dispatch("loop", 1)
    finally:
        cp.functiondef_to_function = real
    text = "\n".join(seen)
    assert "_tro = True" in text and "commit_fresh" in text, text


def _combo_src():
    facts300 = "\n".join(f"p(k({i}))." for i in range(300))
    facts16 = "\n".join("q(_)." for _ in range(16))
    facts20f = "\n".join(f"f({i})." for i in range(100, 120))
    return f"""\
:- module(tluv_combo, [ta/1, tb/1, tc/1]).
:- dynamic(p/1).
{facts300}
p(N) :- integer(N), N > 0, N1 is N - 1, once(assertz(p(N1))), p(N1).
ta(L) :- findall(x, p(2), L).
:- dynamic(q/1).
{facts16}
tb(C0-C1) :-
    assertz(q(_)), assertz(q(_)), findall(x, q(1), L0), length(L0, C0),
    assertz((q(N) :- integer(N), N > 0, N1 is N - 1, once(assertz(q(N1))),
                     q(N1))),
    findall(x, q(2), L), length(L, C1).
:- dynamic(f/1).
:- dynamic(loop/1).
{facts20f}
loop(0).
loop(N) :- N > 0, once(assertz(f(N))), N1 is N - 1, loop(N1).
tc(C-L) :-
    loop(500), findall(X, f(X), Xs), length(Xs, C),
    findall(X, (f(X), X < 4), L).
"""


def test_tail_calls_and_fact_tables_that_grow_in_place(native, ans):
    """A fact table takes an assertz in place, installing a dispatch over the
    grown table instead of invalidating; the clause generation moves all the
    same.  ``p/1``: 300 facts and a tail-recursive rule (a clause table);
    ``q/1``: a 16-fact table that takes two facts in place, then a
    tail-recursive rule at run time (it recompiles without the table, with
    the restart; without the check it answers 54); ``loop/1``: a dynamic
    loop whose prefix appends to the fact table ``f/1`` (its own restart is
    kept).  Scryer: [x,x], 18-56, 520-[3,2,1]."""
    mod = native.load("tluv_combo", _combo_src())
    assert ans(mod, "ta") == [["x", "x"]]
    assert ans(mod, "tb") == [("-", 18, 56)]
    assert ans(mod, "tc") == [("-", 520, [3, 2, 1])]


def test_an_in_place_fact_append_moves_the_clause_generation(native, ans):
    from clausal.logic.solve import call
    src = ":- module(tluv_gen, [go/0]).\n:- dynamic(f/1).\n" + "\n".join(
        f"f({i})." for i in range(20)) + "\ngo :- assertz(f(99)).\n"
    mod = native.load("tluv_gen", src)
    db = vars(mod)["$module"].db
    assert len(ans(mod, "f")) == 20          # compiles f/1 (a fact table)
    dispatch = db.row("f", 1).dispatch_fn
    gen = db.row("f", 1).clause_generation
    assert len(list(call("go", module=mod))) == 1
    row = db.row("f", 1)
    assert row.clause_generation > gen
    assert row.dispatch_fn is not None and row.dispatch_fn is not dispatch
