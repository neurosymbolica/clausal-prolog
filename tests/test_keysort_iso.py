"""keysort/2 (ISO 8.4.2): it did not exist -- existence_error(procedure,
keysort/2).  Answers are Scryer's (2026-09-30); the one error row where
Scryer FAILS (a non-pair element of Sorted) follows ISO 8.4.2.3, which
names type_error(pair, E) -- ISO first."""
import pytest

from clausal.logic.database import Module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var


@pytest.fixture
def mod():
    return Module("keysort_iso")


def P(k, v):
    return ("-", k, v)


def _answers(mod, pairs):
    S = Var()
    return [_deref_walk(S) for _ in solve(("keysort", pairs, S), mod)]


def test_stable_by_key_duplicates_kept(mod):
    assert _answers(mod, [P("b", 1), P("a", 2), P("b", 0), P("a", 1)]) == [
        [P("a", 2), P("a", 1), P("b", 1), P("b", 0)]]


def test_empty(mod):
    assert _answers(mod, []) == [[]]


def test_standard_order_float_before_int(mod):
    assert _answers(mod, [P(2, "a"), P(1.0, "b"), P(1, "c")]) == [
        [P(1.0, "b"), P(1, "c"), P(2, "a")]]


def test_check_mode(mod):
    assert len(list(solve(("keysort", [P("b", 1), P("a", 2)],
                           [P("a", 2), P("b", 1)]), mod))) == 1
    assert list(solve(("keysort", [P("b", 1), P("a", 2)],
                       [P("b", 1), P("a", 2)]), mod)) == []


def _formal(mod, pairs, sorted_=None):
    goal = ("keysort", pairs, Var() if sorted_ is None else sorted_)
    with pytest.raises(LogicException) as info:
        list(solve(goal, mod))
    return info.value.term[1]


def test_errors(mod):
    assert _formal(mod, "a") == ("type_error", "list", "a")
    assert _formal(mod, ["a"]) == ("type_error", "pair", "a")
    assert _formal(mod, [Var()]) == "instantiation_error"
    assert _formal(mod, Var()) == "instantiation_error"
    assert _formal(mod, [P("a", 1)], "x") == ("type_error", "list", "x")
    assert _formal(mod, [P("a", 1)], ["x"]) == ("type_error", "pair", "x")
