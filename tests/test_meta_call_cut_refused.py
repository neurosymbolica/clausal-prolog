"""A cut INSIDE a meta-called body is refused, never run as ``true``.

Clausal is cut-free with no committed choice (ruled permanently).  No clause
body can spell ``!`` (the seam's parser rejects it; the native ``.pl`` front
end refuses it at load), so the only way a cut reaches the solver is as a
TERM built at run time and handed to a meta-call.  ``call/1``'s zero-arity
table answers ``!`` as ``true``, and every meta-call reaches its goal
through call/1, so the cut in ``call((p(X), !))`` ran as ``true`` and gave
BOTH ``p`` answers where ISO 7.8.3 and Scryer give the first -- a silently
wrong answer set.

Two cases, split on whether the cut is the WHOLE goal of the call:

- the whole goal (``call(!)``, ``\\+ !``, ``findall(X, !, L)``, a variable
  leaf bound to ``!`` at run time): ISO makes the cut local to the call, so
  there is nothing to cut and ``true`` is the ISO answer.  Unchanged.
- a leaf INSIDE a body term (``(G, !)``, ``(!, G)``, ``(G ; !)``,
  ``\\+ (G, !)``, ``findall(X, (p(X), !), L)``): refused with
  ``existence_error(procedure, !/0)`` -- the form ``->``/``*->`` already get
  at run time (``call_body.iso_control_cell_dispatch``), which is what an
  ISO system answers for a construct it does not provide.

``assertz(!)`` / ``asserta(!)`` are ``permission_error(modify,
static_procedure, !/0)`` (ISO 8.9.1.3 c, Scryer); they used to STORE a fact
``!/0``.
"""
from __future__ import annotations

import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call as pcall
from clausal.logic.variables import Var, deref, walk
from tests._suffix import SEAM

CUT_REFUSED = ("existence_error", "procedure", ("/", "!", 0))


@pytest.fixture
def lm(tmp_path):
    path = tmp_path / f"cutrefused{SEAM}"
    path.write_text(textwrap.dedent("""
        -dynamic(h/1)
        p(1),
        p(2),
        a(S, S),
        cg1(G) <- call(G),
        cg2(G, A) <- call(G, A),
    """).lstrip())
    return _load_module("cutrefused", str(path)).__dict__["$module"]


def _formal(exc):
    return exc.term[1]


def _refused(goal, lm):
    with pytest.raises(LogicException) as ei:
        list(pcall("cg1", goal, module=lm))
    return _formal(ei.value)


X = Var()


@pytest.mark.parametrize("label, goal", [
    ("(G, !)", (",", ("p", X), "!")),
    ("(!, G)", (",", "!", ("p", X))),
    ("(G ; !)", (";", ("p", X), "!")),
    ("(! ; G)", (";", "!", ("p", X))),
    ("\\+ (G, !)", ("\\+", (",", ("p", X), "!"))),
    ("call((G, !))", ("call", (",", ("p", X), "!"))),
    ("m:(G, !)", (":", "cutrefused", (",", ("p", X), "!"))),
    ("findall(X, (p(X), !), L)", ("findall", X, (",", ("p", X), "!"), Var())),
    ("forall(p(X), (true, !))", ("forall", ("p", X), (",", "true", "!"))),
    ("once((p(X), !))", ("once", (",", ("p", X), "!"))),
    ("aggregate_all(count, (p(X), !), C)",
     ("aggregate_all", "count", (",", ("p", X), "!"), Var())),
    ("phrase((a, !), [])", ("phrase", (",", "a", "!"), [])),
    ("phrase((a, !), [], R)", ("phrase", (",", "a", "!"), [], Var())),
])
def test_a_cut_in_a_meta_call_is_refused(lm, label, goal):
    """Each of these ran the cut as ``true`` (phrase: reached the fold as
    the nonterminal ``!/2``)."""
    assert _refused(goal, lm) == CUT_REFUSED, label


def test_the_hole_the_answer_count_used_to_show(lm):
    """``call((p(X), !))`` gave 2 answers; Scryer gives 1.  It gives none:
    the body is refused when it is converted, before it runs."""
    seen = []
    with pytest.raises(LogicException) as ei:
        for _ in pcall("cg1", (",", ("p", X), "!"), module=lm):
            seen.append(walk(deref(X)))
    assert _formal(ei.value) == CUT_REFUSED
    assert seen == []


