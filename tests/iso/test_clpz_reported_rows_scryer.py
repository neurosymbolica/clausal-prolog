"""Two CLP(Z) defects reported against Scryer, both fixed on 2026-10-28,
pinned as oracle rows (the same ``.pl`` text in the engine and in Scryer)
and with Scryer's answers as constants, so they run without the oracle.

1. SOUNDNESS: the search below has 214 solutions (Scryer); 285bdb8e found
   228, extras such as ``[1,5,0]`` violating the reified conjunct.  The
   old ``min``/``max`` propagator narrowed its operands to domains it had
   computed BEFORE narrowing its result -- and narrowing the result runs
   the other propagators at once, so an operand already narrower than that
   was WIDENED back, and the reified constraint lost its pruning.  Replaced
   by clausal/logic/clpfd_nonlinear.py's propagators, which intersect with
   the current domain before every narrowing (the bare repro: ``min(X1,
   X2) #> X3, <the reified conjunct>, X1 = 1, X2 = 5, X3 = 0`` succeeded
   in that binding order and failed in another).
2. ``//`` propagated forward only: ``X in 0..20, Q #= X//4, Q #>= 3`` left X
   in 0..20 (Scryer: 12..20), ``X//3 #< Y//3`` over 0..8 left both 0..8
   (Scryer: X in 0..5, Y in 3..8).
"""

from __future__ import annotations

import importlib
import sys

import pytest

from .test_iso_answers_scryer import _engine_answers, _scryer_answers

_REIFIED = ("((-2*X3 + X2 #< X1 + -1) #==> (3*X3 #\\= 4)) #==> "
            "((-2*X2 #>= 6) #<==> (-1*X2 #< -4))")
_DOMS = "X1 in 1..24, X2 in (-4)..18, X3 in 0..16"

#: (row name, body binding R, what both print)
ROWS = [
    ("soundness: 214 solutions",
     "findall([X1,X2,X3], (" + _DOMS + ", ( min(X3,X1) #> X3, "
     "2*X1 + 3*X2 + -2*X3 #>= 3*X2 + 2*X1 ; min(X1,X2) #> X3, "
     "all_distinct([X1,X3,X2]) ), X1 #\\= 3, " + _REIFIED
     + ", label([X1,X2,X3]) ), L), sort(L, S), length(S, R)", ["214"]),
] + [
    (f"soundness: [1,5,0] is no solution ({order})",
     "( " + _DOMS + ", min(X1,X2) #> X3, " + _REIFIED + ", " + order
     + " -> R = yes ; R = no )", ["no"])
    for order in ("X1 = 1, X2 = 5, X3 = 0", "X3 = 0, X1 = 1, X2 = 5",
                  "X2 = 5, X1 = 1, X3 = 0")
] + [
    # (fd_dom's 12..20, as [Inf, Sup] and the size: the answer printer
    # here has no clpz operators)
    ("// backward",
     "X in 0..20, Q #= X//4, Q #>= 3, fd_inf(X, L), fd_sup(X, H), "
     "fd_size(X, N), R = [L, H, N]", ["[12,20,9]"]),
    ("// on both sides",
     "X in 0..8, Y in 0..8, X//3 #< Y//3, fd_inf(X, XL), fd_sup(X, XH), "
     "fd_size(X, XN), fd_inf(Y, YL), fd_sup(Y, YH), fd_size(Y, YN), "
     "R = [XL, XH, XN, YL, YH, YN]", ["[0,5,6,3,8,6]"]),
]

PROGRAM = (":- use_module(library(clpz)).\n:- use_module(library(lists)).\n"
           + "".join(f"r{i}(R) :- {body}.\n"
                     for i, (_, body, _) in enumerate(ROWS)))


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("clpz_reported")
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    name = "_clpz_reported_1028"
    (d / f"{name}.pl").write_text(PROGRAM)
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    try:
        yield importlib.import_module(name)
    finally:
        sys.modules.pop(name, None)
        mp.undo()


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_engine(pl_mod, i):
    assert _engine_answers(pl_mod, f"r{i}", 5) == ROWS[i][2]


def test_oracle(scryer):
    del scryer   # the fixture only asserts the binary is there
    got = _scryer_answers(PROGRAM, [(f"r{i}(R)", 5) for i in range(len(ROWS))])
    assert got == [r[2] for r in ROWS]
