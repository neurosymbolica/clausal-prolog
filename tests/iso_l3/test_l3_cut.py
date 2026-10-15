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


# S33: a cut in the Then of `->` inside a `;` cuts the clause (7.8.6/7.8.8).
NEST_SRC = SRC + """\
nest(X) :- ( ( X = 1 ; X = 2 ), ( X = 2 -> ! ; true ) ; X = 3 ).
nest(4).
"""


def test_cut_in_a_then_inside_a_disjunction_cuts_the_clause(native, ans):
    mod = native.load("l3_cut_nest", NEST_SRC)
    assert ans(mod, "nest") == [1, 2]


# S20: an exception thrown after a cut in catch/3's Goal (7.8.9).
CATCH_SRC = SRC + """\
a17(R) :- catch((p(X), !, throw(got(X))), got(Y), R = Y).
"""


def test_exception_after_a_cut_in_a_catch_goal(native, ans):
    mod = native.load("l3_cut_catch", CATCH_SRC)
    assert ans(mod, "a17") == [1]


# S11 and its neighbours: catch/3 calls its Goal "as call/1" (ISO 7.8.9), so a
# cut in the Goal is local to it.  The brief recorded Scryer's c3 as
# [1,2,3,9], a deviation from its own call/1 ([1,2,9]); the Scryer at
# /workspace/scryer-prolog (2026-10-14, scratchpad/cut/t4_s.pl) answers
# [1,2,9] for both, which is also ISO (7.8.8: a cut in Then is transparent
# to the catch Goal).  c6: the cut prunes the Goal's own `;` and nothing else.
# f: a goal woken in the cutting Goal throws inside the catch; k: a ball from
# the continuation is not the Goal's; n: nested catches, both cutting.
CATCH_GOAL_SRC = """\
p(1). p(2). p(3).
a11(X) :- catch((p(X), !), _, true).
a11(9).
c2(X) :- catch(p(X), _, true), !.
c2(9).
c3(X) :- catch(( p(X), ( X > 1 -> ! ; true ) ), _, true).
c3(9).
c4(R) :- catch(( p(X), !, X > 5 ), _, true), R = X.
c4(none).
c6(X) :- catch(( ! ; X = 2 ), _, true), X == 2.
c6(7).
f(X) :- catch((freeze(Y, throw(w)), p(X), !, Y = 1), w, X = caught).
k(X) :- catch(k0(X), out(Z), X = outer(Z)).
k0(X) :- catch((p(X), !), _, X = caught), throw(out(X)).
n(X) :- catch(catch((p(X), !, throw(i)), j, true), i, (p(X), X > 1, !)).
n(9).
"""


@pytest.mark.parametrize("name,want", [
    ("a11", [1, 9]), ("c2", [1]), ("c3", [1, 2, 9]), ("c4", ["none"]),
    ("c6", [7]), ("f", ["caught"]), ("k", [("outer", 1)]), ("n", [2, 9]),
])
def test_catch_goal_is_opaque_to_cut(native, ans, name, want):
    """catch/3's Goal is a cut barrier (ISO 7.8.9, "as call/1").  Every
    value is Scryer's and ISO's (see the comment above for c3)."""
    mod = native.load("l3_cut_catch_goal", CATCH_GOAL_SRC)
    assert ans(mod, name) == want


# catch/3's Recovery is likewise called "as call/1" (ISO 7.8.9): a cut in it
# is local to the Recovery.  All values are Scryer's (scratchpad/cut/t4_s.pl).
CATCH_RECOVERY_SRC = """\
p(1). p(2). p(3).
r1(X) :- catch(throw(e), e, (p(X), !)).
r1(9).
r2(X) :- catch(throw(e), e, (p(X), ( X > 1 -> ! ; true ))).
r2(9).
r3(X) :- catch(throw(e), e, p(X)), !.
r3(9).
r4(X-Y) :- catch((p(X), !), _, true), catch(throw(e), e, (p(Y), !)).
r4(9-9).
r5(R) :- catch(throw(e), e, (p(X), !, X > 5)), R = X.
r5(none).
r6(X) :- catch(throw(e), e, (p(X), !, throw(again(X)))).
r7(X) :- catch(r6(X), again(Y), X = c(Y)).
r9(X) :- catch(throw(e), e, ( ! ; X = 2 )), X == 2.
r9(7).
"""


