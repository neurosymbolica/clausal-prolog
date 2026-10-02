"""``/`` under the clpz #-family is exact integer division.

``X #= 7/2`` SUCCEEDED binding X to Fraction(7, 2) (the #-builtins shared
infix ``==``'s rational ``/``, ruling Q15).  Scryer's clpz fails it, and
``X #= Y/2, Y = 7`` too; ``X #= 8/2`` is 4.  Infix ``==`` keeps ``/``
rational (pinned here too).  Every #-family answer is Scryer's for the same
goal (2026-09-30)."""
from __future__ import annotations

import importlib
import shutil
import sys
from fractions import Fraction

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from tests._suffix import SEAM

PL = """\
:- use_module(library(clpz)).
t1(L) :- findall(X, X #= 7/2, L).
t2(L) :- findall(X, X #= -7/2, L).
t3(L) :- findall(X, X #= 8/2, L).
t4(L) :- findall(X, X #= 7//2, L).
t5(L) :- findall(X, (X #= Y/2, Y = 7), L).
t6(L) :- findall(X, (X #= Y/2, Y = 8), L).
t7(L) :- findall(Y, (Y in 0..9, 3 #= Y/2, label([Y])), L).
t8(L) :- findall(X-Y, (X in 0..4, Y in 1..2, X #= Y/2, label([X,Y])), L).
t9(L) :- findall(X, (7/2 #\\= X, X = 3), L).
t10(L) :- findall(X, X #= 7/0, L).
t11(L) :- findall(X-Y, (Y in -4..4, X #= 4/Y, label([Y])), L).
t12(L) :- findall(X, (X in 0..10, X/3 #= 2, label([X])), L).
t13(L) :- findall(X, X #= (8/2)/2, L).
t14(L) :- findall(X, (X #=< 9/3, X #>= 9/3), L).
t15(L) :- findall(X, (X #< 7/2, X #> 5/5, label([X])), L).
t16(L) :- findall(X, (X in 0..100, X/3 #= Z, Z in 5..6, label([X])), L).
"""

WANT = {
    "t1": [], "t2": [], "t3": [4], "t4": [3], "t5": [], "t6": [4], "t7": [6],
    "t8": [("-", 1, 2)], "t9": [], "t10": [],
    "t11": [("-", -1, -4), ("-", -2, -2), ("-", -4, -1), ("-", 4, 1),
            ("-", 2, 2), ("-", 1, 4)],
    "t12": [6], "t13": [2], "t14": [3], "t15": [], "t16": [15, 18],
}


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("clpz_div")
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    (d / "clpz_exact_div_pl.pl").write_text(PL)
    sys.modules.pop("clpz_exact_div_pl", None)
    importlib.invalidate_caches()
    try:
        m = importlib.import_module("clpz_exact_div_pl")
        assert type(m.__loader__).__name__ == "NativePrologLoader"
        yield m
    finally:
        sys.modules.pop("clpz_exact_div_pl", None)
        shutil.rmtree(d / "__pycache__", ignore_errors=True)
        mp.undo()


@pytest.mark.parametrize("name", sorted(WANT))
def test_native_pl(pl_mod, name):
    v = Var()
    assert [_deref_walk(v) for _ in solve((name, v), pl_mod)] == [WANT[name]]


SEAM_ROWS = [
    ("findall(X, '#='(X, 7 / 2), L)", []),
    ("findall(X, '#='(X, '/'(7, 2)), L)", []),
    ("findall(X, '#='(X, 8 / 2), L)", [4]),
    ("findall(X, ('#='(X, Y / 2), Y is 7), L)", []),
    ("findall(X, ('#='(X, Y / 2), Y is 8), L)", [4]),
    ("findall(X, '#<'(X, 7 / 2), L)", []),
    # infix == keeps / rational (ruling Q15)
    ("findall(X, X == 7 / 2, L)", [Fraction(7, 2)]),
]


@pytest.fixture(scope="module")
def seam_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("clpz_div_seam")
    src = "-allow_singletons\n" + "".join(
        f"g{i}(L) <- ({b}),\n" for i, (b, _) in enumerate(SEAM_ROWS))
    p = d / f"_clpz_exact_div{SEAM}"
    p.write_text(src)
    return _load_module("_clpz_exact_div", str(p))


@pytest.mark.parametrize("i", range(len(SEAM_ROWS)), ids=[b for b, _ in SEAM_ROWS])
def test_seam(seam_mod, i):
    v = Var()
    assert [_deref_walk(v) for _ in solve((f"g{i}", v), seam_mod)] == [SEAM_ROWS[i][1]]
