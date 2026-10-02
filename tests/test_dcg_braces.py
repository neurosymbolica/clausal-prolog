"""ISO DCG braces ``{G}`` (``{}//0``... the ``{}/1`` grammar body).

ISO 7.14.2 and Scryer's library(dcgs) translate ``{G}`` as ``G, S0 = S``:
G runs with its bindings shared with the rule, every answer kept, and
consumes nothing.

1. ``phrase({G}, L)`` / ``phrase({G}, L, R)`` and a ``{G}`` inside a
   phrase body raised ``existence_error(procedure, {}/3)`` (the braces were
   looked up as a nonterminal).
2. A rule whose WHOLE body (or a whole disjunct) is ``{G}`` dropped the
   ``S0 = S`` equation, so ``e(X) --> {X = 5}.`` accepted ``[a]`` and left
   phrase/3's rest unbound.  ``.pl`` rules come through the seam rewriter,
   so both surfaces had it.

Scryer (measured, ``findall`` over the goal)::

    phrase({true}, [])                         -> 1
    phrase({true}, [a])                        -> 0
    phrase({fail}, [])                         -> 0
    phrase({member(X, [1,2])}, [])             -> X = 1 ; X = 2
    phrase({member(X, [1,2])}, [a], R)         -> R = [a] (twice)
    phrase({!}, [])                            -> 1
    phrase(({member(X,[1,2,3])}, {!}), [])     -> 1 (the cut is NOT local)
    phrase({G}, [])                            -> instantiation_error
    phrase({3}, [])                            -> type_error(callable, (3, []=[]))
    phrase(({member(X,[1,2])}, {V = !}, V), [])-> 2 (a variable leaf is
                                                  phrase(V, S0, S): local)
    e(X) --> {X = 5}:  phrase(e(X), [a]) -> 0;  phrase(e(X), [a], R) -> R = [a]

A cut inside braces within a larger body is a cut inside a meta-called
body, so Clausal refuses it (existence_error(procedure, !/0)) rather than
cut; a WHOLE body ``{!}`` is the same local cut as ``phrase(!, L)``.
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
    path = tmp_path / f"dcgbraces{SEAM}"
    path.write_text(textwrap.dedent("""
        -private([x])
        p(1),
        p(2),
        cg1(G) <- call(G),
        se(_x) >> ({_x is 5})
        sf(_x) >> ({member(_x, [1, 2])})
        sor(_x) >> ({_x is 1} or [x])
        site(_x) >> if_({_x == 1}, [x], [])
        sboth(_x, _y) >> ({_x is 1, _y is 2})
        snot >> (not {fail})
    """).lstrip())
    return _load_module("dcgbraces", str(path)).__dict__["$module"]


@pytest.fixture
def plm(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUSAL_PL_FRONTEND", raising=False)
    path = tmp_path / "dcgbraces_pl.pl"
    path.write_text(textwrap.dedent("""
        a --> {X = 1}, [x], {X == 1}.
        b(X) --> {member(X, [1,2,3])}, [X].
        c --> {fail}, [x].
        e(X) --> {X = 5}.
        cg1(G) :- call(G).
    """).lstrip())
    return _load_module("dcgbraces_pl", str(path)).__dict__["$module"]


def _sols(m, goal, *outs):
    return [tuple(walk(deref(o)) for o in outs)
            for _ in pcall("cg1", goal, module=m)]


def _err(m, goal):
    with pytest.raises(LogicException) as ei:
        list(pcall("cg1", goal, module=m))
    return ei.value.term[1]


def br(g):
    return ("{}", g)


# ── 1. phrase over a braces body ────────────────────────────────────────────

def test_phrase_true_braces(lm):
    assert _sols(lm, ("phrase", br("true"), [])) == [()]
    assert _sols(lm, ("phrase", br("true"), ["a"])) == []


def test_phrase_failing_braces(lm):
    assert _sols(lm, ("phrase", br("fail"), [])) == []


def test_phrase_nondeterministic_braces_keeps_every_answer(lm):
    X = Var()
    assert _sols(lm, ("phrase", br(("p", X)), []), X) == [(1,), (2,)]


def test_phrase_3_braces_consumes_nothing(lm):
    X, R = Var(), Var()
    assert _sols(lm, ("phrase", br(("p", X)), ["a"], R), X, R) == [
        (1, ["a"]), (2, ["a"])]


def test_braces_share_variables_with_the_rest_of_the_body(lm):
    X = Var()
    body = (",", br(("p", X)), [X])
    assert _sols(lm, ("phrase", body, [2]), X) == [(2,)]


def test_a_whole_body_braced_cut_is_local(lm):
    assert _sols(lm, ("phrase", br("!"), [])) == [()]
    assert _sols(lm, ("phrase", br("!"), ["a"])) == []


def test_a_braced_cut_inside_a_larger_body_is_refused(lm):
    body = (",", br(("p", Var())), br("!"))
    assert _err(lm, ("phrase", body, [])) == CUT_REFUSED


def test_a_variable_leaf_bound_to_a_cut_is_its_own_local_phrase(lm):
    V = Var()
    body = (",", br(("p", Var())), (",", br(("=", V, "!")), V))
    assert len(_sols(lm, ("phrase", body, []))) == 2


def test_unbound_braces_goal_is_an_instantiation_error(lm):
    assert _err(lm, ("phrase", br(Var()), [])) == "instantiation_error"


def test_non_callable_braces_goal_is_a_type_error(lm):
    formal = _err(lm, ("phrase", br(3), []))
    assert formal[:2] == ("type_error", "callable")


def test_the_bare_atom_braces_is_still_a_nonterminal(lm):
    """``'{}'`` alone is the nonterminal ``{}//0`` (Scryer:
    existence_error(procedure, {}/2))."""
    assert _err(lm, ("phrase", "{}", [])) == (
        "existence_error", "procedure", ("/", "{}", 2))


# ── 2. rules whose whole body is braces ─────────────────────────────────────

def test_seam_whole_body_braces_threads_the_state(lm):
    X, R = Var(), Var()
    assert _sols(lm, ("phrase", ("se", X), []), X) == [(5,)]
    assert _sols(lm, ("phrase", ("se", X), ["a"])) == []
    assert _sols(lm, ("phrase", ("se", X), ["a"], R), R) == [(["a"],)]
    assert _sols(lm, ("phrase", ("sf", X), ["a"])) == []
    assert _sols(lm, ("phrase", ("sf", X), []), X) == [(1,), (2,)]


def test_seam_braces_as_a_disjunct_threads_the_state(lm):
    X = Var()
    assert _sols(lm, ("phrase", ("sor", X), []), X) == [(1,)]
    assert len(_sols(lm, ("phrase", ("sor", X), ["x"]))) == 1


def test_seam_braces_as_an_if_condition_threads_the_state(lm):
    R = Var()
    assert _sols(lm, ("phrase", ("site", 1), ["x", "z"], R), R) == [(["z"],)]
    assert _sols(lm, ("phrase", ("site", 2), ["z"], R), R) == [(["z"],)]
    assert _sols(lm, ("phrase", ("site", 1), ["z"])) == []


def test_seam_multi_goal_whole_body_braces_threads_the_state(lm):
    X, Y, R = Var(), Var(), Var()
    assert _sols(lm, ("phrase", ("sboth", X, Y), []), X, Y) == [(1, 2)]
    assert _sols(lm, ("phrase", ("sboth", X, Y), ["z"])) == []
    assert _sols(lm, ("phrase", ("sboth", X, Y), ["z"], R), R) == [(["z"],)]


def test_seam_whole_body_negation_threads_the_state(lm):
    """ISO DCG: ``\\+ B`` is ``\\+ phrase(B, S0, _), S0 = S`` -- consumes
    nothing.  (Scryer's library(dcgs) refuses ``\\+`` in a grammar body:
    representation_error(dcg_body).)  It accepted ``[z]``."""
    R = Var()
    assert _sols(lm, ("phrase", "snot", [])) == [()]
    assert _sols(lm, ("phrase", "snot", ["z"])) == []
    assert _sols(lm, ("phrase", "snot", ["z"], R), R) == [(["z"],)]


def test_pl_rules_with_braces(plm):
    X, R = Var(), Var()
    assert len(_sols(plm, ("phrase", "a", ["x"]))) == 1
    assert _sols(plm, ("phrase", ("b", X), [2]), X) == [(2,)]
    L = Var()
    assert _sols(plm, ("phrase", ("b", X), L), X, L) == [
        (1, [1]), (2, [2]), (3, [3])]
    assert _sols(plm, ("phrase", "c", ["x"])) == []
    assert _sols(plm, ("phrase", ("e", X), []), X) == [(5,)]
    assert _sols(plm, ("phrase", ("e", X), ["a"])) == []
    assert _sols(plm, ("phrase", ("e", X), ["a"], R), R) == [(["a"],)]


def test_pl_phrase_over_braces(plm):
    X = Var()
    assert _sols(plm, ("phrase", br(("member", X, [1, 2])), []), X) == [
        (1,), (2,)]
