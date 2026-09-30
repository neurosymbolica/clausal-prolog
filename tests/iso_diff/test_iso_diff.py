"""Differential sweep: the native ``.pl`` front end (CLAUSAL_PL_FRONTEND=
native) against Scryer (:data:`SCRYER`), on atoms & strings, term inspection,
standard order and sorting, between/succ/numlist, the arithmetic evaluables,
catch/throw error terms, the all-solutions predicates and library(lists).

Each area file holds ``t(Id, Template, Goal)`` rows; ``prelude.pl`` (put in
front of it) prints one line per row: the findall/3 of Template over Goal,
or ``ex(E)`` for an error, with variables numbered and error contexts
blanked (ISO leaves the context implementation dependent).  Both engines
run the SAME file and every row is compared.

:data:`KNOWN` lists the rows where the two still answer differently, each
with its classification.  The test fails on a NEW divergence and on a KNOWN
row that stopped diverging (remove it from the table then), so the table is
always the current state.  Skipped when the Scryer binary is absent.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
#: The oracle: upstream Scryer plus a commit that only adds library(clpq)
#: (not the /workspace/scryer-prolog working tree, which carries WIP).
SCRYER = os.environ.get(
    "CLAUSAL_SCRYER",
    "/workspace/scryer-prolog-clpq/target/release/scryer-prolog")
AREAS = ["atoms", "terms", "sorting", "between", "arith", "except", "allsol",
         "lists"]

#: Row -> why the engines still differ.  (c) = a Clausal extension or a
#: writer/reader difference; (d) = needs a ruling; (o) = the Scryer build is
#: the one that disagrees with ISO; (a) = Clausal is wrong, not fixed yet;
#: (b) = a builtin Scryer has and Clausal lacks (a loud existence_error).
KNOWN = {
    # writeq quotes a non-ASCII lowercase atom that Scryer writes bare
    "a67": "c", "a80": "c",
    # [a|b] (a non-list tail) in a type_error(list, _) culprit comes out
    # as [a,b]
    "a68": "a", "x22": "a", "s25": "a",
    # standard order: ISO 7.2 puts every float before every integer; Clausal
    # compares numbers by value (float first on a tie)
    "t43": "d", "t52": "d", "t67": "d", "s04": "d", "s11": "d",
    # the Scryer build: a list inside sort/2's list is a type_error, and
    # [a] @> [a, c] (both are Scryer defects)
    "t58": "o", "t71": "o", "s09": "o", "s12": "o", "s13": "o", "s28": "o",
    # -0.0 and 0.0 are equal in standard order; sort/2 keeps a different one
    "s16": "c",
    # atan/2 is a Clausal evaluable (Scryer has atan2/2 only)
    "e77": "c",
    # log(0): Scryer says float_overflow, ISO undefined (Clausal)
    "e71": "o",
    # call(foo:bar): no module foo -- the culprit is the quoted spelling
    "x36": "a",
    # msort/2 is a Clausal builtin, absent from Scryer
    "x52": "c",
    # sum_list/2 on a non-number: type_error(number) vs Scryer's evaluable
    "x59": "d", "l56": "d",
    # setof/3 merges 1 and 1.0 (parked decision A01-D001)
    "f21": "d",
    # setof/3 with a Bag [a|b]: see the [a|b] rows
    "f36": "a",
    # select/3 does not run in the (-, ?, +) mode; sum_list/2 does not
    # enumerate a list; permutation(foo, _) fails
    "l43": "a", "l53": "a", "l49": "d", "l65": "a",
}

_ROW = re.compile(r"([a-z]+\d+) (.*)$")


def _rows(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = _ROW.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _source(area: str) -> str:
    with open(os.path.join(HERE, "prelude.pl"), encoding="utf-8") as f:
        pre = f.read()
    with open(os.path.join(HERE, area + ".pl"), encoding="utf-8") as f:
        return pre + f.read()


_CLAUSAL = r"""
import importlib, os, shutil, sys
d, name = sys.argv[1], sys.argv[2]
import clausal
root = os.environ["CLAUSAL_ROOT"]
assert clausal.__file__.startswith(root), (clausal.__file__, root)
sys.path.insert(0, d)
shutil.rmtree(os.path.join(d, "__pycache__"), ignore_errors=True)
from clausal import import_hook as ih
mod = importlib.import_module(name)
assert type(mod.__loader__) is ih.NativePrologLoader, type(mod.__loader__)
st = mod.__loader__.l3_stats
assert st["read"] > 0 and st["refused"] == 0, st
from clausal.logic.solve import call
for _ in call("run", module=mod):
    break
"""


@pytest.mark.parametrize("area", AREAS)
def test_area_matches_scryer_except_known(area, tmp_path):
    if not os.path.exists(SCRYER):
        pytest.skip(f"the clean Scryer is not built at {SCRYER}")
    src = _source(area)
    ids = re.findall(r"^t\(([a-z]+\d+),", src, re.M)
    assert ids and len(ids) == len(set(ids)), area
    name = f"isodiff_{area}"
    path = tmp_path / (name + ".pl")
    path.write_text(src, encoding="utf-8")

    s = subprocess.run([SCRYER, str(path), "-g", "run", "-g", "halt"],
                       stdin=subprocess.DEVNULL, capture_output=True,
                       text=True, timeout=180)
    env = dict(os.environ, PYTHONPATH=ROOT, CLAUSAL_ROOT=ROOT,
               CLAUSAL_PL_FRONTEND="native")
    c = subprocess.run([sys.executable, "-W", "ignore", "-c", _CLAUSAL,
                        str(tmp_path), name],
                       cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=600)
    S, C = _rows(s.stdout), _rows(c.stdout)
    # Every row answered on both sides: a short count means a load or run
    # failure, not agreement.
    assert len(S) == len(ids), (area, len(S), len(ids), s.stderr[-2000:])
    assert len(C) == len(ids), (area, len(C), len(ids), c.stderr[-3000:])

    diverging = {i for i in ids if S[i] != C[i]}
    known = {i for i in ids if i in KNOWN}
    new = sorted(diverging - known)
    fixed = sorted(known - diverging)
    detail = "\n".join(f"{i}\n  scryer:  {S[i]}\n  clausal: {C[i]}"
                       for i in new)
    assert not new, f"{area}: new divergences\n{detail}"
    assert not fixed, f"{area}: KNOWN rows that now agree: {fixed}"


def test_known_rows_exist():
    """Every KNOWN id names a row of some area file."""
    ids = set()
    for area in AREAS:
        ids |= set(re.findall(r"^t\(([a-z]+\d+),", _source(area), re.M))
    assert len(ids) > 250
    assert set(KNOWN) <= ids, sorted(set(KNOWN) - ids)
