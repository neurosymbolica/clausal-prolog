"""Cut and tabling: XSB's rule -- "cuts are allowed within tabled predicates
subject to the restriction that the scope of a cut cannot include a call to
a tabled predicate" (XSB manual, tabling chapter; checked at compile time,
compilation aborted).  ISO is silent; Scryer runs such a cut and gives it no
effect (tg/1 below answers [0,1,2] there), which is not a semantics our
re-lead fixpoint can promise, so the static refusal is ruled."""
from __future__ import annotations

import pytest

OK = """\
p(1). p(2). p(3).
:- table(tf/1).
tf(X) :- p(X), !.
:- table(th/1).
th(X) :- ( p(X), X > 1 -> true ; X = 0 ).
"""

BAD_CUT = """\
:- table(tg/1).
tg(X) :- tg(Y), !, X is Y + 1, X < 3.
tg(0).
"""

BAD_ITE = """\
p(1). p(2).
:- table(tp/1).
tp(X) :- p(X).
u(X) :- ( tp(X) -> true ; X = none ).
"""

BAD_UNTABLED_CALLER = """\
p(1). p(2).
:- table(tf/1).
tf(X) :- p(X).
tc(X) :- tf(X), !.
"""

BAD_IMPORTED = """\
:- use_module(tabled_lib).
v(X) :- lib_t(X), !.
"""


def test_cut_with_no_tabled_call_in_scope_is_allowed(native, ans):
    """Scryer: tf → [1], th → [2] (scratchpad/cut/sem2.pl, catch_s.pl)."""
    mod = native.load("l3_tab_ok", OK)
    assert ans(mod, "tf") == [1]
    assert ans(mod, "th") == [2]


@pytest.mark.parametrize("src,who", [(BAD_CUT, "tg/1"), (BAD_ITE, "tp/1"), (BAD_UNTABLED_CALLER, "tf/1")])
def test_cut_over_a_tabled_call_is_refused_at_load(native, src, who):
    """"The scope of a cut" is every call executed before it in the same
    barrier scope.  Refusing it whether or not the CALLER is tabled -- tc/1
    cuts over a table that is already COMPLETE -- is our ruling's choice, not
    XSB's: XSB's static rule is worded for tabled predicates and its run-time
    check errors only over an INCOMPLETE table.  Scryer runs tc/1 (answers
    [1]).  Spec S37, ruling Q1."""
    with pytest.raises(SyntaxError) as e:
        native.load("l3_tab_bad", src)
    assert "tabled" in str(e.value) and who in str(e.value)


def test_cut_over_an_imported_tabled_call_is_refused(native, tmp_path):
    (tmp_path / "tabled_lib.pl").write_text(":- module(tabled_lib, [lib_t/1]).\n:- table(lib_t/1).\nlib_t(1). lib_t(2).\n")
    with pytest.raises(SyntaxError, match="lib_t/1"):
        native.load("l3_tab_bad_imp", BAD_IMPORTED)


# -- Beyond the brief: where the scope ends ---------------------------------

SCOPE_OK = """\
p(1). p(2). p(3).
:- table(tf/1).
tf(X) :- p(X).
after(X) :- p(X), !, tf(X).
then(X) :- ( p(X) -> tf(X) ; true ).
other(X) :- ( tf(X) ; p(X), ! ).
local(X) :- \\+ \\+ tf(X), findall(Y, (tf(Y), Y > 1), _), p(X), !.
plain(X) :- call(p(X)), !.
"""


def test_a_tabled_call_outside_the_cuts_scope_is_allowed(native, ans):
    """A tabled call AFTER the cut, in the Then branch, in an EARLIER
    disjunct, or inside a barrier that leaves no choice point behind (\\+,
    findall) is not in the cut's scope; nor is a call/1 of an untabled goal.
    Scryer gives the same answers."""
    mod = native.load("l3_tab_scope_ok", SCOPE_OK)
    assert ans(mod, "after") == [1]
    assert ans(mod, "then") == [1]
    assert sorted(ans(mod, "other")) == [1, 1, 2, 3]
    assert ans(mod, "local") == [1]
    assert ans(mod, "plain") == [1]


BAD_IN_FINDALL = """\
:- table(tf/1).
tf(1). tf(2).
w(L) :- findall(X, (tf(X), !), L).
"""

