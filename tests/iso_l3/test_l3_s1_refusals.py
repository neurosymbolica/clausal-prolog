"""Slice 1, refusals: ``!``, ``->``, ``*->`` (and ``;`` with a ``->`` left
branch) are refused by design on the Clausal Prolog surface (``.clausal``) --
Clausal is cut-free with no committed choice, forever -- and so is anything ISO
says is not a clause.  Each refusal is an import-time ``SyntaxError`` citing
the ruling and naming the file's line; the module does not import.  The same
shapes as DATA load fine.

The refusal of ``!`` and ``->`` is a property of the SURFACE: a ``.pl`` file
runs them with ISO 7.8 semantics (every expected answer below measured on
Scryer Prolog).  ``*->`` is refused on both surfaces (Scryer: it is no ISO
control construct).
"""
from __future__ import annotations

import sys

import pytest

from clausal.tools import iso_l3 as L3

CUT_FREE = "cut-free with no committed choice"


CUT_ROWS = [
    ("r_cut", "p(X) :- q(X), !.", "`!` (cut)"),
    ("r_ite", "p(X) :- ( q(X) -> true ; fail ).", "`->` (if-then)"),
    ("r_it", "p(X) :- ( q(X) -> true ).", "`->` (if-then)"),
    ("r_notcut", "p(X) :- q(X), \\+ !.", "`!` (cut)"),
    ("r_callcut", "p(X) :- call((q(X), !)).", "`!` (cut)"),
    ("r_callite", "p(X) :- call((q(X) -> true ; true)).", "`->` (if-then)"),
    ("r_findcut", "p(L) :- findall(X, (q(X), !), L).", "`!` (cut)"),
    ("r_orcut", "p(X) :- ( q(X) ; ! ).", "`!` (cut)"),
]
SOFT_ROWS = [
    ("r_soft", "p(X) :- ';'('*->'(q(X), true), fail).", "`*->` (soft-cut)"),
    ("r_soft2", "p(X) :- '*->'(q(X), true).", "`*->` (soft-cut)"),
]


def _refused(native, name, body, what, suffix):
    with pytest.raises(SyntaxError) as ei:
        native.load(name, "q(1).\n\n" + body + "\n", suffix=suffix)
    msg = str(ei.value)
    assert what in msg and CUT_FREE in msg, msg
    assert f"{name}{suffix}:3" in msg and ei.value.lineno == 3, msg
    assert name not in sys.modules


@pytest.mark.parametrize("name, body, what", CUT_ROWS + SOFT_ROWS)
def test_the_cut_family_is_refused_with_the_ruling_and_the_line(
        native, name, body, what):
    """On the Clausal Prolog surface the whole family is refused."""
    _refused(native, name + "_cl", body, what, ".clausal")


@pytest.mark.parametrize("name, body, what", SOFT_ROWS)
def test_soft_cut_is_refused_in_a_pl_file_too(native, name, body, what):
    _refused(native, name, body, what, ".pl")


#: Scryer's ``findall(X, p(X), R)`` over ``q(1). q(2).`` and the row's body
#: (None: an unbound variable).
PL_ANSWERS = {
    "r_cut": [1], "r_ite": [1], "r_it": [1], "r_notcut": [],
    "r_callcut": [1], "r_callite": [1], "r_findcut": [[1]],
    "r_orcut": [1, 2, None],
}


@pytest.mark.parametrize("name, body, what", CUT_ROWS)
def test_the_cut_family_runs_in_a_pl_file(native, ans, name, body, what):
    """The same rows in a ``.pl`` file load and answer as ISO (Scryer)."""
    from clausal.logic.variables import Var
    mod = native.load(name, "q(1).\nq(2).\n" + body + "\n")
    got = [None if isinstance(a, Var) else a for a in ans(mod, "p")]
    assert got == PL_ANSWERS[name], got


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
    ("r_dcg_not", "s --> \\+ [a].", "representation_error(dcg_body)"),
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


def test_a_grammar_cut_is_refused_on_the_clausal_surface(native):
    """``.pl``: test_l3_dcg.py runs it (ISO 7.14.2)."""
    with pytest.raises(SyntaxError) as ei:
        native.load("r_dcg_cut", "q.\ns --> [a], !.\n", suffix=".clausal")
    assert ("`!` (cut) is refused" in str(ei.value)
            and ei.value.lineno == 2), str(ei.value)


COUNT_SRC = ("a.\np :- !.\nq :- (a -> a ; a).\n:- nodirective(d/1).\n"
             "r :- a.\n")


def test_counting_mode_counts_every_refusal():
    _, st = L3.lower_items(L3.read_iso(COUNT_SRC), strict=False,
                           source=COUNT_SRC, filename="c.clausal")
    assert (st["read"], st["lowered"], st["refused"]) == (5, 2, 3), st
    assert [m.split(":")[1] for m in st["refusals"]] == ["2", "3", "4"]


def test_counting_mode_lowers_cut_in_a_pl_file():
    _, st = L3.lower_items(L3.read_iso(COUNT_SRC), strict=False,
                           source=COUNT_SRC, filename="c.pl")
    assert (st["read"], st["lowered"], st["refused"]) == (5, 4, 1), st
    assert [m.split(":")[1] for m in st["refusals"]] == ["4"]
