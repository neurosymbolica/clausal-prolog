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
