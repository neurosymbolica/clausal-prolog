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
    barrier scope -- whether or not the CALLER is tabled (XSB).  Scryer runs
    tc/1 (answers [1]); XSB's rule is the ruling (Spec S37)."""
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
local(X) :- once(tf(X)), !.
"""


def test_a_tabled_call_outside_the_cuts_scope_is_allowed(native, ans):
    """A tabled call AFTER the cut, in the Then branch, in an EARLIER
    disjunct, or inside a barrier (once/1) that the cut does not see into,
    is not in the cut's scope.  Scryer gives the same answers."""
    mod = native.load("l3_tab_scope_ok", SCOPE_OK)
    assert ans(mod, "after") == [1]
    assert ans(mod, "then") == [1]
    assert sorted(ans(mod, "other")) == [1, 1, 2, 3]
    assert ans(mod, "local") == [1]


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


@pytest.mark.parametrize("src", [BAD_IN_FINDALL, BAD_IN_NAF, BAD_IN_COND_CUT, BAD_AFTER_DISJ],
                         ids=["findall", "naf", "cond_cut", "after_disj"])
def test_a_cut_inside_a_barrier_over_a_tabled_call_is_refused(native, src):
    """A barrier (findall's goal, \\+, an ITE condition) is a scope of its
    own; a cut in it over a tabled call in that same scope breaks the rule
    just as a clause-level cut does.  A disjunction before the cut puts its
    tabled calls in the cut's scope."""
    with pytest.raises(SyntaxError, match=r"tabled.*tf/1"):
        native.load("l3_tab_bad_barrier", src)


def test_the_refusal_names_the_predicate_and_the_line(native):
    with pytest.raises(SyntaxError, match=r"in predicate tc/1 \(line 4\).*tf/1"):
        native.load("l3_tab_where", BAD_UNTABLED_CALLER)


def test_the_one_switch_relaxes_to_scryers_behaviour(native, ans, monkeypatch):
    """Ruling Q1 is provisional: ``cut_scope.CUT_OVER_TABLED_CALL = "run"``
    compiles the cut as written.  Scryer: tc/1 answers [1]."""
    from clausal.logic.compiler import cut_scope
    monkeypatch.setattr(cut_scope, "CUT_OVER_TABLED_CALL", "run")
    mod = native.load("l3_tab_run", BAD_UNTABLED_CALLER)
    assert ans(mod, "tc") == [1]
