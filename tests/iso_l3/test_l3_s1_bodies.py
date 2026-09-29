"""Slice 1, bodies: rules and the control constructs ``,`` ``;`` ``\\+``
``true`` ``fail``/``false`` and ``call/N``; a variable goal is ``call(G)``
(ISO 7.6.2), in a meta-argument position too.  Loaded through the REAL import
path with ``CLAUSAL_PL_FRONTEND=native``.
"""
from __future__ import annotations

import ast
import warnings

import pytest

from clausal.lint_warnings import ClausalSingletonWarning
from clausal.tools import iso_l3 as L3

GRAPH = "edge(a, b).\nedge(b, c).\nedge(c, d).\n"


def test_recursion(native, ans):
    mod = native.load("s1_path", GRAPH +
                      "path(X, Y) :- edge(X, Y).\n"
                      "path(X, Y) :- edge(X, Z), path(Z, Y).\n")
    assert ans(mod, "path", 2, "a") == ["b", "c", "d"]
    assert mod.__loader__.l3_stats["lowered"] == 5


def test_disjunction_keeps_iso_order(native, ans):
    mod = native.load("s1_or", "d(X) :- ( X = 1 ; X = 2 ; X = 3 ).\n")
    assert ans(mod, "d") == [1, 2, 3]


def test_negation_as_failure(native, ans):
    mod = native.load("s1_not", GRAPH +
                      "source(X) :- edge(X, _), \\+ edge(_, X).\n")
    assert ans(mod, "source") == ["a"]


def test_true_fail_false(native, ans):
    mod = native.load("s1_tf", "t(1) :- true.\nt(2) :- fail.\nt(3) :- false.\n"
                               "t(4) :- true, true.\n")
    assert ans(mod, "t") == [1, 4]


def test_call_n_and_a_variable_goal(native, ans):
    mod = native.load("s1_call", GRAPH +
                      "c1(Y) :- call(edge, a, Y).\n"
                      "c2(Y) :- G = edge(b, Y), call(G).\n"
                      "c3(Y) :- G = edge(c, Y), G.\n"
                      "c4(Y) :- call(edge(a), Y).\n"
                      "c5(Y) :- G = (edge(a, Z), edge(Z, Y)), call(G).\n")
    assert ans(mod, "c1") == ["b"]
    assert ans(mod, "c2") == ["c"]
    assert ans(mod, "c3") == ["d"]
    assert ans(mod, "c4") == ["b"]
    assert ans(mod, "c5") == ["c"]


def test_a_variable_goal_lowers_to_call():
    mod, _ = L3.lower_items(L3.read_iso("v(G) :- G.\n"))
    calls = [n for n in ast.walk(mod) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "$LoadName"]
    assert [ast.literal_eval(k.value) for c in calls for k in c.keywords
            if k.arg == "name"] == ["call"]


def test_a_variable_in_a_meta_argument_position_is_call_g(native, ans):
    """``findall(X, G, L)`` with G a variable is refused by the compiler
    (BareGoalVariableError) unless lowered as ``call(G)``."""
    mod = native.load("s1_meta", GRAPH +
                      "all(L) :- G = edge(_, X), findall(X, G, L).\n"
                      "n(L) :- G = edge(a, _), findall(t, \\+ G, L).\n"
                      "f(L) :- findall(X-Y, (edge(X, Z), edge(Z, Y)), L).\n")
    assert ans(mod, "all") == [["b", "c", "d"]]
    assert ans(mod, "n") == [[]]
    assert ans(mod, "f") == [[("-", "a", "c"), ("-", "b", "d")]]


def test_bagof_setof_keep_the_iterated_goal(native, ans):
    """``^`` in bagof/setof's goal is the existential prefix (ISO 7.1.1.4):
    one answer, [1,2,3] -- the translator's two answers were the defect."""
    mod = native.load("s1_caret",
                      "p(1, a).\np(2, a).\np(3, b).\n"
                      "s(L) :- setof(X, Y^p(X, Y), L).\n"
                      "g(Y-L) :- setof(X, p(X, Y), L).\n"
                      "b(L) :- G = Y^p(X, Y), bagof(X, G, L).\n")
    assert ans(mod, "s") == [[1, 2, 3]]
    assert ans(mod, "g") == [("-", "a", [1, 2]), ("-", "b", [3])]
    assert ans(mod, "b") == [[1, 2, 3]]


