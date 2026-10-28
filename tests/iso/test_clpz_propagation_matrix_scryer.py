"""CLP(Z) propagation in every direction, for every operator, against
Scryer's clpz.

A generated matrix (``_clpz_matrix.py``; seeded, so the same rows every
run): each binary operator (``+ - * // div mod rem ^ min max``) and the
unary ``abs`` and ``-``, under each relation (``#= #\\= #< #=< #> #>=``),
with the expression on either side; domains on the variables (negative,
zero, holes, ``inf``/``sup``, bignums near 2^70); each variable bound or
narrowed BEFORE or AFTER the post, in every order; nested pairs of
operators; reification (``#<==>``, ``#==>``, ``#\\/`` with B bound early
and late); and hand-picked edges (division by zero, ``0^-1``, the
``R*T #= 14, T = 7`` late binding).  Each row runs the same ISO text in
both engines and compares success, failure or the error term, and every
variable's ``fd_dom/2``.

A row passes when Clausal's answer is Scryer's, or NARROWER than Scryer's
and still sound: Scryer labels each case whose domains are finite and small
(the whole solution set), and each narrower row is checked against every
solution -- for an unbounded case, against every solution with the
variables in a window around 0.  Weaker propagation, a different error,
or a narrowing that loses a solution fails the row.

``CLAUSAL_CLPZ_MATRIX_SCALE=4`` (or more) runs a larger matrix; the
default (2036 rows) takes about a minute.  Operator ruling 2026-10-24 (a
non-conformity is a bug); found and fixed 2026-10-28.
"""
from __future__ import annotations

import os
import re

import pytest

from tests._oracles import SCRYER, run_scryer
from tests.iso import _clpz_matrix as M

SCALE = int(os.environ.get("CLAUSAL_CLPZ_MATRIX_SCALE", "1"))
CASES = M.generate(SCALE)

#: Rows still WEAKER than Scryer (an open defect each): case text -> why.
KNOWN_WEAKER: dict = {}


@pytest.fixture(scope="module")
def matrix(tmp_path_factory):
    if not os.path.exists(SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}")
    d = tmp_path_factory.mktemp("clpz_matrix")
    sc, truth = M.run_scryer_matrix(CASES, str(d / "m_s.pl"), run_scryer)
    cl = M.run_clausal_matrix(CASES, str(d / "m_c.pl"))
    # the narrower rows Scryer could not label: check them in a window
    pending = []
    for c in CASES:
        s, k = M.parse_answer(sc.get(c.index, "raw|missing")), M.parse_answer(cl[c.index])
        t = M.parse_truth(truth.get(c.index, "big"))
        if t is None and M.classify(k, s, t) in ("stronger", "fail_vs_ok"):
            pending.append(c.index)
    window = M.window_truth(CASES, pending, str(d / "m_w.pl"), run_scryer)
    return sc, truth, window, cl


def _id(c):
    return f"{c.id}-" + re.sub(r"[^A-Za-z0-9]+", "_", c.family).strip("_")


@pytest.mark.parametrize("case", CASES, ids=[_id(c) for c in CASES])
def test_row(matrix, case):
    sc, truth, window, cl = matrix
    s_text = sc.get(case.index)
    assert s_text is not None, f"Scryer gave no answer for {case.text}"
    k_text = cl[case.index]
    s, k = M.parse_answer(s_text), M.parse_answer(k_text)
    t = M.parse_truth(truth.get(case.index, "big"))
    cls = M.classify(k, s, t, k_text, s_text)
    if cls in ("stronger", "fail_vs_ok") and t is None:
        w = M.parse_truth(window.get(case.index, "err"))
        assert w is not None, f"no window solutions for {case.text}"
        cls = M.classify(k, s, w)
        if cls == "fail_vs_ok":
            cls = "unsound"
    if case.text in KNOWN_WEAKER:
        pytest.xfail(KNOWN_WEAKER[case.text])
    assert cls in ("agree", "stronger"), (
        f"{cls}: {case.text}\n  clausal: {k_text}\n  scryer:  {s_text}")


def test_matrix_size():
    """The matrix covers what it claims: every operator under every
    relation on both sides, the binding orders, nesting, reification and
    the edges."""
    fams = {c.family.split(":")[0] for c in CASES}
    assert fams == {"op", "bind2", "order", "nested", "reif", "edge"}
    ops = {c.family.split(":")[1] for c in CASES if c.family.startswith("op:")}
    assert ops == set(M.BINARY) | set(M.UNARY)
    rels = {c.family.split(":")[2] for c in CASES if c.family.startswith("op:")}
    assert rels == set(M.RELATIONS)
    assert len(CASES) >= 2000 * SCALE
