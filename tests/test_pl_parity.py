"""Slice 8.1 (re-planned 2026-10-12): translator-vs-native parity over
every ``.pl`` source in the repository.

``clausal.tools.pl_parity`` loads each file under both ``.pl`` front ends,
each in its own subprocess with its own empty bytecode cache, and compares
load/refusal, test verdicts and (for files without tests) all-answers.  The
known differences are pinned, with their class, in
``tests/fixtures/pl_parity_known.json``: a NEW difference goes red, and so
does a pinned one that has gone (prune the fixture as gaps close).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from clausal.tools import pl_parity as P

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "pl_parity_known.json"


def _side(**kw):
    base = {"load": "ok", "error": None, "tests": None, "collect_error": None,
            "preds": None, "loader": None}
    base.update(kw)
    return base


# ── the comparison ───────────────────────────────────────────────────────────


def test_compare_agrees_on_identical_sides():
    s = _side(preds={"p/1": ["[a]", "[b]"]})
    assert P.compare("f.pl", s, dict(s)) == []


def test_compare_reports_each_kind():
    kinds = lambda t, n: [d.kind for d in P.compare("f.pl", t, n)]  # noqa: E731
    assert kinds(_side(), _side(load="refused", error="x")) == ["load"]
    assert kinds(_side(load="refused"), _side(load="refused")) == []
    assert kinds(_side(tests={"t": "pass"}), _side(tests={"t": "fail"})) == ["tests"]
    assert kinds(_side(preds={"p/1": ["[a]"]}),
                 _side(preds={"p/1": ["[b]"]})) == ["answers"]
    assert kinds(_side(preds={"p/1": []}), _side(preds={})) == ["predicates"]
    assert kinds({"crash": "boom"}, _side()) == ["crash"]


def test_check_flags_new_and_gone_differences():
    r = P.Run(read=1, compared=1)
    r.diffs = [P.Difference("f.pl", "load", "", "ok", "refused: x")]
    assert P.check(r, {"f.pl::load::": {"class": "b"}}) == []
    problems = P.check(r, {"g.pl::load::": {"class": "b"}})
    assert any(p.startswith("NEW difference: f.pl::load::") for p in problems)
    assert any(p.startswith("GONE (prune the fixture): g.pl::load::")
               for p in problems)


def test_norm_ignores_spacing_and_variable_names():
    assert P._norm("[_123, f(_123, _G7)]") == P._norm("[_1,f(_1,_)]")
    assert P._norm("[_1,_1]") != P._norm("[_,_]")


# ── fail closed ──────────────────────────────────────────────────────────────


def test_an_empty_run_is_refused(capsys):
    rc = P.main(["--no-docs", "--only", "no-such-file-anywhere-xyz"])
    out = capsys.readouterr().out
    assert rc == 2, out
    assert "0 files read, 0 compared" in out, out
    assert "refusing an empty run" in out, out


# ── the probe: one front end per child, asserted ─────────────────────────────


def test_each_side_runs_its_own_front_end(tmp_path):
    """Negative control as well: a file the translator refuses (an
    underscore-led functor) and native loads is a difference."""
    f = tmp_path / "u.pl"
    f.write_text("p('_'(1)).\ntest(t) :- p(_).\n")
    src = P.Source(str(f), "u.pl", "tests")
    cache = tmp_path / "cache"
    t = P.run_side(src, "translator", cache, REPO_ROOT)
    n = P.run_side(src, "native", cache, REPO_ROOT)
    assert "crash" not in t and "crash" not in n, (t, n)
    assert n["loader"] == "NativePrologLoader" and n["tests"] == {"t": "pass"}
    assert t["load"] == "refused", t
    assert [d.kind for d in P.compare("u.pl", t, n)] == ["load"]
    # The caches are private and per front end; nothing lands beside f.
    assert not (tmp_path / "__pycache__").exists()


# ── the gate ─────────────────────────────────────────────────────────────────


def test_fixture_classes_are_valid():
    data = json.loads(FIXTURE.read_text())
    assert data["known"], "an empty fixture pins nothing"
    for e in data["known"]:
        assert e["class"] in ("a", "b", "c", "d"), e
        assert e.get("note"), e


def test_repository_parity_matches_the_pinned_differences():
    proc = subprocess.run(
        [sys.executable, "-m", "clausal.tools.pl_parity", "-j", "6",
         "--check", str(FIXTURE)],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=1500,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)})
    out = proc.stdout + proc.stderr
    assert "files read" in out, out
    first = out.splitlines()[0]
    read = int(first.split()[1])
    compared = int(first.split()[4])
    assert read > 0 and compared == read, out
    assert proc.returncode == 0, out
