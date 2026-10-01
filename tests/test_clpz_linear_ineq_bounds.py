"""clpz inequalities over an arithmetic side narrow bounds and BIND.

``7*R #=< 1000000`` posted a LeConstraint over the TREE ``7*R``; its
propagator narrows only a side that is a bare variable, so R kept inf..sup.
The floor-division idiom ``T #> 0, R*T #=< C*10000, C*10000 - R*T #< T``
left R unbound where Scryer binds R = 142857.  An inequality with an
``+ - *`` / negation side is now linearised (ceil/floor division by the
coefficient) and a product of two unknowns is lifted into a times
propagator, as clpz does.

Every row fails on 81dcd42b.  The expected domains are Scryer's
(/workspace/scryer-prolog-clpq), except the three rows marked TIGHTER:
there Scryer answers a weaker but equally sound bound (``7*R #>= 1000000``
is R in 142857..sup in Scryer, but 7*142857 = 999999).
"""
from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var

PL = """\
:- use_module(library(clpz)).
r(C, T, R) :- T #> 0, R * T #=< C * 10000, C * 10000 - R * T #< T.
w(R, D) :- r(100, 7, R), fd_dom(R, D).
le1(R, D) :- 7*R #=< 1000000, fd_dom(R, D).
lt1(R, D) :- 7*R #< 1000000, fd_dom(R, D).
ge1(R, D) :- 7*R #>= 1000000, fd_dom(R, D).
gt1(R, D) :- 7*R #> 1000000, fd_dom(R, D).
rhs1(R, D) :- 1000000 #>= R*7, fd_dom(R, D).
neg1(R, D) :- -3*R #=< 10, fd_dom(R, D).
neg2(R, D) :- 10 - 3*R #> 0, fd_dom(R, D).
neg3(R, D) :- R*(-3) #< -10, fd_dom(R, D).
tpre(R, D) :- T = 7, R*T #=< 1000000, fd_dom(R, D).
tpost(R, D) :- R*T #=< 1000000, T = 7, fd_dom(R, D).
tpost2(R, D) :- R*T #=< 1000000, 1000000 - R*T #< T, T = 7, fd_dom(R, D).
multi(R, D) :- X = 3, Y = 4, 2*X + 3*Y + 5*R #=< 100, fd_dom(R, D).
multi2(R, D) :- 2*X + 3*Y + 5*R #=< 100, X = 3, Y = 4, fd_dom(R, D).
multi3(R, D) :- X in 0..10, Y in 0..10, 2*X + 3*Y + 5*R #>= 100, fd_dom(R, D).
both(R, D) :- 7*R #=< 1000000, 7*R #>= 999994, fd_dom(R, D).
twoside(R, D) :- 3*R + 1 #=< 2*R + 10, fd_dom(R, D).
fin(R, D) :- R in 0..1000000, 7*R #=< 1000000, fd_dom(R, D).
big1(R, D) :- R * 1000000000000000000000000000000 #=< 10000000000000000000000000000000000000000, fd_dom(R, D).
big2(R, D) :- X in 0..5, 100000000000000000000*X + R #=< 1000000000000000000000, X = 3, fd_dom(R, D).
alias(R, D) :- R + R #=< 7, fd_dom(R, D).
square(R, D) :- R * R #=< 16, fd_dom(R, D).
tneg(R, D) :- R*T #=< 10, T = -2, fd_dom(R, D).
tdom(R, D) :- T in 2..5, R*T #=< 10, R #>= 0, fd_dom(R, D).
gtexp(R, D) :- Y in 0..5, R - 1 #> Y, fd_dom(R, D).
canc0(R, D) :- R - R #< 0, D = ok.
"""

INF, SUP = "inf", "sup"


def _d(lo, hi):
    return ("..", lo, hi)


