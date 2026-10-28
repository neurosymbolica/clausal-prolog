"""CLP(Z) propagation through the non-linear operators, late binding and
linear disequalities: Scryer's answers, pinned without the oracle.

Each row is a body over the listed variables, run on the ISO surface
(``.pl`` with ``library(clpz)``); the answer is ``fail`` or each variable's
``fd_dom/2`` (an integer once bound).  Every row was weaker in Clausal
than in Scryer before 2026-10-28 (``R*T #= 14, T = 7`` left R unbound:
todo/done/clpz-nonlinear-eq-late-binding-does-not-narrow-2026-10-01.md);
the expected answer is Scryer's, or -- rows marked NARROWER -- a sound
answer narrower than Scryer's (checked by hand against the solutions).
The full matrix against the live oracle is
tests/iso/test_clpz_propagation_matrix_scryer.py.
"""
from __future__ import annotations

import pytest

from tests.iso import _clpz_matrix as M

BIG = 2 ** 70

ROWS = [
    # (vars, body, expected answer text)
    ("R,T", "R*T #= 14, T = 7", "ok|2|7"),
    ("R,T", "T = 7, R*T #= 14", "ok|2|7"),
    ("X,Y,Z", "Z #= (X)*(Y), Y = 3, Z = 6", "ok|2|3|6"),
    ("X,Y,Z", "Z #= (X)*(Y), Y = 5, Z = 1", "fail"),
    ("X,Y,Z", "X * Y #= Z, X in 1..3, Y in 1..3, Z = 5", "fail"),
    ("X,Y,Z", "Y in 4 .. 7, X in 0..5, (X)*(Y) #= Z, Z in 1\\/3\\/5", "ok|1|5|5"),
    ("X,Y,Z", "X in -6.. -2, Z in 0 .. 0, Y in -5..5, (X)*(Y) #\\= Z",
     "ok|-6.. -2|-5.. -1\\/1..5|0"),
    ("X,Y", "X #= Y * Y, X = %d" % (BIG * BIG), "ok|%d|-%d\\/%d" % (BIG * BIG, BIG, BIG)),
    ("X,Y", "X * X #= Y, Y in 2..3", "fail"),
    ("X,Y", "X #= Y ^ 2, X = 49", "ok|49|-7\\/7"),
    ("X,Y", "X #= Y ^ 2, X in 50..60", "fail"),
    ("X,Y", "X #= 2 ^ Y, X = %d" % BIG, "ok|%d|70" % BIG),
    ("X,Y,Z", "Z #= (X)^(Y), X = 0, Z = 3", "fail"),
    ("X,Y,Z", "Z #= (X)^(Y), X = 0, Z = 1", "ok|0|0|1"),
    ("X,Y,Z", "Z #= (X)^(Y), X = 1, Z = 2", "fail"),
    ("X,Y", "X #= Y mod 3", "ok|0..2|inf..sup"),
    ("X,Y", "X #= Y rem -3", "ok|-2..2|inf..sup"),
    ("X,Y", "X #= Y // 3, X = 2", "ok|2|6..8"),
    # NARROWER: Scryer -8.. -4, but -8 div 3 is -3
    ("X,Y", "X #= Y div 3, X = -2", "ok|-2|-6.. -4"),
    ("X,Y", "Y in -1..1, X #= 7 // Y", "ok|-7\\/7|-1\\/1"),
    ("X,Y,Z", "Z #= (X)//(Y), X = 5, Z = 3", "fail"),
    ("X,Y,Z", "Z #= (X)//(Y), Y = -1, Z = 7", "ok|-7|-1|7"),
    ("X,Y,Z", "Z #= (X)//(Y), X = -1, Z = 0", "ok|-1|inf.. -2\\/2..sup|0"),
    ("X,Y,Z", "Z = 5, Y = 2, Z #\\= (X)//(Y)", "ok|inf..9\\/12..sup|2|5"),
    ("X,Y,Z", "Z #= (X) mod (Y), X = 3, Z = -1", "ok|3|-4\\/ -2|-1"),
    ("X,Y,Z", "Z #= (X) rem (Y), X = 3, Z = 1", "ok|3|-2\\/2|1"),
    ("X,Y,Z", "Z #= (X) rem (Y), X = 7, Z = -2", "fail"),
    ("X,Y", "X #= max(Y, 3), X = 5", "ok|5|5"),
    ("X,Y,Z", "Z #= max(X,Y), X = 0, Z = 2", "ok|0|2|2"),
    ("X,Y,Z", "Y in inf..0, X in 1..4, Z = -2, Z #> min(X,Y)",
     "ok|1..4|inf.. -3|-2"),
    ("X,Y", "X in 0..100, X // 2 #=< 3", "ok|0..7|inf..sup"),
    # linear: holes kept, late binding of a disequality
    ("X,Y,Z", "X #> 1, Y in 1\\/3\\/5, Z in 0..5, X in -5..5, (X)-(Y) #= Z, Z = 0",
     "ok|3\\/5|3\\/5|0"),
    ("X,Y", "X in 1..5, X #\\= Y + 1, Y = 2", "ok|1..2\\/4..5|2"),
    ("X,Y", "Y in 1..5, X #\\= Y + 1, X = 3", "ok|3|1\\/3..5"),
    ("X,Z", "Z #\\= -(X), Z = 4", "ok|inf.. -5\\/ -3..sup|4"),
    # a coefficient beyond int64
    ("X,Y,Z", "Z in -4.. -1\\/2..4, Y = -%d, Z #= (X)*(Y), Z #\\= -3" % BIG, "fail"),
    # reified, a total non-linear operator: B decided by X's domain
    ("B,X,Y", "X in -6.. -2, Y in 0..sup, B #==> (X #> (Y) mod (2))",
     "ok|0|-6.. -2|0..sup"),
]


@pytest.fixture(scope="module")
def answers(tmp_path_factory):
    cases = []
    for vs, body, _want in ROWS:
        cases.append(M.Case("pin", vs.split(","), [body]))
    for i, c in enumerate(cases):
        c.index = i
    d = tmp_path_factory.mktemp("clpz_nonlinear")
    return M.run_clausal_matrix(cases, str(d / "pins.pl"), "_clpz_nonlinear_pins")


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[1] for r in ROWS])
def test_row(answers, i):
    vs, body, want = ROWS[i]
    got = answers[i]
    assert M.parse_answer(got) == M.parse_answer(want), (body, got)