BAD_IN_NAF = """\
:- table(tf/1).
tf(1). tf(2).
n :- \\+ (tf(X), !, X > 5).
"""

BAD_IN_COND_CUT = """\
:- table(tf/1).
tf(1). tf(2).
c(X) :- ( (tf(X), !) -> true ; X = 0 ).
"""

BAD_AFTER_DISJ = """\
p(1).
:- table(tf/1).
tf(1). tf(2).
d(X) :- ( tf(X) ; p(X) ), !.
"""


BAD_AFTER_CATCH = """\
:- table(tf/1).
tf(1). tf(2).
k(X) :- catch(tf(X), _, true), !.
"""


@pytest.mark.parametrize("src", [BAD_IN_FINDALL, BAD_IN_NAF, BAD_IN_COND_CUT, BAD_AFTER_DISJ,
                                 BAD_AFTER_CATCH],
                         ids=["findall", "naf", "cond_cut", "after_disj", "after_catch"])
def test_a_cut_inside_a_barrier_over_a_tabled_call_is_refused(native, src):
    """A barrier (findall's goal, \\+, an ITE condition) is a scope of its
    own; a cut in it over a tabled call in that same scope breaks the rule
    just as a clause-level cut does.  A disjunction before the cut puts its
    tabled calls in the cut's scope, and so does catch/3 (ISO 7.8.9: its
    Goal is call/1's, whose choice points survive it)."""
    with pytest.raises(SyntaxError, match=r"tabled.*tf/1"):
        native.load("l3_tab_bad_barrier", src)


def test_the_refusal_names_the_predicate_and_the_line(native):
    with pytest.raises(SyntaxError, match=r"in predicate tc/1 \(line 4\).*tf/1"):
        native.load("l3_tab_where", BAD_UNTABLED_CALLER)


RECURSIVE_ITE = """\
:- table(r/1).
r(X) :- ( r(Y) -> X is Y + 1, X < 4 ; X = 0 ).
r(0).
"""


def test_the_switch_skips_the_refusal_and_does_not_give_scryers_answers(native, ans, monkeypatch):
    """Ruling Q1 is provisional: ``cut_scope.CUT_OVER_TABLED_CALL = "run"``
    only skips the refusal and compiles the cut as written.  Over a COMPLETE
    table that agrees with Scryer (tc/1: [1]).  Over an INCOMPLETE, recursive
    table it does NOT: the committed answer depends on the re-lead fixpoint's
    pass order.  The two rows below are pinned KNOWN DIFFERENCES, not
    targets -- reproducing Scryer's cut over an incomplete table is engine
    semantics, out of scope."""
    from clausal.logic.compiler import cut_scope
    monkeypatch.setattr(cut_scope, "CUT_OVER_TABLED_CALL", "run")
    mod = native.load("l3_tab_run", BAD_UNTABLED_CALLER)
    assert ans(mod, "tc") == [1]                              # Scryer: [1]
    mod = native.load("l3_tab_run_tg", BAD_CUT)
    assert sorted(ans(mod, "tg")) == [0, 1]                   # Scryer: [0,1,2]
    mod = native.load("l3_tab_run_r", RECURSIVE_ITE)
    assert sorted(ans(mod, "r")) == [0, 1]                    # Scryer: [0,1,2,3]


# -- Fix round 1 -------------------------------------------------------------

LITERAL_CALLS = {
    "call1_body": "c(X) :- call((tf(X), !)).",
    "call1_then_cut": "c(X) :- call(tf(X)), !.",
    "calln_atom_closure": "c(X) :- call(tf, X), !.",
    "calln_compound_closure": "c(X) :- call(tf2(1), X), !.",
    "call1_in_cond": "c(X) :- ( call((tf(X), !)) -> true ; true ).",
    "call1_in_findall": "c(L) :- findall(X, call((tf(X), !)), L).",
}


@pytest.mark.parametrize("clause", list(LITERAL_CALLS.values()), ids=list(LITERAL_CALLS))
def test_a_literal_call_goal_is_scanned_like_the_body(native, clause):
    """call/N with a LITERAL goal (or an atom/compound closure: call(tf, X)
    calls tf/1) is visible statically, so it is checked like the static
    body: call/1 is a cut barrier, but its choice points survive it.  A goal
    built at run time (``G = (tf(X), !), call(G)``) stays out of reach of a
    static rule, as in XSB (whose run-time check covers it)."""
    src = (":- table(tf/1).\ntf(1). tf(2).\n:- table(tf2/2).\ntf2(1, 1). tf2(1, 2).\n"
           + clause + "\n")
    with pytest.raises(SyntaxError, match=r"tabled.*tf2?/[12]"):
        native.load("l3_tab_call", src)