def test_caret_outside_bagof_setof_is_just_a_term(native, ans):
    mod = native.load("s1_caret_data",
                      "c(T) :- T = 2^3.\nv(X) :- X is 2^3.\n")
    assert ans(mod, "c") == [("^", 2, 3)]
    assert ans(mod, "v") == [8]


def test_rule_positions_point_at_pl_lines():
    src = "a(1).\n\np(X) :-\n    q(X),\n    r(X).\n"
    mod, _ = L3.lower_items(L3.read_iso(src), source=src)
    calls = {ast.literal_eval(k.value): n for n in ast.walk(mod)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "$LoadName"
             for k in n.keywords if k.arg == "name"}
    pos = {name: ast.literal_eval(next(k.value for k in c.keywords
                                       if k.arg == "position"))
           for name, c in calls.items()}
    assert pos["q"][:2] == (4, 4) and pos["r"][:2] == (5, 4)


# ── the singleton lint (D19: a `_`-prefixed name is exempt in a .pl) ──


def _singletons(native, name, text):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        native.load(name, text)
    return [str(w.message) for w in caught
            if issubclass(w.category, ClausalSingletonWarning)]


def test_a_plain_singleton_warns_with_its_pl_line(native):
    found = _singletons(native, "s1_single",
                        "p(1, a).\n\nh(L) :- setof(Z, p(Z, W), L).\n")
    assert len(found) == 1, found
    assert "`W`" in found[0] and "s1_single.pl:3" in found[0]


def test_an_underscore_variable_is_exempt_as_in_prolog(native, ans):
    """D19 (operator-approved 2026-09-29) supersedes the plan's slice-1 line:
    in a .pl file `_Y` is no singleton.  `_` never is."""
    found = _singletons(native, "s1_under",
                        "p(1, a).\np(2, b).\n"
                        "g(L) :- setof(X, p(X, _Y), L).\n"
                        "k(X) :- p(X, _).\n")
    assert found == []


def test_a_repeated_variable_is_no_singleton(native):
    assert _singletons(native, "s1_twice", "e(X, X).\n") == []


# ── roborev round 1 ──


def test_the_meta_goal_table_matches_the_compilers(native):
    """_META_GOAL_ARGS is index-keyed; ir.META_GOAL_POSITIONS is field-keyed.
    Every compiler meta kind that a .pl program can name must be listed, with
    as many goal positions, so a new one cannot drift in silently."""
    from clausal.logic.compiler.ir import META_GOAL_POSITIONS
    ours = {name: len(ix) for (name, _), ix in L3._META_GOAL_ARGS.items()}
    theirs = {k: len(v) for k, v in META_GOAL_POSITIONS.items()
              if k not in ("catch_error", "catch_recover")}   # not ISO names
    assert ours == theirs


def test_an_operator_goal_position_is_the_whole_goal():
    src = "p(A, B) :- A == B, q(A).\nq(1).\n"
    mod, _ = L3.lower_items(L3.read_iso(src), source=src)
    pos = {}
    for n in ast.walk(mod):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "$LoadName":
            kw = {k.arg: k.value for k in n.keywords}
            pos[ast.literal_eval(kw["name"])] = ast.literal_eval(kw["position"])
    assert pos["=="] == (1, 11, 1, 17)       # `A == B`, not `A =`
    assert pos["q"] == (1, 19, 1, 20)        # prefix goal: the name


@pytest.mark.parametrize("text", ["'None'(1).", "p :- 'True'(1).",
                                  "'False'."])
def test_true_false_none_as_predicate_names_are_refused_cleanly(native, text):
    """``ast.Name`` cannot carry these ids and the engine's codegen raises
    on them (ValueError, no line): refused with the .pl line instead."""
    with pytest.raises(SyntaxError, match="cannot name a predicate") as ei:
        native.load("s1_pyconst", "q.\n" + text + "\n")
    assert ei.value.lineno == 2


def test_a_refusal_line_counts_newlines_only(native):
    with pytest.raises(SyntaxError) as ei:
        native.load("s1_ff", "a('\f').\np :- !.\n")
    assert ei.value.lineno == 2 and ei.value.text == "p :- !."
