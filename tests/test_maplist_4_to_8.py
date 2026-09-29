"""maplist/4..8 (Scryer's library(lists) has maplist/2..9).  Only /2 and /3
existed: ``maplist(plus, Xs, Ys, Zs)`` was existence_error(procedure,
maplist/4)."""
from clausal.logic.database import Module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var


def _q(goal, v):
    m = Module("maplist_n")
    return [_deref_walk(v) for _, _ in zip(solve(goal, m), range(5))]


def test_maplist_4_modes():
    Z = Var()
    assert _q(("maplist", "plus", [1, 2], [3, 4], Z), Z) == [[4, 6]]
    Y = Var()
    assert _q(("maplist", "plus", [1, 2], Y, [4, 6]), Y) == [[3, 4]]
    L = Var()
    assert _q(("maplist", "plus", L, [1], [2]), L) == [[1]]
    assert _q(("maplist", "plus", [1], [2], [4]), Var()) == []


def test_maplist_5_to_9_exist_and_run(tmp_path):
    from clausal.import_hook import _load_module
    src = "-allow_singletons\n" + "".join(
        f"ok{n}({', '.join(['_'] * n)}),\n" for n in range(4, 8))
    p = tmp_path / "maplist_n_ok.clausal"
    p.write_text(src)
    m = _load_module("maplist_n_ok", str(p))
    for n_lists in range(4, 8):
        lists = [[1, 2]] * n_lists
        assert len(list(solve(("maplist", f"ok{n_lists}", *lists), m))) == 1, n_lists
