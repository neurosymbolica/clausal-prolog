"""is_dict_t/2 -- the reified twin of is_dict/1.

``is_dict_t(Term, T)``: T = true when Term is a dict (whatever is_dict/1
accepts: a DictTerm or a plain Python dict), T = false for any other nonvar
term, instantiation_error for an unbound Term.  One answer, no choice point.
A T bound to true/false is a test; a T bound to anything else fails, as
dif_t/3 does.  The if_/3 rows (each surface) are in
tests/iso_l3/test_l3_is_dict_t.py.
"""
from __future__ import annotations

import pytest

from clausal.logic.atoms import mint, spelling
from clausal.logic.cells import chars
from clausal.logic.database import Module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import DictTerm, SetTerm


def _truths(term, t=None):
    """Every answer of is_dict_t(term, T), as the bound T (one per answer)."""
    t = Var() if t is None else t
    return [deref(t) for _ in call("is_dict_t", term, t, module=Module("t"))]


# ── T unbound: one answer, true or false ──


@pytest.mark.parametrize("term", [
    DictTerm({"a": 1}),
    DictTerm({}),
    {"a": 1},          # a plain Python dict (is_dict/1 accepts it)
    {},
], ids=["dict", "empty-dict", "plain-dict", "empty-plain-dict"])
def test_a_dict_is_true(term):
    assert _truths(term) == [True]


@pytest.mark.parametrize("term", [
    [1, 2],
    [],                # the engine's [] is the empty list, not a dict
    mint("a"),
    42,
    1.5,
    ("f", 1, 2),
    chars("text"),
    SetTerm([1, 2]),
], ids=["list", "nil", "atom", "integer", "float", "compound", "string",
        "set"])
def test_any_other_nonvar_term_is_false(term):
    assert _truths(term) == [False]


def test_an_unbound_term_is_an_instantiation_error():
    with pytest.raises(LogicException) as info:
        _truths(Var())
    formal, context = info.value.term[1], info.value.term[2]
    assert spelling(formal) == "instantiation_error"
    assert context == ("/", "is_dict_t", 2)


def test_an_unbound_term_throws_even_with_t_bound():
    with pytest.raises(LogicException):
        _truths(Var(), True)


# ── T bound ──


def test_a_bound_truth_value_is_a_test():
    assert _truths(DictTerm({"a": 1}), True) == [True]
    assert _truths(DictTerm({"a": 1}), False) == []
    assert _truths(mint("a"), False) == [False]
    assert _truths(mint("a"), True) == []


@pytest.mark.parametrize("bad", [mint("maybe"), 1, [1]],
                         ids=["atom", "integer", "list"])
def test_a_non_boolean_truth_value_fails_as_dif_t_does(bad):
    assert _truths(DictTerm({"a": 1}), bad) == []
    assert _truths(mint("a"), bad) == []
    # dif_t/3's convention, which is_dict_t/2 follows: no type_error.
    assert list(call("dif_t", 1, 2, bad, module=Module("t"))) == []


# ── determinism ──


def test_no_choice_point_is_left():
    """The builtin's generator is exhausted after its one answer."""
    from clausal.logic.builtins.dict_set import _is_dict_t__2 as fn
    from clausal.logic.variables import Trail
    for term in (DictTerm({}), mint("a")):
        gen = fn(term, Var(), Trail(), None)
        assert next(gen) is None
        with pytest.raises(StopIteration):
            next(gen)


def test_registered_beside_is_dict_and_known_deterministic():
    from clausal.logic.builtins import _BUILTINS
    from clausal.logic.compiler.tro import _DETERMINISTIC_BUILTINS
    assert ("is_dict_t", 2) in _BUILTINS
    assert ("is_dict_t", 2) in _DETERMINISTIC_BUILTINS