def test_catch_sees_the_refusal_as_an_ordinary_error(lm):
    """``catch((p(X), !), error(E, _), true)`` catches it: E is the
    existence_error, so a portable "no such procedure" handler sees it."""
    E = Var()
    sols = []
    for _ in pcall("cg1", ("catch", (",", ("p", X), "!"),
                           ("error", E, Var()), "true"), module=lm):
        sols.append(walk(deref(E)))
    assert sols == [CUT_REFUSED]


@pytest.mark.parametrize("label, goal, n", [
    ("call(!)", "!", 1),
    ("call(call, !)", ("call", "!"), 1),
    ("m:!", (":", "cutrefused", "!"), 1),
    ("\\+ !", ("\\+", "!"), 0),
    ("findall(X, !, L)", ("findall", X, "!", Var()), 1),
    ("forall(p(X), !)", ("forall", ("p", X), "!"), 1),
    ("once(!)", ("once", "!"), 1),
    # a VARIABLE leaf is call(V): the cut bound to it at run time is that
    # call's whole goal (ISO 7.6.2), so both p answers stand
    ("(p(X), V = !, V)", (",", ("p", X), (",", ("=", V := Var(), "!"), V)), 2),
])
def test_a_cut_that_is_the_whole_goal_is_unchanged(lm, label, goal, n):
    """ISO 7.8.3: a cut that is the whole goal of a call is local to it and
    cuts nothing, so ``true`` is the ISO answer -- kept."""
    assert len(list(pcall("cg1", goal, module=lm))) == n, label


@pytest.mark.parametrize("builtin", ["assertz", "asserta"])
def test_asserting_the_cut_is_a_permission_error(lm, builtin):
    with pytest.raises(LogicException) as ei:
        list(pcall("cg1", (builtin, "!"), module=lm))
    assert _formal(ei.value) == (
        "permission_error", "modify", "static_procedure", ("/", "!", 0))
    with pytest.raises(LogicException) as ei:
        list(pcall("cg1", (builtin, (":-", "!", "true")), module=lm))
    assert _formal(ei.value) == (
        "permission_error", "modify", "static_procedure", ("/", "!", 0))


def test_a_runtime_rule_with_a_cut_stays_refused(lm):
    """Already refused before this change (rules are never asserted at run
    time); pinned so the cut cannot come in through assert either."""
    with pytest.raises(LogicException) as ei:
        list(pcall("cg1", ("assertz", (":-", ("h", X), (",", ("p", X), "!"))),
                   module=lm))
    assert _formal(ei.value)[:3] == ("permission_error", "assert", "rule")


def test_cut_with_extra_arguments_is_still_the_folded_procedure(lm):
    """``call(!, x)`` is the goal ``!/1``, which no database defines."""
    with pytest.raises(LogicException) as ei:
        list(pcall("cg2", "!", "x", module=lm))
    assert _formal(ei.value) == ("existence_error", "procedure",
                                 ("/", "!", 1))


def test_true_and_fail_by_name_are_unchanged(lm):
    assert len(list(pcall("cg1", "true", module=lm))) == 1
    assert list(pcall("cg1", "fail", module=lm)) == []
    assert len(list(pcall("cg1", (",", ("p", X), "true"), module=lm))) == 2


def test_the_seam_cannot_spell_a_cut(tmp_path):
    """The seam has no cut at all: Python's parser rejects ``!``."""
    path = tmp_path / f"seamcut{SEAM}"
    path.write_text("q(1),\np(X) <- (q(X), !),\n")
    with pytest.raises(SyntaxError):
        _load_module("seamcut", str(path))


