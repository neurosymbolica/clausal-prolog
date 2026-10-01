"""``phrase(!, L)`` / ``phrase(!, L, R)``: a cut that is the WHOLE grammar
body is local to phrase and cuts nothing, as ``call(!)`` does.

ISO 7.14.2 translates ``!`` as ``!, S0 = S``, and phrase/3 calls that
translation, so the cut is the first goal inside the call's barrier and
cuts nothing: the goal is ``S0 = S``.  It used to be looked up as the
nonterminal ``!//0`` and raised ``existence_error(procedure, !/2)``.

Scryer (measured)::

    phrase(!, [])        -> true
    phrase(!, [a])       -> false
    phrase(!, [a], R)    -> R = [a]
    phrase(!, S0, S)     -> S0 = S

A cut INSIDE a larger body (``phrase((a, !), L)``) stays refused:
tests/test_meta_call_cut_refused.py.
"""
from __future__ import annotations

import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call as pcall
from clausal.logic.variables import Var, deref, walk


@pytest.fixture
def lm(tmp_path):
    path = tmp_path / "phrasecut.clausal"
    path.write_text(textwrap.dedent("""
        a(S, S),
        cg1(G) <- call(G),
    """).lstrip())
    return _load_module("phrasecut", str(path)).__dict__["$module"]


def _answers(lm, goal, *outs):
    return [tuple(walk(deref(o)) for o in outs)
            for _ in pcall("cg1", goal, module=lm)]


def test_phrase_2_cut_succeeds_on_the_empty_list(lm):
    assert _answers(lm, ("phrase", "!", [])) == [()]


def test_phrase_2_cut_fails_on_a_nonempty_list(lm):
    assert _answers(lm, ("phrase", "!", ["a"])) == []


def test_phrase_2_cut_binds_an_unbound_list_to_the_empty_list(lm):
    L = Var()
    assert _answers(lm, ("phrase", "!", L), L) == [([],)]


def test_phrase_3_cut_leaves_the_input_as_the_rest(lm):
    R = Var()
    assert _answers(lm, ("phrase", "!", ["a"], R), R) == [(["a"],)]


def test_phrase_3_cut_unifies_the_two_states(lm):
    S0, S = Var(), Var()
    same = [deref(S0) is deref(S)
            for _ in pcall("cg1", ("phrase", "!", S0, S), module=lm)]
    assert same == [True]


def test_phrase_cut_on_text(lm):
    from clausal.logic.cells import chars
    assert len(list(pcall("cg1", ("phrase", "!", chars("")), module=lm))) == 1
    assert list(pcall("cg1", ("phrase", "!", chars("a")), module=lm)) == []


def test_a_cut_inside_a_larger_body_is_still_refused(lm):
    with pytest.raises(LogicException) as ei:
        list(pcall("cg1", ("phrase", (",", "a", "!"), []), module=lm))
    assert ei.value.term[1] == ("existence_error", "procedure",
                                ("/", "!", 0))