@pytest.mark.parametrize("name,want", [
    ("r1", [1, 9]), ("r2", [1, 2, 9]), ("r3", [1]),
    ("r4", [("-", 1, 1), ("-", 9, 9)]), ("r5", ["none"]),
    ("r7", [("c", 1)]), ("r9", [7]),
])
def test_catch_recovery_is_opaque_to_cut(native, ans, name, want):
    mod = native.load("l3_cut_catch_rec", CATCH_RECOVERY_SRC)
    assert ans(mod, name) == want


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


# ── Task 8: the body visitors that walk Not also walk the two ISO nodes ─────

def _regex_goal(text):
    from clausal.pythonic_ast.nodes import Call, LoadName
    return Call(func=LoadName(name="match"),
                args=[text, LoadName(name="S"), LoadName(name="G")], kwargs=[])


def test_goal_expansion_descends_into_ite_and_leaves_cut_alone():
    from clausal.logic.goal_expansion import _ExpansionContext, _expand_goal
    from clausal.modules.py import re as regex_mod
    from clausal.pythonic_ast.nodes import And, Cut, IfThenElse, LoadName
    ctx = _ExpansionContext({"match": regex_mod.match})
    cut = Cut()
    assert _expand_goal(cut, ctx) is cut
    ite = IfThenElse(test=_regex_goal(r"\d+"), body=And(left=cut, right=_regex_goal(r"a+")),
                     orelse=_regex_goal(r"b+"))
    out = _expand_goal(ite, ctx)
    assert type(out) is IfThenElse and out is not ite
    for g in (out.test, out.body.right, out.orelse):
        assert g.args[0].name.startswith("_re_")      # pattern pre-compiled
    assert out.body.left is cut
    no_else = IfThenElse(test=_regex_goal(r"\d+"), body=cut, orelse=None)
    out = _expand_goal(no_else, ctx)
    assert out.orelse is None and out.test.args[0].name.startswith("_re_")
    untouched = IfThenElse(test=cut, body=cut, orelse=cut)
    assert _expand_goal(untouched, ctx) is untouched


def test_term_expansion_goal_names_walk_the_ite_arms():
    from clausal.logic.term_expansion import _goal_names
    from clausal.pythonic_ast.nodes import Call, Cut, IfThenElse, LoadName
    c = lambda n, *a: Call(func=LoadName(name=n), args=list(a), kwargs=[])
    out = set()
    _goal_names(IfThenElse(test=c("t"), body=Cut(), orelse=c("e")), out)
    assert out == {"t", "e"}
    out = set()
    _goal_names(IfThenElse(test=c("t"), body=c("b"), orelse=None), out)
    assert out == {"t", "b"}


def _graph(native, name, src):
    from clausal.logic.stratification import build_dependency_graph
    mod = native.load(name, src)
    from clausal.logic.predicate import namespace_db
    return build_dependency_graph(namespace_db(vars(mod)))


def test_stratification_walks_ite_arms_and_ignores_cut(native):
    g = _graph(native, "l3_cut_strat", """\
q. r. s.
a :- ( q -> r ; s ).
b :- q, !, r.
c :- ( \\+ q -> ! ; r ).
""")
    assert sorted(g[("a", 0)]) == [(("q", 0), False), (("r", 0), False), (("s", 0), False)]
    assert sorted(g[("b", 0)]) == [(("q", 0), False), (("r", 0), False)]
    # a Not above the ITE is sticky; the test itself is not a negation
    assert (("q", 0), True) in g[("c", 0)] and (("r", 0), False) in g[("c", 0)]


def test_a_negation_cycle_through_an_ite_arm_warns(native):
    import warnings
    from clausal.logic.stratification import ClausalStratificationWarning
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        native.load("l3_cut_strat_cyc", "p :- ( true -> \\+ q ; true ).\nq :- ( p -> true ; fail ).\n")
    assert any(issubclass(w.category, ClausalStratificationWarning) for w in caught)


