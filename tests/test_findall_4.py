"""findall/4 (Scryer, SWI): findall/3 whose list ends in Tail.  It did not
exist (existence_error(procedure, findall/4))."""
import pytest

from clausal.logic.database import Module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var


def test_findall_4_from_python():
    m = Module("f4a")
    X, L = Var(), Var()
    assert [_deref_walk(L) for _ in solve(
        ("findall", X, ("member", X, ["a", "b"]), L, ["c"]), m)] == [["a", "b", "c"]]
    X, L = Var(), Var()
    assert [_deref_walk(L) for _ in solve(("findall", X, "fail", L, ["c"]), m)] \
        == [["c"]]
    with pytest.raises(LogicException):
        list(solve(("findall", Var(), Var(), Var(), []), m))


def test_findall_4_from_a_clause_body(tmp_path):
    from clausal.import_hook import _load_module
    p = tmp_path / "f4b.clausal"
    p.write_text("-private([a, b, c])\np(a),\np(b),\n"
                 "q(L) <- findall(X, p(X), L, [c])\n"
                 "r(L, T) <- findall(X, p(X), L, T)\n")
    m = _load_module("f4b", str(p))
    L = Var()
    assert [_deref_walk(L) for _ in solve(("q", L), m)] == [["a", "b", "c"]]
    L = Var()
    assert [_deref_walk(L) for _ in solve(("r", L, []), m)] == [["a", "b"]]
