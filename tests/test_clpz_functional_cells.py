"""rem/2, sign/1 and the bitwise functors over unbound operands in a
CLP(FD) post.

They have no operator node, so a non-ground cell reached the post as a plain
compound: ``X in -5..5, X rem 3 #= 1, label([X])`` had NO answers (Scryer:
1, 4), and likewise sign/1, /\\, xor/2, <<.  Each is now lifted into a
FunctionalConstraint.  Every answer is Scryer's clpz for the same goal
(2026-09-30)."""
from __future__ import annotations

import importlib
import shutil
import sys

from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var

PL = """\
:- use_module(library(clpz)).
q1(L) :- findall(X, (X in -5..5, X rem 3 #= 1, label([X])), L).
q3(L) :- findall(X, (X in -2..2, sign(X) #= -1, label([X])), L).
q4(L) :- findall(X, (X in 0..7, X /\\ 3 #= 1, label([X])), L).
q8(L) :- findall(X-Y, (X in 0..3, Y in 0..3, xor(X, Y) #= 3, label([X,Y])), L).
q9(L) :- findall(X, (X in -3..3, B #<==> (X rem 2 #= 0), B = 1, label([X])), L).
q10(L) :- findall(X, (X in 0..4, 1 << X #= 8, label([X])), L).
q11(L) :- findall(X, (X in 0..7, X \\/ 1 #= 5, label([X])), L).
q12(L) :- findall(X-Y, (X in -3..3, Y in -1..1, X rem Y #= 0, X #= 2, label([Y])), L).
"""

WANT = {
    "q1": [1, 4], "q3": [-2, -1], "q4": [1, 5],
    "q8": [("-", 0, 3), ("-", 1, 2), ("-", 2, 1), ("-", 3, 0)],
    "q9": [-2, 0, 2], "q10": [3], "q11": [4, 5],
    "q12": [("-", 2, -1), ("-", 2, 1)],
}


def test_native_pl(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "_clpz_fn_cells.pl").write_text(PL)
    sys.modules.pop("_clpz_fn_cells", None)
    importlib.invalidate_caches()
    try:
        m = importlib.import_module("_clpz_fn_cells")
        for name, want in WANT.items():
            v = Var()
            assert [_deref_walk(v) for _ in solve((name, v), m)] == [want], name
    finally:
        sys.modules.pop("_clpz_fn_cells", None)
        shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)
