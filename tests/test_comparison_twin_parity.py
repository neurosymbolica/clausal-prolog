"""The four comparison entries (``fd_eq``, ``fd_ne``, ``fd_lt``, ``fd_le``)
exist TWICE in ``clausal/logic/clpfd.py``: a pure-Python twin, and a C-backed
wrapper defined later that is the one actually loaded when the C propagate
module imports.  On 2026-09-17 a defect lived in the GAP between them (the
twin folded a ground expression tree before comparing, the wrapper did not)
while every test that named ``fd_eq`` exercised the twin and passed.
a downstream checker's question: "has the CHANGE been measured, or the
INTERACTION?"  This file measures the interaction: one matrix, both
implementations, outcomes compared.

The pure-Python twins are loaded in a SUBPROCESS with the C propagate module
blocked (``sys.modules[...] = None`` makes its import raise ImportError, which
is exactly the branch the module takes on a box without the extension).  The
C-backed wrappers run in-process.  A positive control mutates the loaded
wrapper and asserts the matrix SEES it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

_MATRIX = r'''
import sys, json
if sys.argv[1] == "python":
    sys.modules["clausal.logic._clpfd_propagate"] = None
from clausal.logic import clpfd
from decimal import Decimal
from fractions import Fraction
from clausal.logic.variables import Var, Trail
from clausal.terms import Add, Div
from clausal.logic.atoms import mint
assert clpfd._USE_C_PROPAGATE == (sys.argv[1] == "C"), clpfd._USE_C_PROPAGATE
def cases():
    yield "int==int", 3, 3
    yield "int<int", 3, 4
    yield "frac,float eq", Fraction(1, 2), 0.5
    yield "frac,float ne", Fraction(1, 2), 0.9
    yield "dec,int", Decimal("1.5"), 1
    yield "dec,float", Decimal("1.5"), 1.5
    yield "dec,dec scale", Decimal("1.0"), Decimal("1.00")
    yield "tree,float", Div(left=7, right=2), 3.5
    yield "tree(int),int", Add(left=1, right=2), 3
    yield "mixed var", Add(left=Fraction(1, 2), right=Var()), 0.9
    yield "var,str", Var(), "banana"
    yield "str,str", "apple", "banana"
    yield "str,charlist", "ab", [mint("a"), mint("b")]
    yield "var,int", Var(), 3
    yield "bool,int", True, 1
    yield "frac,var", Fraction(1, 2), Var()
    yield "float,var", 0.5, Var()
    yield "dec,var", Decimal("1.5"), Var()
    yield "var,var", Var(), Var()
    yield "atom,int", mint("a"), 1
    yield "none,int", None, 1
def run():
    out = {}
    for entry in ("fd_eq", "fd_ne", "fd_lt", "fd_le"):
        fn = getattr(clpfd, entry)
        for label, l, r in cases():
            try:
                out[f"{entry} {label}"] = f"-> {fn(l, r, Trail())!r}"
            except Exception as ex:
                out[f"{entry} {label}"] = f"RAISES {type(ex).__name__}: {str(ex).splitlines()[0][:60]}"
    return out
if __name__ == "__main__":
    print(json.dumps(run()))
'''


def _matrix(cfg: str) -> dict:
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    proc = subprocess.run([sys.executable, "-c", _MATRIX, cfg], capture_output=True,
                          text=True, env=env, cwd=os.getcwd())
    assert proc.returncode == 0, proc.stderr[-800:]
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def both():
    c, py = _matrix("C"), _matrix("python")
    assert len(c) == 84 and len(py) == 84, (len(c), len(py))   # the extraction is not empty
    return c, py


def test_the_c_config_is_the_loaded_one():
    from clausal.logic import clpfd
    if not clpfd._USE_C_PROPAGATE:
        pytest.skip("C propagate module not built here; the parity check needs both")


def test_c_wrappers_and_python_twins_agree_on_the_whole_matrix(both):
    c, py = both
    diff = {k: (c[k], py.get(k)) for k in c if c[k] != py.get(k)}
    assert diff == {}, "\n".join(f"{k}: C {a} | python {b}" for k, (a, b) in diff.items())


def test_the_defect_of_2026_09_17_is_in_the_matrix(both):
    """The shape that lived in the gap: a ground TREE against a float."""
    c, py = both
    assert c["fd_eq tree,float"] == py["fd_eq tree,float"] == "-> True"


def test_positive_control_the_matrix_sees_a_wrapper_only_divergence(both):
    """Mutate the LOADED (C) wrapper's ground fold the way it was before
    9e30afa9 and the matrix must report the tree case diverging."""
    c, py = both
    import clausal.logic.clpfd as clpfd
    from clausal.logic.variables import Trail
    from clausal.terms import Div
    orig = clpfd._resolve
    clpfd._resolve = lambda x: x          # the pre-fix wrapper: no fold
    try:
        try:
            got = f"-> {clpfd.fd_eq(Div(left=7, right=2), 3.5, Trail())!r}"
        except Exception as ex:
            got = f"RAISES {type(ex).__name__}: {str(ex).splitlines()[0][:60]}"
    finally:
        clpfd._resolve = orig
    assert got != py["fd_eq tree,float"], got
