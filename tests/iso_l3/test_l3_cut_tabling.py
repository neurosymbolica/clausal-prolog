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


def test_a_run_time_goal_is_out_of_reach(native, ans):
    src = (":- table(tf/1).\ntf(1). tf(2).\n"
           "c(L) :- G = (tf(X), !), findall(X, call(G), L).\n")
    mod = native.load("l3_tab_rt", src)
    assert ans(mod, "c") == [[1]]                             # Scryer: [[1]]


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