def test_a_run_time_goal_loads_and_cuts_a_complete_table(native, ans):
    """Out of reach of the static rule, so the file loads.  tf/1 is called
    outside any table's evaluation, so it completes its table before its
    first answer (D68) and the cut prunes a COMPLETE table: no error.  It
    raised permission_error(cut, incomplete_table, tf/1) before D68.
    Scryer: [[1]]."""
    src = (":- table(tf/1).\ntf(1). tf(2).\n"
           "c(L) :- G = (tf(X), !), findall(X, call(G), L).\n")
    mod = native.load("l3_tab_rt", src)
    assert ans(mod, "c") == [[1]]


def test_once_over_a_tabled_call_is_refused(native):
    """ISO 8.15.2: once(G) is call((G, !)) -- the same commit as
    ( G -> true ), so it is refused like it (coordinator ruling, part of
    Mike's Q1).  \\+ and findall are not defined through cut and stay
    allowed (test_a_tabled_call_outside_the_cuts_scope_is_allowed)."""
    src = ":- table(tf/1).\ntf(1). tf(2).\nc(X) :- once(tf(X)).\n"
    with pytest.raises(SyntaxError, match=r"once/1.*tf/1"):
        native.load("l3_tab_once", src)


def test_the_refusal_uses_the_loaders_framing(native, tmp_path):
    with pytest.raises(SyntaxError) as e:
        native.load("l3_tab_frame", BAD_UNTABLED_CALLER)
    path = str(tmp_path / "l3_tab_frame.pl")
    assert str(e.value.msg).startswith(f"Cannot import {path}: l3_tab_frame.pl:4: ")
    assert e.value.filename == path
    assert e.value.lineno == 4
    assert e.value.text == "tc(X) :- tf(X), !."


def test_a_qualified_imported_callee_is_named_in_iso_spelling(native, tmp_path):
    (tmp_path / "tabled_lib.pl").write_text(":- module(tabled_lib, [lib_t/1]).\n:- table(lib_t/1).\nlib_t(1). lib_t(2).\n")
    src = ":- use_module(tabled_lib).\nv(X) :- tabled_lib:lib_t(X), !.\n"
    with pytest.raises(SyntaxError, match=r"tabled call\(s\) tabled_lib:lib_t/1"):
        native.load("l3_tab_qual", src)


def test_setup_call_cleanups_setup_commits_like_once(native, ans):
    """setup_call_cleanup/3 runs Setup as once/1 (Scryer), so a tabled call
    in Setup is refused like once(tf(X)) (coordinator ruling).  Its Goal
    keeps its choice points: a tabled call there is allowed (no cut)."""
    bad = ":- table(tf/1).\ntf(1). tf(2).\nc(X) :- setup_call_cleanup(tf(X), true, true).\n"
    with pytest.raises(SyntaxError, match=r"once/1.*tf/1"):
        native.load("l3_tab_scc_bad", bad)
    bad_lit = ":- table(tf/1).\ntf(1). tf(2).\nc(X) :- call(setup_call_cleanup(tf(X), true, true)).\n"
    with pytest.raises(SyntaxError, match=r"tf/1"):
        native.load("l3_tab_scc_bad_lit", bad_lit)
    ok = ":- table(tf/1).\ntf(1). tf(2).\nc(X) :- setup_call_cleanup(true, tf(X), true).\n"
    mod = native.load("l3_tab_scc_ok", ok)
    assert sorted(ans(mod, "c")) == [1, 2]                    # Scryer: [1,2]


SELF_QUALIFIED = {
    "user_direct": "t(X) :- user:tf(X), !.",
    "self_direct": "t(X) :- {mod}:tf(X), !.",
    "self_closure": "t(X) :- call({mod}:tf, X), !.",
    "self_call1": "t(X) :- call({mod}:tf(X)), !.",
}