# ── a cut bound to a variable BEFORE the meta-call that converts it ────────
#
# A meta-argument goal is converted to a body when the meta-call CALLS it
# (ISO 8.10.1 findall/3, 8.15.2 once/1, 7.8.9 catch/3 ...), not when the
# clause is read: a variable sitting in it under ``,``/``;`` is dereferenced
# then, so ``G = !, findall(X, (p(X), G), L)`` converts the body
# ``(p(X), !)`` -- a cut INSIDE a body, refused like the rows above.  The
# Clausal Prolog front end compiled the meta-argument as written, the
# variable as ``call(G)``, so the cut ran as ``true`` and gave every ``p``
# answer (Scryer: the first).  A ``.pl`` file already converted it when
# called; its rows below are Scryer's answers (2026-10-23).
#
# Unchanged, because ISO converts a CLAUSE body at consult: a variable goal
# in a clause body is ``call(G)``, so a cut bound to it is that call's whole
# goal (``cb/1``, ``u/1``); and a variable bound only after the meta-call
# started (``late``) was unbound when the body was converted.

RUNTIME_CUT_SRC = """\
:- use_module(library(lambda)).
:- use_module(library(reif)).
p(1).
p(2).
cc(G, Y) :- p(Y), G.
cb(X) :- G = !, p(X), G.
r(Name, R) :- catch((s(Name, L), R = ran(L)), error(E, _), R = caught(E)).
u(R) :- G = !, catch((call(G), R = ran), E, R = caught(E)).
s(findall_conj, L) :- G = !, findall(X, (p(X), G), L).
s(findall_disj, L) :- G = !, findall(X, (p(X) ; G), L).
s(findall_nested, L) :- G = !, findall(X, (p(X), (true, G)), L).
s(findall4, L) :- G = !, findall(X, (p(X), G), L, []).
s(neg, L) :- G = !, findall(x, \\+ (p(_), G, fail), L).
s(once, L) :- G = !, findall(X, once((p(X), G)), L).
s(forall, L) :- G = !, findall(x, forall(p(_), (true, G)), L).
s(catch, L) :- G = !, findall(X, catch((p(X), G), foo, true), L).
s(aggregate_all, L) :- G = !, aggregate_all(count, (p(_), G), L).
s(bagof, L) :- G = !, bagof(X, (p(X), G), L).
s(setof, L) :- G = !, setof(X, (p(X), G), L).
s(bagof_caret, L) :- G = !, bagof(X, Y^(p(X), Y = 1, G), L).
s(setup_call_cleanup, L) :-
    G = !, findall(X, setup_call_cleanup(true, (p(X), G), true), L).
s(call_cleanup, L) :- G = !, findall(X, call_cleanup((p(X), G), true), L).
s(call_n, L) :- G = !, findall(X, call(','(p(X)), G), L).
s(variable_body, L) :- G = !, B = (p(X), G), findall(X, B, L).
s(lambda, L) :- G = !, findall(Y, maplist(\\Z^(p(Z), G), [Y]), L).
s(maplist_closure, L) :- G = !, findall(Y, maplist(cc(G), [Y]), L).
s(if_branch, L) :- G = !, findall(X, if_(1 = 1, (p(X), G), true), L).
s(if_else_branch, L) :- G = !, findall(X, if_(1 = 2, true, (p(X) ; G)), L).
s(bound_body, L) :- G = (true, !), findall(X, (p(X), G), L).
s(whole, L) :- G = !, findall(x, G, L).
s(late, L) :- findall(X, (p(X), G = !, G), L).
s(clause_body, L) :- findall(X, cb(X), L).
s(cut_free, L) :- G = true, findall(X, (p(X), G), L).
s(not_callable, L) :- G = 1, findall(X, once((X = 8 ; G)), L).
s(not_callable_deep, L) :- G = (true, 1), findall(X, once((X = 8 ; G)), L).
"""

#: Every route a Clausal Prolog module meta-calls a body holding a cut by.
RUNTIME_CUT_REFUSED = [
    "findall_conj", "findall_disj", "findall_nested", "findall4", "neg",
    "once", "forall", "catch", "aggregate_all", "bagof", "setof",
    "bagof_caret", "setup_call_cleanup", "call_cleanup", "call_n",
    "variable_body", "lambda", "if_branch", "if_else_branch", "bound_body",
]

#: Scryer's answer for each row in a ``.pl`` file (2026-10-23; the same
#: program with library(lambda), lists and iso_ext loaded).
SCRYER = {
    "findall_conj": [1], "findall_disj": None, "findall_nested": [1],
    "findall4": [1], "neg": ["x"], "once": [1], "forall": ["x"],
    "catch": [1], "bagof": [1], "setof": [1], "bagof_caret": [1],
    "setup_call_cleanup": [1], "call_cleanup": [1], "call_n": [1],
    "variable_body": [1], "lambda": [1], "if_branch": [1],
    "if_else_branch": None, "bound_body": [1],
}


