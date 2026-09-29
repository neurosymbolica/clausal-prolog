"""nth0/nth1 (/3, /4), between/3 errors, atom_codes/number_codes range.

Measured against Scryer (library(lists), library(between); 2026-09-30):
- nth0/3, nth1/3, nth0/4, nth1/4 did not exist (existence_error);
- between(1, a, X) and between(_, 3, X) FAILED silently where Scryer raises
  type_error(integer, a) / instantiation_error; a float bound likewise;
- atom_codes(A, [97, -1]) FAILED silently where Scryer raises
  representation_error(character_code).
"""
import pytest

from clausal.logic.database import Module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var


@pytest.fixture
def mod():
    return Module("scryer_lists_between_codes")


def _q(mod, *g):
    vs = [a for a in g if isinstance(a, Var)]
    return [tuple(_deref_walk(v) for v in vs) for _ in solve(g, mod)]


def _err(mod, *g):
    with pytest.raises(LogicException) as info:
        list(solve(g, mod))
    return info.value.term[1]


def test_nth_scryer_rows(mod):
    V = Var
    assert _q(mod, "nth0", 1, ["a", "b", "c"], V()) == [("b",)]
    assert _q(mod, "nth1", 0, ["a"], V()) == []
    assert _q(mod, "nth0", V(), ["a", "b"], V()) == [(0, "a"), (1, "b")]
    assert _q(mod, "nth1", V(), ["a", "b"], "b") == [(2,)]
    assert _q(mod, "nth0", 5, ["a"], V()) == []
    assert _q(mod, "nth0", 1, ["a", "b", "c"], V(), V()) == [("b", ["a", "c"])]
    assert _q(mod, "nth0", V(), ["a", "b", "a"], "a", V()) == [
        (0, ["b", "a"]), (2, ["a", "b"])]
    from clausal.logic.cells import chars
    # [x, y]: a list of char atoms, which the engine presents as the string.
    assert _q(mod, "nth1", 1, V(), "x", ["y"]) == [(chars("xy"),)]
    assert _err(mod, "nth0", "a", ["a"], Var()) == ("type_error", "integer", "a")
    assert _err(mod, "nth0", -1, ["a"], Var()) == (
        "domain_error", "not_less_than_zero", -1)


def test_between_errors(mod):
    assert _q(mod, "between", 1, 3, Var()) == [(1,), (2,), (3,)]
    assert _q(mod, "between", 3, 1, Var()) == []
    assert _err(mod, "between", 1, "a", Var()) == ("type_error", "integer", "a")
    assert _err(mod, "between", Var(), 3, Var()) == "instantiation_error"
    assert _err(mod, "between", 1.0, 3, Var()) == ("type_error", "integer", 1.0)
    assert _err(mod, "between", 1, 3, "a") == ("type_error", "integer", "a")
    assert _err(mod, "between", 1, 3, 2.0) == ("type_error", "integer", 2.0)


def test_code_out_of_range_is_a_representation_error(mod):
    for name in ("atom_codes", "number_codes"):
        assert _err(mod, name, Var(), [97, -1]) == (
            "representation_error", "character_code")