@pytest.mark.parametrize("key", list(SELF_QUALIFIED))
def test_a_call_qualified_with_its_own_module_or_user_is_seen(native, key):
    """``user:tf(X)`` and ``<this module>:tf(X)`` name the local table, so
    the qualifier is stripped before the tabled lookup (Scryer commits
    ``user:tf(X), !`` to [1]: a real cut over a table)."""
    mod = f"l3_tab_selfq_{key}"
    src = (":- table(tf/1).\ntf(1). tf(2).\n"
           + SELF_QUALIFIED[key].format(mod=mod) + "\n")
    with pytest.raises(SyntaxError, match=r"tabled call\(s\) \w+:tf/1"):
        native.load(mod, src)


# ── the pre-check: a body that cannot commit skips the scan ─────────────────

NO_COMMIT = """\
p(1). p(2).
:- table(tf/1).
tf(X) :- p(X).
w(L) :- findall(X, (tf(X), p(X)), L).
w2(X) :- ( tf(X) ; p(X) ), \\+ tf(9), call(tf, X).
"""


def test_a_body_that_cannot_commit_skips_the_scan(native, ans, monkeypatch):
    """The scan runs only for a body that holds a commit (``!``, ``->``,
    once/1, setup_call_cleanup/3, in any spelling); the refusal itself is
    unchanged (the rows above, and the cutting twin here)."""
    from clausal.logic.compiler import cut_scope
    scanned = []
    real = cut_scope.tabled_calls_in_cut_scope

    def spy(ir, db):
        scanned.append(ir)
        return real(ir, db)
    monkeypatch.setattr(cut_scope, "tabled_calls_in_cut_scope", spy)
    mod = native.load("l3_tab_nocommit", NO_COMMIT)
    assert scanned == []
    assert ans(mod, "w") == [[1, 2]]
    assert ans(mod, "w2") == [1, 2, 1, 2]
    with pytest.raises(SyntaxError, match="tf/1"):
        native.load("l3_tab_nocommit_cut",
                    NO_COMMIT + "c(L) :- findall(X, (tf(X), !), L).\n")
    assert scanned


def test_the_pre_check_sees_every_commit_spelling():
    from clausal.logic.compiler.cut_scope import _may_commit
    from clausal.logic.compiler.ir import (
        Cut, IfThenElse, MetaCall, Sequence, SubCall)
    from clausal.pythonic_ast import nodes

    def call(f, *a):
        return SubCall(fname=f, arity=len(a), args=list(a))
    assert not _may_commit(Sequence(ops=[call("tf", 1), call("p", 2)]))
    assert not _may_commit(Sequence(ops=[MetaCall(
        kind="findall", args={"inner": ("tf", 1), "template": 1})]))
    for commit in (
            Cut(),
            IfThenElse(test=call("tf", 1), then=Sequence(ops=[]),
                       else_=Sequence(ops=[])),
            MetaCall(kind="once", args={"inner": ("tf", 1)}),
            MetaCall(kind="setup_call_cleanup",
                     args={"setup": ("tf", 1), "call": True,
                           "cleanup": True}),
            call("call", "once", ("tf", 1)),          # call/N closure atom
            call("call", (",", ("tf", 1), "!")),      # a cell cut
            call("call", ("->", ("tf", 1), True)),    # a cell if-then
            MetaCall(kind="findall", args={           # a node in a raw goal
                "inner": nodes.And(left=("tf", 1), right=nodes.Cut())}),
    ):
        assert _may_commit(Sequence(ops=[commit])), commit


# ── XSB's run-time half (D61 Q1, final review C-1) ───────────────────────────
#
# What the static rule cannot see -- a tabled predicate reached through an
# untabled one, or a goal built at run time -- is checked when the cut runs:
# a cut (an if-then-else commit, once/1, setup_call_cleanup's Setup) that
# would prune a tabled call over a table that is still INCOMPLETE raises
# permission_error(cut, incomplete_table, F/N).  XSB raises at run time on
# the same programs; Scryer runs them (answers in the comments).


def _INCOMPLETE(f, n):
    return ("permission_error", "cut", "incomplete_table", ("/", f, n))


THROUGH_UNTABLED = """\
:- table(a/1).
a(X) :- b(X), !.
b(X) :- a(Y), X is Y+1, X < 3.
b(0).
r(E) :- catch((findall(X, a(X), _), E = none), error(E0, _), E = E0).
"""


