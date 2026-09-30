"""Slice 4's exit test (plan native-iso-reader-step2 §4 Slice 4): the
meta-predicates, all-solutions, library(reif), dif and the transition
constructs, on the native ``.pl`` front end.

``s4/s4_exit.pl`` holds one ``case(Name, L)`` row per construct, ``L`` the
findall/3 of its answers in order; ``s4/s4_exit_twin.seam`` holds the same
rows as a seam author writes them.  The rows

1. loaded by the NATIVE front end (``__pycache__`` cleared, the loader class
   and non-zero read/lowered counts asserted), rendered as Scryer's
   ``writeq/1`` writes them, equal :data:`SCRYER_ROWS`;
2. from the seam twin equal the native ones, term for term;
3. are Scryer's own (the oracle test runs the same ``.pl`` through
   ``/workspace/scryer-prolog-clpq``; see test_l3_s5_exit.py for why not
   ``/workspace/scryer-prolog``);

and the D13 lint counts exactly the transition-construct sites PLANTED in
the ``.pl`` (:data:`PLANTED`), on the full lowering and on a cache hit.
"""
from __future__ import annotations

import importlib
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
S4 = os.path.join(HERE, "s4")
SCRYER = "/workspace/scryer-prolog-clpq/target/release/scryer-prolog"
ENV = "CLAUSAL_PL_FRONTEND"

#: Scryer's answers, measured with the oracle binary above (2026-09-30).
SCRYER_ROWS = {
    "c01_setof_caret": "[[1,2,3]]",
    "c02_bagof_groups": "[a-[1,2],b-[3]]",
    "c03_findall4": "[[1,2,3]]",
    "c04_forall": "[yes]",
    "c05_forall_fails": "[]",
    "c06_once": "[a]",
    "c07_catch_throw": "[my(err)]",
    "c08_maplist2": "[1-1,1-2,2-1,2-2]",
    "c09_maplist3": "[[2,3]]",
    "c10_maplist4to7": "[[11,22]-[6]-[10]-[15]]",
    "c11_foldl4to6": "[6-11-6]",
    "c12_dif": "[b,c]",
    "c13_naf": "[1,3]",
    "c14_if_eq": "[a-y,b-n]",
    "c15_if_dif": "[a-n,b-y]",
    "c16_if_and": "[a-b-y,a-d-n,c-b-n,c-d-n]",
    "c17_if_or": "[a-b-y,a-d-y,c-b-y,c-d-n]",
    "c18_if_closure": "[a-y,c-n]",
    "c19_memberd_t_true": "[ok]",
    "c20_memberd_t_enum": "[a-true,b-true,c-false]",
    "c21_tfilter": "[a-a-[a,a],a-b-[a],b-a-[a],b-b-[]]",
    "c22_tfilter_dif": "[[b,c]]",
    "c23_tpartition": "[[a,a]-[b,c]]",
    "c24_tmember": "[ok]",
    "c25_tmember_t": "[true,false]",
    "c26_cond_t": "[a-true,b-false]",
    "c27_eq3_dif3_order": "[true-false,true-true,false-false,false-true]",
    "c28_if_errors": "[instantiation_error,type_error(boolean,foo)]",
    "c29_truth_data": "[true,false]",
    "c30_user_true_n": "[1-1-2]",
    "c31_memberchk": "[a]",
    "c32_findall_backdoor": "[1]",
    "c33_naf_as_data": "[ok]",
}

#: The transition-construct sites written in s4_exit.pl, by lint key: one
#: ``\\+`` (c13; c33's is DATA and is not a site), once/1 in c05 and c06,
#: forall/2 in c04 and c05, memberchk/2 in c31, the findall(_, G, [])
#: backdoor in c32, no make_quantity/3.
PLANTED = {"\\+/1": 1, "once/1": 2, "forall/2": 2, "memberchk/2": 1,
           "findall/3_empty": 1, "make_quantity/3": 0}

_ATOM = re.compile(r"[a-z][A-Za-z0-9_]*\Z")


