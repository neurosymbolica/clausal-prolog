"""Slice 5's exit test (plan native-iso-reader-step2 §4 Slice 5): 19 clpz and
6 clpq cases whose answers are IDENTICAL to Scryer's.

``s5/s5_clpz_exit.pl`` and ``s5/s5_clpq_exit.pl`` hold one ``case(Name, L)``
row per query, ``L`` the findall/3 of its answers in order.  The same files
are

1. loaded by the NATIVE front end (``__pycache__`` cleared, the loader class
   and non-zero read/lowered counts asserted), each row rendered as Scryer's
   ``writeq/1`` writes it, and compared with :data:`CLPZ` / :data:`CLPQ`;
2. run through Scryer (the oracle test), whose output must equal the same
   tables -- so the tables are Scryer's measured answers, not ours.

THE ORACLE BINARY.  ``/workspace/scryer-prolog-clpq`` (upstream master at
3e2f3ecf plus a commit that adds ``library(clpq)``/``library(clpr)`` only,
Holzbaur's CLP(Q,R) port) -- NOT ``/workspace/scryer-prolog``, whose working
tree carries uncommitted clpz.pl/clpz.rs changes that DROP a constraint:
``[X,Y] ins 0..10, X+Y #= 10, X-Y #= 4, label([X,Y])`` answers seven
solutions there (measured 2026-09-30) and ``[[7,3]]`` here.  The clpq rows
use this build's own ``library(clpq)``.
"""
from __future__ import annotations

import importlib
import os
import re
import shutil
import subprocess
import sys
from fractions import Fraction

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
S5 = os.path.join(HERE, "s5")
SCRYER = "/workspace/scryer-prolog-clpq/target/release/scryer-prolog"
ENV = "CLAUSAL_PL_FRONTEND"

#: Scryer's answers, measured with the oracle binary above.
CLPZ = {
    "c01_ins_label": "[[0,0],[0,1],[1,0],[1,1]]",
    "c02_union_domain": "[1,2,3,5,6,7,9]",
    "c03_linear": "[[7,3]]",
    "c04_label_order": "[[1,1],[1,2],[2,1],[2,2],[3,1],[3,2]]",
    "c05_down": "[4,3,2,1]",
    "c06_ff": "[[1,1],[2,1],[3,1],[1,2],[2,2],[3,2]]",
    "c07_reify_iff": "[[0,0],[1,0],[2,0],[3,0],[4,1],[5,1]]",
    "c08_or": "[1,4]",
    "c09_implies": "[[0,0],[0,1],[0,2],[0,3],[1,0],[1,1],[1,2],[1,3],"
                   "[2,0],[2,1],[2,2],[2,3],[3,0]]",
    "c10_not": "[0,1,3]",
    "c11_reify_and": "[[0,0],[1,0],[2,1],[3,1],[4,0],[5,0],[6,0]]",
    "c12_xor_bisect": "[[0,1],[1,0],[1,2],[2,1]]",
    "c13_reify_in": "[[0,0],[1,0],[2,1],[3,1],[4,1],[5,0],[6,1]]",
    "c14_rimplies": "[[2,2],[2,1],[2,0],[1,2],[0,2],[1,0],[0,0]]",
    "c15_sum": "[[0,1,2],[0,2,1],[1,2,0]]",
    "c16_int_in": "[3,5]",
    "c17_errors": "[domain_error-clpz_expression,domain_error-clpz_expression,"
                  "domain_error-clpz_domain,domain_error-clpz_domain,"
                  "type_error-integer,type_error-list,instantiation_error,"
                  "domain_error-labeling_option,"
                  "domain_error-consistent_labeling_options,"
                  "domain_error-nonrepeating_labeling_options,none,"
                  "type_error-list,"
                  "instantiation_error,instantiation_error,"
                  "instantiation_error,"
                  "domain_error-clpz_reifiable_expression]",
    "c18_label_errors": "[instantiation_error,instantiation_error,"
                        "type_error-list]",
    "c19_bisect_negative": "[[-5,0],[-4,0],[-3,0],[-2,0],[-1,0],[0,0],"
                           "[-5,1],[-4,1],[-3,1],[-2,1],[-1,1],[0,1],"
                           "[-5,2],[-4,2],[-3,2],[-2,2],[-1,2],[0,2]]",
}