def test_a_cut_over_an_incomplete_table_through_an_untabled_predicate_raises(native, ans):
    """The final review's repro: a/1's cut prunes b/1's consumer call of
    a/1 while a/1's table is incomplete.  It used to answer [0,1] silently
    (Scryer: [0,1,2]; XSB: the run-time error)."""
    mod = native.load("l3_tab_rt_untabled", THROUGH_UNTABLED)
    assert ans(mod, "r") == [_INCOMPLETE("a", 1)]


def test_the_run_time_error_says_what_happened_and_what_to_do(native):
    """D68: Mike -- "When the error is raised, is it clear enough what has
    happened?  These are subtle errors."  The message names the clause
    holding the cut, the tabled predicate, why its table is still being
    computed (here: a recursive call inside a/1's own evaluation), what the
    cut would do, and what to do instead."""
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    mod = native.load("l3_tab_rt_msg", THROUGH_UNTABLED)
    with pytest.raises(LogicException) as e:
        list(call("a", Var(), module=mod))
    msg = str(e.value)
    assert "permission_error(cut,incomplete_table,a/1)" in msg
    assert ("in predicate a/1 would prune the call to the tabled predicate "
            "a/1 while its table is still being computed") in msg
    assert ("the call is made inside the evaluation of a/1 itself "
            "(a recursive call, directly or through other predicates)") in msg
    assert "the cut would throw away answers it has not produced yet" in msg
    assert "Collect the answers first (findall/3 over the call" in msg
    assert "move the commit out of the recursive evaluation" in msg


MUTUAL = """\
:- table(p/1).
:- table(q/1).
p(X) :- once(qq(X)).
p(5).
qq(X) :- q(X).
q(X) :- p(Y), X is Y + 1, X < 3.
q(0).
r(E) :- catch((findall(X, p(X), _), E = none), error(E0, _), E = E0).
"""


def test_a_cut_over_an_scc_members_incomplete_table_names_the_ancestor(native, ans):
    """The refused case that remains after D68: q/1 is a fresh call made
    inside p/1's evaluation, and q/1 calls p/1 back, so q/1's table cannot
    complete before p/1's does.  It hands back what it has so far, and
    once/1 over it raises, naming p/1 as the evaluation it is inside."""
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    mod = native.load("l3_tab_rt_mutual", MUTUAL)
    assert ans(mod, "r") == [_INCOMPLETE("q", 1)]
    mod = native.load("l3_tab_rt_mutual_msg", MUTUAL)
    with pytest.raises(LogicException) as e:
        list(call("p", Var(), module=mod))
    msg = str(e.value)
    assert ("in predicate p/1 would prune the call to the tabled predicate "
            "q/1 while its table is still being computed") in msg
    assert ("the call is made inside the evaluation of the tabled predicate "
            "p/1, and q/1 depends on it (mutual recursion)") in msg


CALL_N = """\
:- table(path/2).
e(a, b). e(b, a).
path(X, Y) :- e(X, Y).
path(X, Y) :- path(X, Z), e(Z, Y).
u(Y) :- G = (path(a, Y), !), call(G).
r(E) :- catch((findall(Y, u(Y), _), E = none), error(E0, _), E = E0).
"""


def test_a_run_time_built_goal_cutting_over_a_root_recursive_table_runs(native, ans):
    """path/2 is left-recursive, but u/1 calls it from outside any table's
    evaluation: its table (the whole SCC) completes before the first answer
    (D68), and the cut keeps the first answer in TABLE order, b -- the
    answer the untabled program gives too (e(a, b) is path/2's first
    derivation).  Scryer: [a] (its own table order).  It raised
    permission_error(cut, incomplete_table, path/2) before D68, and before
    the run-time check answered [b] silently from an incomplete table."""
    mod = native.load("l3_tab_rt_calln", CALL_N)
    assert ans(mod, "r") == ["none"]
    mod = native.load("l3_tab_rt_calln_u", CALL_N)
    assert ans(mod, "u") == ["b"]


