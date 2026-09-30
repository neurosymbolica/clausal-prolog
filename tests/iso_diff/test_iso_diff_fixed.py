"""Rows the differential sweep (test_iso_diff.py) found wrong and that are
now fixed, pinned WITHOUT the Scryer binary: the expected lines are Scryer's
answers (error contexts blanked, as prelude.pl prints them).  Each failed
silently before the fix."""
from __future__ import annotations

import os
import subprocess
import sys

from test_iso_diff import _CLAUSAL, _rows, HERE, ROOT

CASES = """
t(r01, X, succ(-1, X)).
t(r02, X, succ(a, X)).
t(r03, X-Y, succ(X, Y)).
t(r04, X, succ(1.0, X)).
t(r05, X, succ(X, -1)).
t(r06, X, succ(X, a)).
t(r07, X, succ(X, 0)).
t(r08, X, succ(X, 4)).
t(r09, X, numlist(a, 3, X)).
t(r10, X, numlist(1, b, X)).
t(r11, x, compare(foo, a, b)).
t(r12, x, compare(1, a, b)).
t(r13, R, compare(R, a, b)).
t(r14, x, compare(<, a, b)).
t(r15, x, compare([], a, b)).
"""

WANT = {
    "r01": "ex(error(domain_error(not_less_than_zero,-1),ctx))",
    "r02": "ex(error(type_error(integer,a),ctx))",
    "r03": "ex(error(instantiation_error,ctx))",
    "r04": "ex(error(type_error(integer,1.0),ctx))",
    "r05": "ex(error(domain_error(not_less_than_zero,-1),ctx))",
    "r06": "ex(error(type_error(integer,a),ctx))",
    "r07": "[]",
    "r08": "[3]",
    "r09": "ex(error(type_error(integer,a),ctx))",
    "r10": "ex(error(type_error(integer,b),ctx))",
    "r11": "ex(error(domain_error(order,foo),ctx))",
    "r12": "ex(error(type_error(atom,1),ctx))",
    "r13": "[<]",
    "r14": "[x]",
    "r15": "ex(error(domain_error(order,[]),ctx))",
}


def test_fixed_rows(tmp_path):
    with open(os.path.join(HERE, "prelude.pl"), encoding="utf-8") as f:
        src = f.read() + CASES
    name = "isodiff_fixed"
    (tmp_path / (name + ".pl")).write_text(src, encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=ROOT, CLAUSAL_ROOT=ROOT,
               CLAUSAL_PL_FRONTEND="native")
    c = subprocess.run([sys.executable, "-W", "ignore", "-c", _CLAUSAL,
                        str(tmp_path), name],
                       cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=300)
    got = _rows(c.stdout)
    assert len(got) == len(WANT), c.stderr[-3000:]
    assert got == WANT