#: (R, fd_dom(R)) -- R is None when it stays a variable; None for no answer
WANT = {
    "w": (142857, _d(142857, 142857)),
    "le1": (None, _d(INF, 142857)),
    "lt1": (None, _d(INF, 142857)),
    "ge1": (None, _d(142858, SUP)),           # TIGHTER than Scryer's 142857
    "gt1": (None, _d(142858, SUP)),           # TIGHTER than Scryer's 142857
    "rhs1": (None, _d(INF, 142857)),
    "neg1": (None, _d(-3, SUP)),
    "neg2": (None, _d(INF, 3)),
    "neg3": (None, _d(4, SUP)),               # TIGHTER than Scryer's 3
    "tpre": (None, _d(INF, 142857)),
    "tpost": (None, _d(INF, 142857)),
    "tpost2": (142857, _d(142857, 142857)),
    "multi": (None, _d(INF, 16)),
    "multi2": (None, _d(INF, 16)),
    "multi3": (None, _d(10, SUP)),
    "both": (142857, _d(142857, 142857)),
    "twoside": (None, _d(INF, 9)),
    "fin": (None, _d(0, 142857)),
    "big1": (None, _d(INF, 10**10)),
    "big2": (None, _d(INF, 7 * 10**20)),
    "alias": (None, _d(INF, 3)),
    "square": (None, _d(-4, 4)),
    "tneg": (None, _d(-5, SUP)),
    "tdom": (None, _d(0, 5)),
    "gtexp": (None, _d(2, SUP)),
    "canc0": None,                            # R - R < 0 has no solution
}


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("clpz_lin")
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    (d / "clpz_linear_ineq_pl.pl").write_text(PL)
    sys.modules.pop("clpz_linear_ineq_pl", None)
    importlib.invalidate_caches()
    try:
        m = importlib.import_module("clpz_linear_ineq_pl")
        assert type(m.__loader__).__name__ == "NativePrologLoader"
        yield m
    finally:
        sys.modules.pop("clpz_linear_ineq_pl", None)
        shutil.rmtree(d / "__pycache__", ignore_errors=True)
        mp.undo()


def _answers(goal, mod, *vs):
    out = []
    for _ in solve(goal, mod):
        out.append(tuple(_deref_walk(v) for v in vs))
    return out


@pytest.mark.parametrize("name", sorted(WANT))
def test_native_pl(pl_mod, name):
    r, d = Var(), Var()
    got = _answers((name, r, d), pl_mod, r, d)
    want = WANT[name]
    if want is None:
        assert got == []
        return
    assert len(got) == 1
    gr, gd = got[0]
    if want[0] is None:
        assert isinstance(gr, Var), gr
    else:
        assert gr == want[0] and type(gr) is int
    if want[1] is not None:
        assert gd == want[1]


def test_witness_binds_an_integer(pl_mod):
    """The reported idiom: R is BOUND (a scorer int()s it)."""
    r = Var()
    got = _answers(("r", 100, 7, r), pl_mod, r)
    assert got == [(142857,)] and type(got[0][0]) is int


@pytest.mark.parametrize("c,t", [(100, 7), (1, 3), (37, 11), (0, 5), (-5, 3)])
def test_witness_is_floor_division(pl_mod, c, t):
    r = Var()
    assert _answers(("r", c, t, r), pl_mod, r) == [((c * 10000) // t,)]


SEAM = """\
-allow_singletons
r(C, T, R) <- (T > 0, R * T <= C * 10000, C * 10000 - R * T < T),
late(R) <- (R * T <= 1000000, 1000000 - R * T < T, T is 7),
"""


@pytest.fixture(scope="module")
def seam_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("clpz_lin_seam")
    p = d / "_clpz_linear_ineq.clausal"
    p.write_text(SEAM)
    return _load_module("_clpz_linear_ineq", str(p))


def test_seam_bare_comparisons_bind(seam_mod):
    r = Var()
    assert _answers(("r", 100, 7, r), seam_mod, r) == [(142857,)]
    r = Var()
    assert _answers(("late", r), seam_mod, r) == [(142857,)]


def test_python_twin_agrees():
    """The pure-Python propagation path (no C extension) answers the same."""
    code = (
        "import sys\n"
        "sys.modules['clausal.logic._clpfd_propagate'] = None\n"
        "import clausal.logic.clpfd as F\n"
        "assert not F._USE_C_PROPAGATE\n"
        "from clausal.logic.variables import Var\n"
        "from clausal.logic.clpfd import fd_le, fd_lt\n"
        "from clausal.logic.variables import Trail\n"
        "from clausal.terms import Mult, Sub\n"
        "from clausal.logic.solve import _deref_walk\n"
        "t = Trail(); R = Var()\n"
        "assert fd_le(Mult(left=R, right=7), 1000000, t)\n"
        "assert fd_lt(Sub(left=1000000, right=Mult(left=R, right=7)), 7, t)\n"
        "print(_deref_walk(R))\n"
    )
    env = dict(os.environ)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, env=env, timeout=300)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "142857"