def _load_surface(tmp_path, name, suffix):
    path = tmp_path / f"{name}{suffix}"
    path.write_text(RUNTIME_CUT_SRC)
    return _load_module(name, str(path)).__dict__["$module"]


@pytest.fixture
def clausal_prolog(tmp_path):
    from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES
    return _load_surface(tmp_path, "cutbound_cl", CLAUSAL_PROLOG_SUFFIXES[0])


@pytest.fixture
def iso_prolog(tmp_path):
    from clausal._suffixes import PROLOG_SUFFIX
    return _load_surface(tmp_path, "cutbound_pl", PROLOG_SUFFIX)


def _answers(mod, name):
    R = Var()
    return [walk(deref(R)) for _ in pcall("r", name, R, module=mod)]


@pytest.mark.parametrize("name", RUNTIME_CUT_REFUSED)
def test_a_cut_bound_before_the_meta_call_is_refused(clausal_prolog, name):
    """Each of these ran the bound cut as ``true`` (``aggregate_all``,
    ``call_n``, ``variable_body`` and ``lambda`` already converted their
    goal at run time, and are pinned so every route stays covered).  An
    ``if_/3`` branch is reif's to CALL (the ``.pl`` lowering already said
    so for a cut written there, 2026-10-20), so a cut bound into it is a
    cut inside a meta-called body as well."""
    assert _answers(clausal_prolog, name) == [("caught", CUT_REFUSED)], name


@pytest.mark.parametrize("name, want", [
    ("whole", [["x"]]),                 # findall(x, !, L): the whole goal
    ("late", [[1, 2]]),                 # G unbound when the body converted
    ("clause_body", [[1, 2]]),          # cb/1's G is call(G): consult time
    ("maplist_closure", [[1, 2]]),      # cc/2's G likewise
    ("cut_free", [[1, 2]]),
])
def test_a_cut_that_is_a_whole_goal_is_still_true(clausal_prolog, name, want):
    got = _answers(clausal_prolog, name)
    assert [g[1] for g in got] == want and all(g[0] == "ran" for g in got)


def test_call_of_a_variable_bound_to_a_cut_is_true(clausal_prolog):
    """``G = !, call(G)``: the cut is call/1's whole goal (ISO 7.8.3), so it
    cuts nothing -- Scryer answers ``R = ran`` too."""
    R = Var()
    assert [walk(deref(R)) for _ in pcall("u", R, module=clausal_prolog)] \
        == ["ran"]


def test_a_non_callable_bound_into_a_meta_argument_names_the_whole_goal(
        clausal_prolog):
    """ISO 7.6.2 / Scryer: ``type_error(callable, (X = 8 ; 1))``, checked when
    once/1 converts its goal; it used to be ``type_error(callable, 1)``."""
    [(tag, err)] = _answers(clausal_prolog, "not_callable")
    assert tag == "caught" and err[:2] == ("type_error", "callable")
    culprit = err[2]
    assert culprit[0] == ";" and culprit[1][0] == "=" and culprit[2] == 1
    # deeper, through the bound variable: still the whole goal
    [(tag, err)] = _answers(clausal_prolog, "not_callable_deep")
    assert tag == "caught" and err[:2] == ("type_error", "callable")
    assert err[2][0] == ";" and err[2][2] == (",", True, 1)


@pytest.mark.parametrize("name", sorted(SCRYER))
def test_a_pl_module_runs_the_bound_cut_as_scryer_does(iso_prolog, name):
    """Control: in a ``.pl`` file the cut runs, local to the meta-call."""
    [(tag, got)] = _answers(iso_prolog, name)
    assert tag == "ran", (name, got)
    if name in ("findall_disj", "if_else_branch"):  # [1, 2, _]: cut last
        assert got[:2] == [1, 2] and len(got) == 3
    else:
        assert got == SCRYER[name], name


def test_a_pl_module_keeps_call_of_a_bound_cut_true(iso_prolog):
    R = Var()
    assert [walk(deref(R)) for _ in pcall("u", R, module=iso_prolog)] \
        == ["ran"]