INDIRECT = """\
:- table(t/1).
t(1). t(2). t(3).
tq(X) :- t(X).
p(1). p(2).
done(X) :- findall(Y, t(Y), _), tq(X), !.
w(X) :- tq(X), !.
w2(X) :- tq(X), X > 1, !.
o1(X) :- once(tq(X)).
o2(X) :- ( tq(X) -> true ; X = 0 ).
o3(X) :- setup_call_cleanup(tq(X), true, true).
n1(X) :- \\+ \\+ tq(_), p(X), !.
n2(X) :- catch((tq(Y), Y > 1, throw(oops)), oops, true), p(X), !.
n3(X) :- tq(X), \\+ (p(Y), !, Y > 5).
n4(X) :- tq(X), \\+ (findall(Y, tq(Y), _), !, fail).
fa(L) :- findall(X, (tq(X), !), L).
nf(L) :- findall(x, \\+ (tq(_), !, fail), L).
r(N, E) :- G =.. [N, _], catch((findall(x, G, _), E = none), error(E0, _), E = E0).
"""


def test_a_cut_after_its_tables_completed_runs(native, ans):
    """The static rule refuses ``t(X), !`` even over a COMPLETE table (our
    ruling, test_cut_over_a_tabled_call_is_refused_at_load's tc/1); the
    run-time half only adds what the static rule cannot see, and only over
    an INCOMPLETE table.  done/1 completes t/1 with findall/3 first, so its
    cut over tq/1 prunes nothing incomplete.  Scryer: [1]."""
    mod = native.load("l3_tab_rt_done", INDIRECT)
    assert ans(mod, "done") == [1]


@pytest.mark.parametrize("name,want", [
    ("w", [1]), ("w2", [2]), ("o1", [1]), ("o2", [1]), ("o3", [1]),
    ("fa", [[1]]), ("nf", [["x"]])])
def test_every_commit_over_a_fresh_table_runs_over_a_complete_table(native, ans, name, want):
    """D68 (operator ruling 2026-10-16, option B; XSB's local scheduling):
    a ``!``, an if-then-else commit, once/1 and setup_call_cleanup's Setup,
    each over t/1 reached through the untabled tq/1 (w2/1 commits on its
    SECOND answer); fa/1 and nf/1 cut inside findall's goal and inside a
    \\+ nested in it.  t/1 is called outside any table's evaluation, so it
    completes its table before its first answer and every commit prunes a
    COMPLETE table, with the answer the untabled program gives.  Each
    raised permission_error(cut, incomplete_table, t/1) before D68.
    Scryer answers [1], [2], [1], [1], [1], [[1]], [[]] (recorded when the
    series was written).  nf/1 differs: ``(tq(_), !, fail)`` fails, so its
    \\+ succeeds and findall/3 collects one x, as ISO says for the same
    program untabled; Scryer's [[]] is its tabling's answer, which this
    engine does not reproduce (not re-checked here: no Scryer binary)."""
    mod = native.load("l3_tab_rt_" + name, INDIRECT)
    assert ans(mod, "r", 2, name) == ["none"]
    mod = native.load("l3_tab_rt_ok_" + name, INDIRECT)
    assert ans(mod, name) == want


@pytest.mark.parametrize("name,want", [("n1", [1]), ("n2", [1]), ("n3", [1, 2, 3]),
                                       ("n4", [1, 2, 3])])
def test_a_sub_search_abandoned_by_backtracking_is_not_pruned_by_the_cut(native, ans, name, want):
    """\\+ and catch/3's recovery abandon t/1's leader mid-stream, but they
    undo the trail past it first, so a later cut does not prune it; a cut
    inside \\+ does not reach the tq/1 call before it, even when a tabled
    call made inside the \\+ (and finished there) moved the counter: the
    still-streaming tq/1 call opened BEFORE the \\+ is not in its scope
    (n4).  Scryer agrees."""
    mod = native.load("l3_tab_rt_" + name, INDIRECT)
    assert ans(mod, name) == want


def test_the_switch_turns_off_the_run_time_half_too(native, ans, monkeypatch):
    from clausal.logic.compiler import cut_scope
    monkeypatch.setattr(cut_scope, "CUT_OVER_TABLED_CALL", "run")
    mod = native.load("l3_tab_rt_switch", INDIRECT)
    assert ans(mod, "w") == [1]                               # Scryer: [1]


def test_a_cut_does_not_see_the_tabled_frames_of_another_query(native, ans):
    """Final re-review N-1: Python holds one call() iterator open, with t/1's
    leader live and incomplete, while another query on the same thread runs
    a cut that has no tabled call in its scope.  The record is keyed by
    trail, so the other query's cut ignores it.  Base: [1, 2]."""
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    src = ":- table(t/1).\nt(1). t(2). t(3).\nc(X) :- ( X = 1 ; !, X = 2 ).\n"
    mod = native.load("l3_tab_rt_interleaved", src)
    x, held, got = Var(), [], []
    for _ in call("c", x, module=mod):
        got.append(deref(x))
        it = iter(call("t", Var(), module=mod))
        next(it)
        held.append(it)
    assert got == [1, 2]


