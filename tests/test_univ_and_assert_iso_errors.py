"""'=..'/2 construction errors and assertz/asserta of a non-callable.

Scryer-verified (2026-09-30):
- ``T =.. []`` FAILED silently (domain_error(non_empty_list, [])), as did an
  unbound or partial List or head (instantiation_error) and a non-list List
  (type_error(list, L)); errors now name (=..)/2, not the internal unpack/2.
- ``assertz(1)`` escaped as a raw Python TypeError; it is
  type_error(callable, 1).
"""
import pytest

from clausal.logic.database import Module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var

UNIV = "=.."


@pytest.fixture
def mod():
    return Module("univ_assert_iso")


def _err(mod, goal):
    with pytest.raises(LogicException) as info:
        list(solve(goal, mod))
    return info.value.term[1], info.value.term[2]


def test_univ_construction_errors(mod):
    ctx = ("/", UNIV, 2)
    assert _err(mod, (UNIV, Var(), [])) == (
        ("domain_error", "non_empty_list", []), ctx)
    assert _err(mod, (UNIV, Var(), "bar")) == (("type_error", "list", "bar"), ctx)
    assert _err(mod, (UNIV, Var(), Var())) == ("instantiation_error", ctx)
    assert _err(mod, (UNIV, Var(), [Var(), 1])) == ("instantiation_error", ctx)
    assert _err(mod, (UNIV, Var(), [1, 2]))[0] == ("type_error", "atom", 1)
    assert _err(mod, (UNIV, Var(), [("f", "a")]))[0] == (
        "type_error", "atomic", ("f", "a"))


def test_univ_still_builds(mod):
    T = Var()
    assert [_deref_walk(T) for _ in solve((UNIV, T, ["foo", 1, 2]), mod)] == [
        ("foo", 1, 2)]


@pytest.mark.parametrize("name", ["assertz", "asserta"])
@pytest.mark.parametrize("clause", [1, 2.5])
def test_assert_of_a_number_is_a_type_error(mod, name, clause):
    formal, ctx = _err(mod, (name, clause))
    assert formal == ("type_error", "callable", clause)
    assert ctx == ("/", name, 1)