def writeq(t) -> str:
    """The subset of Scryer's writeq/1 these rows need."""
    if t is True or t is False:
        return "true" if t else "false"
    if type(t) is int:
        return str(t)
    if type(t) is list:
        return "[" + ",".join(writeq(x) for x in t) + "]"
    if type(t) is tuple and len(t) == 2 and t[0] == "$chars":
        return writeq(list(t[1]))
    if type(t) is str:
        assert _ATOM.match(t), t
        return t
    if type(t) is tuple and len(t) == 3 and t[0] == "-":
        right = writeq(t[2])
        if type(t[2]) is tuple and len(t[2]) == 3 and t[2][0] == "-":
            right = f"({right})"
        return f"{writeq(t[1])}-{right}"
    if type(t) is tuple and t and type(t[0]) is str:
        return f"{t[0]}(" + ",".join(writeq(a) for a in t[1:]) + ")"
    raise AssertionError(f"no rendering for {t!r}")


def _rows(mod) -> dict:
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref, walk
    n, lst = Var(), Var()
    return {walk(deref(n)): walk(deref(lst))
            for _ in call("case", n, lst, module=mod)}


@pytest.fixture
def s4(tmp_path, monkeypatch):
    shutil.copytree(S4, tmp_path / "s4")
    monkeypatch.syspath_prepend(str(tmp_path / "s4"))
    monkeypatch.setenv(ENV, "native")
    names = ("s4_exit", "s4_exit_twin")
    for n in names:
        sys.modules.pop(n, None)
    importlib.invalidate_caches()

    def load(name, *, clear=True):
        if clear:
            for p in tmp_path.rglob("__pycache__"):
                shutil.rmtree(p, ignore_errors=True)
        sys.modules.pop(name, None)
        return importlib.import_module(name)
    yield load
    for n in names:
        sys.modules.pop(n, None)


def _native(load, *, clear=True):
    from clausal import import_hook as ih
    mod = load("s4_exit", clear=clear)
    assert type(mod.__loader__) is ih.NativePrologLoader
    st = mod.__loader__.l3_stats
    assert st["read"] > 0 and st["read"] == st["lowered"], st
    assert st["refused"] == 0, st
    return mod


def test_native_rows_equal_scryers(s4):
    rows = _rows(_native(s4))
    assert len(rows) == len(SCRYER_ROWS) == 33
    assert {k: writeq(v) for k, v in rows.items()} == SCRYER_ROWS


def test_seam_twin_rows_equal_the_native_ones(s4):
    native = _rows(_native(s4))
    twin_mod = s4("s4_exit_twin")
    assert twin_mod.__file__.endswith(".seam")
    twin = _rows(twin_mod)
    assert len(native) == 33
    assert twin == native


def test_the_lint_counts_the_planted_sites(s4, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="clausal.pl_frontend")
    mod = _native(s4)
    assert mod.__loader__.l3_stats["transition_constructs"] == PLANTED
    lines = [r.getMessage() for r in caplog.records
             if r.name == "clausal.pl_frontend"
             and "transition constructs" in r.getMessage()]
    assert len(lines) == 1, lines
    assert lines[0].endswith(
        "transition constructs: 7 sites (\\+/1: 1, once/1: 2, forall/2: 2, "
        "memberchk/2: 1, findall/3_empty: 1)"), lines[0]


def test_the_lint_counts_the_same_sites_on_a_cache_hit(s4):
    _native(s4)
    sys.modules.pop("s4_exit", None)
    mod = s4("s4_exit", clear=False)       # bytecode cached: directives only
    st = mod.__loader__.l3_stats
    assert st["skipped"] > 0, st            # the cache-hit path did run
    assert st["transition_constructs"] == PLANTED


def test_the_rows_are_scryers_oracle():
    if not os.path.exists(SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}; set "
                    f"CLAUSAL_ISO_ALLOW_NO_SCRYER=1 to run engine-only")
    goal = ("(case(N, L), write(N), write(' '), writeq(L), nl, fail "
            "; true), halt")
    proc = subprocess.run([SCRYER, os.path.join(S4, "s4_exit.pl"), "-g", goal],
                          capture_output=True, text=True, timeout=120,
                          stdin=subprocess.DEVNULL)
    rows = {}
    for line in proc.stdout.splitlines():
        name, sep, rest = line.partition(" ")
        if sep and re.match(r"c\d\d_", name):
            rows[name] = rest.strip()
    assert rows == SCRYER_ROWS