LIB = """\
:- module(rt_util, [first/1, first_scc/1]).
:- meta_predicate(first(0)).
:- meta_predicate(first_scc(0)).
first(G) :- once(G).
first_scc(G) :- setup_call_cleanup(G, true, true).
"""

LIB_USER = """\
:- use_module(rt_util).
:- table(path/2).
e(a, b). e(b, a).
path(X, Y) :- e(X, Y).
path(X, Y) :- path(X, Z), e(Z, Y).
u1(Y) :- first(path(a, Y)).
u2(Y) :- first_scc(path(a, Y)).
r(N, E) :- G =.. [N, _], catch((findall(x, G, _), E = none), error(E0, _), E = E0).
"""


@pytest.mark.parametrize("name", ["u1", "u2"])
def test_once_on_a_goal_argument_in_a_table_blind_module_commits_a_complete_table(native, ans, tmp_path, name):
    """Final re-review N-2: a library meta-predicate (``first(G) :-
    once(G).``) in a module that tables and imports nothing commits over
    the caller's recursive table.  Its goal is a variable, so the check is
    emitted whatever the module can see.  Since D68 path/2 is called
    outside any table's evaluation and completes first, so the commit takes
    the first answer in table order, b (the untabled program's answer).
    Before D68: the run-time error (XSB's); before that, [b] silently from
    an incomplete table.  Scryer: [a]."""
    (tmp_path / "rt_util.pl").write_text(LIB)
    mod = native.load("l3_tab_rt_lib_" + name, LIB_USER)
    assert ans(mod, "r", 2, name) == ["none"]
    mod = native.load("l3_tab_rt_lib_ok_" + name, LIB_USER)
    assert ans(mod, name) == ["b"]


LIB_USER_IN_TABLE = """\
:- use_module(rt_util).
:- table(path/2).
e(a, b). e(b, a).
path(X, Y) :- e(X, Y).
path(X, Y) :- path(X, Z), first(e(Z, Y)), first(path(Z, _)).
r(E) :- catch((findall(Y, path(a, Y), _), E = none), error(E0, _), E = E0).
"""


def test_once_on_a_goal_argument_inside_the_tables_own_evaluation_is_refused(native, ans, tmp_path):
    """The N-2 route still raises where the table really is incomplete:
    the library's once/1 commits over a recursive call of path/2 made
    inside path/2's own evaluation."""
    (tmp_path / "rt_util.pl").write_text(LIB)
    mod = native.load("l3_tab_rt_lib_in", LIB_USER_IN_TABLE)
    assert ans(mod, "r") == [_INCOMPLETE("path", 2)]


def test_once_on_a_closed_goal_in_a_table_blind_module_is_not_checked():
    """The other side of N-2's rule: once/1 over a literal goal with no
    call/N, in a .pl module that cannot see a table, compiles as it did
    before cut existed (the codegen snapshot pins that); a variable goal or
    a call/N in it is checked.  .clausal/.seam never get the check."""
    from clausal.end_module import SURFACE_PL
    from clausal.logic.compiler.compile_ctx import CompilationContext
    from clausal.logic.compiler.cut_scope import commit_check
    from clausal.logic.database import Database
    from clausal.logic.variables import Var
    from clausal.pythonic_ast import nodes
    from clausal.terms import Call, LoadName

    def ctx(surface):
        db = Database()
        db.surface = surface
        return CompilationContext(db=db, var_context={}, trail_name="trail")

    def call(f, *a):
        return Call(func=LoadName(name=f), args=list(a), kwargs=[])
    pl = ctx(SURFACE_PL)
    assert commit_check(pl, call("mem", Var(), [1])) == ([], [])
    assert commit_check(pl, Var()) != ([], [])
    assert commit_check(pl, nodes.And(left=call("p"), right=call("call", Var()))) != ([], [])
    assert commit_check(pl, nodes.And(left=call("p"), right=call("q", Var()))) == ([], [])
    assert commit_check(ctx(None), Var()) == ([], [])