def test_solve_runs_an_ite_node_query_with_cell_goals(native):
    from clausal.logic.solve import _deref_walk, solve
    from clausal.logic.variables import Var
    from clausal.pythonic_ast.nodes import IfThenElse
    mod = native.load("l3_cut_solve", "p(1). p(2). q(2).\n")
    x = Var()
    ite = IfThenElse(test=("p", x), body=("q", x), orelse=("q", 2))
    assert [_deref_walk(x) for _ in solve(ite, mod)] == []       # commits to p(1); q(1) fails
    y = Var()
    ite = IfThenElse(test=("q", 7), body=("p", y), orelse=("p", y))
    assert [_deref_walk(y) for _ in solve(ite, mod)] == [1, 2]


# ── catch/3 around and inside the cut constructs ────────────────────────────
# i*: a catch in an if-then-else condition (the catch Goal is a barrier
# inside the condition's own barrier); b*: an exception thrown after
# backtracking INTO the catch Goal, with and without a cut first; n*: a
# cutting catch nested in findall, \+, \+ \+ and once; t*: the trail is
# balanced when the clause fails into the next one.  Every value is
# Scryer's (2026-10-15).
CATCH_MORE_SRC = """\
p(1). p(2). p(3).
i1(X) :- ( catch((p(X), !), _, true) -> true ; X = 9 ).
i1(8).
i2(X) :- ( catch(p(X), _, true), X > 1 -> true ; X = 9 ).
i3(X) :- ( catch((p(X), X > 5), _, true) -> true ; X = 9 ).
i4(X) :- ( catch(throw(e), e, (p(X), !)) -> ! ; true ).
i4(7).
b1(X) :- catch(( ( X = 1 ; X = 2 ), ( X == 2 -> throw(c) ; true ) ), c, X = c).
b2(X) :- catch(( ( X = 1 ; X = 2 ), ( X == 1 -> true ; !, throw(c) ) ), c,
               X = c).
b3(X) :- catch(( p(X), X >= 2, throw(c(X)) ), c(Y), X = got(Y)).
n1(L) :- findall(X, catch((p(X), !), _, true), L).
n2(R) :- ( \\+ catch((p(X), !, X > 1), _, true) -> R = yes ; R = no ).
n3(X) :- once(catch((p(X), X > 1, !), _, true)).
n3(9).
n4(L) :- findall(X, ( p(X), catch(( X > 1, ! ), _, true) ), L).
n5(R) :- ( \\+ \\+ catch((p(X), !, X =:= 1), _, true) -> R = yes ; R = no ).
t1(X) :- catch((X = 1, !, fail), _, true).
t1(X) :- var(X), X = 2.
t2(Y) :- Y = a, catch((p(_), !), _, true), fail.
t2(Y) :- var(Y), Y = b.
t3(X) :- ( catch((X = 1, !), _, true), fail -> true ; var(X), X = 3 ).
t4(X) :- catch((X = 1, throw(e)), e, true), var(X), !, X = 4.
t4(5).
"""


@pytest.mark.parametrize("name,want", [
    ("i1", [1, 8]), ("i2", [2]), ("i3", [9]), ("i4", [1]),
    ("b1", [1, "c"]), ("b2", [1, "c"]), ("b3", [("got", 2)]),
    ("n1", [[1]]), ("n2", ["yes"]), ("n3", [2, 9]), ("n4", [[2, 3]]),
    ("n5", ["yes"]),
    ("t1", [2]), ("t2", ["b"]), ("t3", [3]), ("t4", [4]),
])
def test_catch_composes_with_cut_and_if_then_else(native, ans, name, want):
    mod = native.load("l3_cut_catch_more", CATCH_MORE_SRC)
    assert ans(mod, name) == want


