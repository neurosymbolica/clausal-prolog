"""Slice 1, refusals: ``!``, ``->``, ``*->`` (and ``;`` with a ``->`` left
branch) are refused by design -- Clausal is cut-free with no committed choice,
forever -- and so is anything ISO says is not a clause.  Each refusal is an
import-time ``SyntaxError`` citing the ruling and naming the ``.pl`` line; the
module does not import.  The same shapes as DATA load fine.
"""
from __future__ import annotations

import sys

import pytest

from clausal.tools import iso_l3 as L3

CUT_FREE = "cut-free with no committed choice"


@pytest.mark.parametrize("name, body, what", [
    ("r_cut", "p(X) :- q(X), !.", "`!` (cut)"),
    ("r_ite", "p(X) :- ( q(X) -> true ; fail ).", "`->` (if-then)"),
    ("r_it", "p(X) :- ( q(X) -> true ).", "`->` (if-then)"),
    ("r_soft", "p(X) :- ';'('*->'(q(X), true), fail).", "`*->` (soft-cut)"),
    ("r_soft2", "p(X) :- '*->'(q(X), true).", "`*->` (soft-cut)"),
    ("r_notcut", "p(X) :- q(X), \\+ !.", "`!` (cut)"),
    ("r_callcut", "p(X) :- call((q(X), !)).", "`!` (cut)"),
    ("r_callite", "p(X) :- call((q(X) -> true ; true)).", "`->` (if-then)"),
    ("r_findcut", "p(L) :- findall(X, (q(X), !), L).", "`!` (cut)"),
    ("r_orcut", "p(X) :- ( q(X) ; ! ).", "`!` (cut)"),
])
def test_the_cut_family_is_refused_with_the_ruling_and_the_line(
        native, name, body, what):
    with pytest.raises(SyntaxError) as ei:
        native.load(name, "q(1).\n\n" + body + "\n")
    msg = str(ei.value)
    assert what in msg and CUT_FREE in msg, msg
    assert f"{name}.pl:3" in msg and ei.value.lineno == 3, msg
    assert name not in sys.modules


@pytest.mark.parametrize("name, text, fragment", [
    ("r_numgoal", "p :- 1.", "not callable"),
    ("r_numgoal2", "p :- q, 3.5.", "not callable"),
    ("r_varhead", "X :- true.", "head is a variable"),
    ("r_numhead", "1 :- true.", "head is not callable"),
    ("r_strhead", "\"ab\".", "head is not callable"),
    ("r_conjhead", "(a, b) :- true.", "control construct ,/2"),
    ("r_truehead", "true.", "control construct true/0"),
    ("r_callhead", "call(x).", "control construct call/1"),
    ("r_dollarhead", "'$module'(1).", "reserved name"),
    ("r_dollargoal", "p :- '$unify'(a, a).", "reserved name"),
    ("r_directive", ":- initialization(main).", "initialization/1 is refused"),
    ("r_dcg", "s --> [a].", "DCGRule"),
])
def test_what_iso_does_not_make_a_clause_is_refused(native, name, text,
                                                    fragment):
    with pytest.raises(SyntaxError) as ei:
        native.load(name, "q.\n" + text + "\n")
    assert fragment in str(ei.value) and ei.value.lineno == 2, str(ei.value)


def test_the_same_shapes_as_data_load(native, ans):
    mod = native.load("r_data",
                      "d(X) :- X = (a -> b).\nd(X) :- X = !.\n"
                      "d(X) :- X = '*->'(a, b).\nd(X) :- X = (a :- b).\n")
    assert ans(mod, "d") == [("->", "a", "b"), "!", ("*->", "a", "b"),
                             (":-", "a", "b")]


def test_counting_mode_counts_every_refusal():
    src = "a.\np :- !.\nq :- (a -> a ; a).\n:- nodirective(d/1).\nr :- a.\n"
    _, st = L3.lower_items(L3.read_iso(src), strict=False, source=src,
                           filename="c.pl")
    assert (st["read"], st["lowered"], st["refused"]) == (5, 2, 3), st
    assert [m.split(":")[1] for m in st["refusals"]] == ["2", "3", "4"]