CLPQ = {
    "q01_system": "[[7,3]]",
    "q02_rational": "[3 rdiv 2]",
    "q03_bounds": "[2]",
    "q04_exact_decimal": "[3101 rdiv 20]",
    "q05_infeasible": "[]",
    "q06_negation": "[2 rdiv 3]",
}

_ATOM = re.compile(r"[a-z][A-Za-z0-9_]*\Z")


def writeq(t) -> str:
    """The subset of Scryer's writeq/1 these rows need."""
    if type(t) is int:
        return str(t)
    if type(t) is Fraction:
        return f"{t.numerator} rdiv {t.denominator}"
    if type(t) is list:
        return "[" + ",".join(writeq(x) for x in t) + "]"
    if type(t) is str:
        assert _ATOM.match(t), t
        return t
    if type(t) is tuple and len(t) == 3 and t[0] == "-":
        return f"{writeq(t[1])}-{writeq(t[2])}"
    raise AssertionError(f"no rendering for {t!r}")


def _rows(mod):
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref, walk
    n, lst = Var(), Var()
    return {walk(deref(n)): writeq(walk(deref(lst)))
            for _ in call("case", n, lst, module=mod)}


@pytest.fixture
def native_s5(tmp_path, monkeypatch):
    shutil.copytree(S5, tmp_path / "s5")
    monkeypatch.syspath_prepend(str(tmp_path / "s5"))
    monkeypatch.setenv(ENV, "native")
    for n in ("s5_clpz_exit", "s5_clpq_exit"):
        sys.modules.pop(n, None)
    importlib.invalidate_caches()

    def load(name):
        for p in tmp_path.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        from clausal import import_hook as ih
        mod = importlib.import_module(name)
        assert type(mod.__loader__) is ih.NativePrologLoader
        st = mod.__loader__.l3_stats
        assert st["read"] > 0 and st["read"] == st["lowered"], st
        assert st["refused"] == 0, st
        return mod
    yield load
    for n in ("s5_clpz_exit", "s5_clpq_exit"):
        sys.modules.pop(n, None)


def test_clpz_rows_equal_scryers(native_s5):
    rows = _rows(native_s5("s5_clpz_exit"))
    assert len(rows) == len(CLPZ) == 19
    for name, want in CLPZ.items():
        assert rows[name] == want, name


def test_clpq_rows_equal_scryers(native_s5):
    rows = _rows(native_s5("s5_clpq_exit"))
    assert len(rows) == len(CLPQ) == 6
    for name, want in CLPQ.items():
        assert rows[name] == want, name


def _scryer_rows(fname: str) -> dict:
    if not os.path.exists(SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}; set "
                    f"CLAUSAL_ISO_ALLOW_NO_SCRYER=1 to run engine-only")
    goal = ("(case(N, L), write(N), write(' '), writeq(L), nl, fail "
            "; true), halt")
    proc = subprocess.run([SCRYER, os.path.join(S5, fname), "-g", goal],
                          capture_output=True, text=True, timeout=120)
    rows = {}
    for line in proc.stdout.splitlines():
        name, sep, rest = line.partition(" ")
        if sep and re.match(r"[cq]\d\d_", name):
            rows[name] = rest.strip()
    return rows


def test_clpz_table_is_scryers_oracle():
    rows = _scryer_rows("s5_clpz_exit.pl")
    assert rows == CLPZ


def test_clpq_table_is_scryers_oracle():
    rows = _scryer_rows("s5_clpq_exit.pl")
    assert rows == CLPQ