def test_cut_scope_treats_a_branch_test_as_part_of_the_scope():
    """The seam's ``if_/3`` (``Branch``) lowers its test, then and else in
    the enclosing scope -- no barrier -- so a cut in its then/else cuts over
    a tabled call in its test, and ``cut_reaches_scope`` sees through it."""
    from clausal.logic.compiler.cut_scope import (
        cut_reaches_scope, tabled_calls_in_cut_scope)
    from clausal.logic.compiler.ir import Branch, Cut, Sequence, SubCall

    class _DB:
        module_dict: dict = {}

        def is_tabled(self, f, n):
            return f == "tf"

    def call(f):
        return SubCall(fname=f, arity=1, args=[1])

    def br(test, then, else_):
        return Branch(test=test, then=then, else_=else_,
                      reified_test="unify")

    db = _DB()
    assert tabled_calls_in_cut_scope(
        br(call("tf"), Cut(), Sequence(ops=[])), db) == [("tf", 1)]
    assert tabled_calls_in_cut_scope(
        br(call("tf"), Sequence(ops=[]), Cut()), db) == [("tf", 1)]
    # A tabled call in then is not before a cut in else.
    assert tabled_calls_in_cut_scope(
        br(call("q"), call("tf"), Cut()), db) == []
    # ... but is before a cut that follows the Branch.
    assert tabled_calls_in_cut_scope(Sequence(ops=[
        br(call("q"), call("tf"), Sequence(ops=[])), Cut()]), db) == [
        ("tf", 1)]
    assert cut_reaches_scope(br(call("q"), Cut(), Sequence(ops=[])))
    assert cut_reaches_scope(br(call("q"), Sequence(ops=[]), Cut()))
    assert not cut_reaches_scope(br(call("q"), call("r"), Sequence(ops=[])))


def test_goal_expansion_collects_vars_from_all_three_ite_arms(monkeypatch):
    """``_collect_vars_from_term`` walks an ISO IfThenElse's test, then and
    else (and skips a missing else), as it walks And/Or/Not."""
    from clausal.logic import goal_expansion as ge
    from clausal.logic.variables import Var
    from clausal.pythonic_ast.nodes import Cut, IfThenElse
    monkeypatch.setattr(ge, "_cell_slot_names",
                        lambda f, n, md: tuple(f"{f}{i}" for i in range(n)))
    x, y, z = Var(), Var(), Var()
    out: dict = {}
    ge._collect_vars_from_term(
        IfThenElse(test=("t", x), body=("b", y), orelse=("e", z)), out)
    assert out == {"t0": x, "b0": y, "e0": z}
    out = {}
    ge._collect_vars_from_term(
        IfThenElse(test=("t", x), body=Cut(), orelse=None), out)
    assert out == {"t0": x}
    # The ITE's own fields are goal positions, not named slots: a bare
    # variable goal names nothing (the generic term walk would record it
    # under "test").
    out = {}
    ge._collect_vars_from_term(
        IfThenElse(test=x, body=("b", y), orelse=z), out)
    assert out == {"b0": y}


# ── Cleanup of a pruned setup_call_cleanup (final review I-2) ───────────────
#
# A cut is compiled as "run the rest of the clause and the caller's
# continuation, then leave", so the choice points it prunes -- and the
# generator holding a setup_call_cleanup's Goal -- stay alive until that
# continuation has finished.  Cleanup therefore runs AFTER the caller's
# continuation, not at the cut.  Scryer (and Ulrich Neumerkel's
# setup_call_cleanup draft) run Cleanup when the Goal's choice points are
# cut, or as soon as it exits deterministically.  Documented in
# docs/importing_prolog.md; not fixed in this series
# (todo/setup-call-cleanup-cleanup-runs-after-the-continuation-2026-10-16.md).

SCC_PRUNED = """\
:- use_module(library(lists)).
:- dynamic(cl/0).
chk(R) :- cl, R = early.
chk(R) :- \\+ cl, R = late.
u :- setup_call_cleanup(true, member(_, [1,2]), assertz(cl)), !.
t21(R) :- retractall(cl), u, chk(R).
v :- ( setup_call_cleanup(true, member(_, [1,2]), assertz(cl)) -> true ; true ).
t22(R) :- retractall(cl), v, chk(R).
t24(R) :- retractall(cl), \\+ \\+ u, chk(R).
t26(R) :- retractall(cl), setup_call_cleanup(true, true, assertz(cl)), chk(R).
"""


@pytest.mark.xfail(strict=True, reason="final review I-2: Cleanup of a Goal "
                   "pruned by ! or -> runs after the caller's continuation")
@pytest.mark.parametrize("name", ["t21", "t22", "t24", "t26"])
def test_a_pruned_setup_call_cleanup_runs_cleanup_at_the_cut(native, ans, name):
    """t21/t22/t24: pruned by ``!``, by ``->``, by ``!`` under ``\\+ \\+``.
    t26 is the pre-existing root: a DETERMINISTIC Goal's Cleanup also runs
    only after the continuation."""
    mod = native.load("l3_cut_scc_pruned_" + name, SCC_PRUNED)
    assert ans(mod, name) == ["early"]                        # Scryer: early
