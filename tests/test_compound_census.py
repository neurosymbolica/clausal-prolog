"""tools/compound_census: both halves count something real.

The static census and the run-time plugin are the instruments the Compound
retirement slices are gated on, so each is run here on a tiny synthetic tree
and must report NON-ZERO counts at the sites the tree plants -- an instrument
that silently saw nothing cannot pass this file.
"""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

# The run-time half now counts KWTerm (the Compound class is gone; the static
# half still reports any source that names it), so the subject is the KWTerm
# class: slice 9 deletes or rewrites this module.
pytestmark = pytest.mark.compound_retirement_slice9

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "compound_census"


def _census_module():
    return runpy.run_path(str(TOOL / "census.py"))


def test_self_test_passes():
    r = subprocess.run([sys.executable, str(TOOL / "census.py"), "--self-test"],
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "self-test PASS" in r.stdout


def test_static_census_counts_a_synthetic_tree(tmp_path):
    (tmp_path / "a.py").write_text(
        "from clausal.terms import Compound, KWTerm\n"
        "x = Compound('f', (1,))\n"
        "y = Compound('g', (x,))\n"
        "k = KWTerm('r', a=1)\n"
        "ok = isinstance(x, Compound) and isinstance(k, KWTerm)\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("PCompound = 1\ncompound = PCompound\n")
    m = _census_module()
    res = m["census"]([tmp_path])
    c = res["counts"]
    assert res["found"] == 2 and res["parsed"] == 2 and not res["unparsed"]
    assert c["Compound", "construct"] == 2
    assert c["KWTerm", "construct"] == 1
    assert c["Compound", "isinstance"] == 1
    assert c["KWTerm", "isinstance"] == 1
    assert [s[2] for s in res["sites"] if s[0] == "Compound"] == [2, 3]
    assert len(res["per_file"]) == 1          # b.py hits nothing


def test_static_census_sees_the_engine():
    """On the real tree: the Compound class is gone from the engine (no
    reference at all -- the positive control that the census would see one is
    ``test_static_census_counts_a_synthetic_tree``), and KWTerm is still
    there (until its own slice)."""
    m = _census_module()
    res = m["census"]([REPO / "clausal"])
    assert res["parsed"] > 100
    assert res["counts"]["Compound", "refs"] == 0, [
        s for s in res["sites"] if s[0] == "Compound"]
    assert res["counts"]["KWTerm", "refs"] > 0


def test_runtime_plugin_counts_a_synthetic_run(tmp_path):
    (tmp_path / "test_synthetic.py").write_text(
        "from clausal.terms import KWTerm\n"
        "from clausal.logic.exceptions import LogicException\n"
        "def test_builds():\n"
        "    KWTerm('r', a=1)\n"
        "    KWTerm('s', b=2)\n"
        "    LogicException('an_atom')\n"
        "    LogicException(('error', 'y', 'c'))\n")
    out = tmp_path / "cc.json"
    env = {**os.environ, "CC_OUT": str(out), "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": os.pathsep.join([str(REPO), str(TOOL)])}
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "-p", "compound_census_plugin", str(tmp_path / "test_synthetic.py")],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    rep = json.loads(out.read_text())
    assert Path(rep["engine"]).resolve() == (REPO / "clausal" / "__init__.py").resolve()
    assert rep["tests_run"] == 1 and rep["tests_constructing"] == 1
    # only what the synthetic test plants: no engine builder is involved
    assert rep["kwterm_total"] == 2, rep
    assert any(s.startswith("test_synthetic.py:4") for s, _ in rep["kwterm_sites"])
    assert rep["logic_exceptions"] == {"total": 2, "term_str": 1,
                                       "term_cell": 1}
    assert "compound census: KWTerm 2 constructions" in r.stdout
