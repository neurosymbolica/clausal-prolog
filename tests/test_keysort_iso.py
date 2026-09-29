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


def test_from_a_clausal_body_with_source_pairs(tmp_path):
    """A pair written in source (``b - 1``) is a Sub node, not the cell;
    keysort takes both spellings (roborev, High)."""
    from clausal.import_hook import _load_module
    p = tmp_path / "ks_body.clausal"
    p.write_text("-private([a, b, c])\n"
                 "ks(S) <- keysort([b - 1, a - 2, c - 0, a - 1], S)\n"
                 "chk() <- keysort([b - 1, a - 2], [a - 2, b - 1])\n")
    m = _load_module("ks_body", str(p))
    S = Var()
    [got] = [_deref_walk(S) for _ in solve(("ks", S), m)]
    keys = [(e.left, e.right) if hasattr(e, "left") else (e[1], e[2])
            for e in got]
    assert keys == [("a", 2), ("a", 1), ("b", 1), ("c", 0)]
    assert len(list(solve("chk", m))) == 1
