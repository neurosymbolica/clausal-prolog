"""abs/1, min/2 and max/2 over unbound operands in a CLP(FD) post.

``X in -3..3, abs(X) #= 2, label([X])`` gave NO answers (the non-ground
``abs(X)`` cell was compared with 2 as a plain compound), and ``Y #= abs(X)``
raised domain_error(clpz_expression, abs(_)).  Every expected answer below
is Scryer's clpz for the same goal (2026-09-30)."""
from __future__ import annotations

import importlib
import shutil
import sys

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from tests._suffix import SEAM

SEAM_ROWS = [
    ("findall(X, (in_domain(X, -3, 3), abs(X) == 2, label([X])), L)", [-2, 2]),
    ("findall(X, (in_domain(X, -3, 3), 2 == abs(X), label([X])), L)", [-2, 2]),
    ("findall(Y, (in_domain(X, -3, 3), Y == abs(X), label([X])), L)",
     [3, 2, 1, 0, 1, 2, 3]),
    ("findall(X, (abs(X) == 2, label([X])), L)", [-2, 2]),
    ("findall(X, (in_domain(X, -3, 3), abs(X - 1) == 2, label([X])), L)", [-1, 3]),
    ("findall(X, (in_domain(X, -3, 3), abs(X) != 2, label([X])), L)",
     [-3, -1, 0, 1, 3]),
    ("findall(X, (in_domain(X, -3, 3), abs(X) < 2, label([X])), L)", [-1, 0, 1]),
    ("findall(X, (in_domain(X, -3, 3), abs(abs(X) - 2) == 1, label([X])), L)",
     [-3, -1, 1, 3]),
    ("findall([X, Y], (in_domain(X, 0, 3), in_domain(Y, 0, 3), max(X, Y) == 1,"
     " label([X, Y])), L)", [[0, 1], [1, 0], [1, 1]]),
    ("findall([X, Y], (in_domain(X, 0, 3), in_domain(Y, 0, 3), min(X, Y) == 2,"
     " label([X, Y])), L)", [[2, 2], [2, 3], [3, 2]]),
    ("findall(Z, (Z == min(X, Y) + max(X, Y), X == 1, Y == 3), L)", [4]),
    ("findall(X, X == abs(-4), L)", [4]),
    # if_/3 over an abs/1 cell with X unbound: undetermined, so both
    # branches (it took only the else branch, X = 1 and X = -1 included)
    ("findall([X, B], (in_domain(X, -2, 2), if_(abs(X) == 1, B is 1, B is 0),"
     " label([X])), L)", [[-1, 1], [1, 1], [-2, 0], [0, 0], [2, 0]]),
    ("findall([X, B], (in_domain(X, 0, 2), if_(max(X, 1) == 1, B is 1, B is 0),"
     " label([X])), L)", [[0, 1], [1, 1], [2, 0]]),
    ("findall([X, B], (in_domain(X, -1, 1), if_(min(X, 0) == -1, B is 1, B is 0),"
     " label([X])), L)", [[-1, 1], [0, 0], [1, 0]]),
    ("findall([X, B], (in_domain(X, -2, 2), if_(abs(X) + 1 == 2, B is 1, B is 0),"
     " label([X])), L)", [[-1, 1], [1, 1], [-2, 0], [0, 0], [2, 0]]),
]


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("clpz_abs")
    src = "-allow_singletons\n" + "".join(
        f"g{i}(L) <- ({body}),\n" for i, (body, _) in enumerate(SEAM_ROWS))
    p = d / f"_clpz_abs_min_max{SEAM}"
    p.write_text(src)
    return _load_module("_clpz_abs_min_max", str(p))


@pytest.mark.parametrize("i", range(len(SEAM_ROWS)), ids=[b for b, _ in SEAM_ROWS])
def test_seam(mod, i):
    v = Var()
    got = [_deref_walk(v) for _ in solve((f"g{i}", v), mod)]
    assert got == [SEAM_ROWS[i][1]]


PL = """\
:- use_module(library(clpz)).
t1(L) :- findall(X, (X in -3..3, abs(X) #= 2, label([X])), L).
t2(L) :- findall(X-Y, (X in 0..3, Y in 0..3, max(X,Y) #= 1, label([X,Y])), L).
t3(L) :- findall(X, (X in -3..3, abs(abs(X)-2) #= 1, label([X])), L).
t4(L) :- findall(Y, (X in -3..3, Y #= abs(X), label([X])), L).
"""


def test_native_pl(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "_clpz_abs_pl.pl").write_text(PL)
    sys.modules.pop("_clpz_abs_pl", None)
    importlib.invalidate_caches()
    try:
        m = importlib.import_module("_clpz_abs_pl")
        assert m.__loader__.l3_stats["lowered"] == 5

        def ans(name):
            v = Var()
            return [_deref_walk(v) for _ in solve((name, v), m)]

        assert ans("t1") == [[-2, 2]]
        assert ans("t2") == [[("-", 0, 1), ("-", 1, 0), ("-", 1, 1)]]
        assert ans("t3") == [[-3, -1, 1, 3]]
        assert ans("t4") == [[3, 2, 1, 0, 1, 2, 3]]
    finally:
        sys.modules.pop("_clpz_abs_pl", None)
        shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)


REIFIED_PL = """\
:- use_module(library(clpz)).
r3(L) :- findall(X-B, (X in -2..2, B #<==> (abs(X) #= 1), label([X,B])), L).
r5(L) :- findall(X-Y-B, (X in 0..2, Y in 0..2, B #<==> (max(X,Y) #= 1), label([X,Y,B])), L).
r6(L) :- findall(X-B, (X in -2..2, B #<==> (abs(X) + 1 #> 2), label([X,B])), L).
r7(L) :- findall(X-B, (X in -2..2, B #<==> (min(X, 0) #= -1), label([X,B])), L).
r8(E) :- catch(B #<==> (abs(X // Y) #= 1), error(E, _), true).
"""


def test_native_pl_reified(tmp_path, monkeypatch):
    """abs/min/max inside a reified comparison: they were refused
    (domain_error "not supported in a reified comparison"); Scryer's
    answers."""
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "_clpz_abs_reif.pl").write_text(REIFIED_PL)
    sys.modules.pop("_clpz_abs_reif", None)
    importlib.invalidate_caches()
    try:
        m = importlib.import_module("_clpz_abs_reif")

        def ans(name):
            v = Var()
            return [_deref_walk(v) for _ in solve((name, v), m)]

        p = lambda a, b: ("-", a, b)  # noqa: E731
        assert ans("r3") == [[p(-2, 0), p(-1, 1), p(0, 0), p(1, 1), p(2, 0)]]
        assert ans("r5") == [[p(p(0, 0), 0), p(p(0, 1), 1), p(p(0, 2), 0),
                              p(p(1, 0), 1), p(p(1, 1), 1), p(p(1, 2), 0),
                              p(p(2, 0), 0), p(p(2, 1), 0), p(p(2, 2), 0)]]
        assert ans("r6") == [[p(-2, 1), p(-1, 0), p(0, 0), p(1, 0), p(2, 1)]]
        assert ans("r7") == [[p(-2, 0), p(-1, 1), p(0, 0), p(1, 0), p(2, 0)]]
        # posted outside the reification, X // Y would prune Y = 0 for good
        # where the comparison is merely false: refused, as before
        (e,) = ans("r8")
        assert e[0] == "domain_error" and e[1] == "clpz_expression"
    finally:
        sys.modules.pop("_clpz_abs_reif", None)
        shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)
