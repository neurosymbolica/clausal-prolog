"""Slice 8.1 (re-planned 2026-10-12): translator-vs-native parity over
every ``.pl`` source in the repository.

``clausal.tools.pl_parity`` loads each file under both ``.pl`` front ends,
each in its own subprocess with its own empty bytecode cache, and compares
load/refusal, test verdicts and (for files without tests) all-answers.  The
known differences are pinned, with their class, in
``tests/fixtures/pl_parity_known.json``: a NEW difference goes red, and so
does a pinned one that has gone (prune the fixture as gaps close), and so
does any change in a pinned row's values or in native's observation of any
file (``tests/fixtures/pl_parity_native.json``).  Regenerate both with
``python -m clausal.tools.pl_parity --update tests/fixtures/pl_parity_known.json``
and classify each new row (class "?" is refused).
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


def _fixture(known=None, native=None, tsha=None):
    return {"known": known or {}, "native": native or {},
            "translator_sha": tsha or {}}


def test_check_flags_new_and_gone_differences():
    r = P.Run(read=1, compared=1)
    r.diffs = [P.Difference("f.pl", "load", "", "ok", "refused: x")]
    r.sides = {}
    assert P.check(r, _fixture({"f.pl::load::": {"class": "b"}})) == []
    problems = P.check(r, _fixture({"g.pl::load::": {"class": "b"}}))
    assert any(p.startswith("NEW difference: f.pl::load::") for p in problems)
    assert any(p.startswith("GONE (prune the fixture): g.pl::load::")
               for p in problems)


def test_a_changed_value_inside_a_pinned_row_goes_red():
    """The fixture pins VALUES, not just keys: a native regression inside a
    row that is already a known difference is caught."""
    r = P.Run(read=1, compared=1)
    r.sides = {}
    r.diffs = [P.Difference("f.pl", "tests", "t", "pass", "fail")]
    row = {"class": "a", "native_sha": P.sha("fail"),
           "translator_sha": P.sha("pass")}
    assert P.check(r, _fixture({r.diffs[0].key: row})) == []
    r.diffs = [P.Difference("f.pl", "tests", "t", "pass", "error: boom")]
    problems = P.check(r, _fixture({r.diffs[0].key: row}))
    assert any(p.startswith("CHANGED native value in pinned row")
               for p in problems), problems


def test_native_observation_of_every_file_is_pinned():
    """A native-only file has no translator side to differ from; its native
    answers are pinned on their own, so a native regression there is red."""
    t = {"load": "refused", "error": "x", "tests": None,
         "collect_error": None, "preds": None}
    n = _side(preds={"p/1": ["[a]", "[b]"]})
    r = P.Run(read=1, compared=1, sides={"f.pl": (t, n)})
    r.diffs = P.compare("f.pl", t, n)
    known = {d.key: {"class": "a"} for d in r.diffs}
    pinned = {"f.pl": P.pinned_view(n)}
    tsha = {"f.pl": P.sha(P.pinned_view(t))}
    assert P.check(r, _fixture(known, pinned, tsha)) == []
    n2 = _side(preds={"p/1": ["[a]"]})
    r.sides = {"f.pl": (t, n2)}
    problems = P.check(r, _fixture(known, pinned, tsha))
    assert any(p.startswith("NATIVE CHANGED f.pl: preds p/1") for p in problems)


def test_a_timeout_is_not_a_translator_vs_native_difference():
    t = _side(preds={"p/1": "timeout", "q/0": ["true"]})
    n = _side(preds={"p/1": ["[a]"], "q/0": ["true"]})
    assert P.compare("f.pl", t, n) == []


def test_a_timeout_where_a_value_is_pinned_goes_red():
    """A native regression that turns into a hang must not hide behind the
    timeout: against a pinned value it is a change (after run()'s retry)."""
    pinned = {"load": "ok", "preds": {"p/1": ["[a]"]}}
    now = {"load": "ok", "preds": {"p/1": "timeout"}}
    assert P._diff_items(pinned, now)
    assert P._needs_retry(now, pinned)


def test_a_pinned_timeout_that_now_terminates_goes_red():
    pinned = {"load": "ok", "preds": {"p/1": "timeout"}}
    now = {"load": "ok", "preds": {"p/1": ["[a]"]}}
    assert P._diff_items(pinned, now)
    assert not P._needs_retry(now, pinned)


def test_only_a_pinned_timeout_that_still_times_out_passes():
    pinned = {"load": "ok", "preds": {"p/1": "timeout"}}
    assert P._diff_items(pinned, dict(pinned)) == []
    assert not P._needs_retry(pinned, pinned)


def test_a_runaway_call_is_killed_and_observed_as_timeout(tmp_path,
                                                         monkeypatch):
    monkeypatch.setenv("CLAUSAL_PARITY_CALL_TIMEOUT", "2")
    f = tmp_path / "loop.pl"
    f.write_text("loop(X) :- loop(X).\nok(1).\n")
    n = P.run_side(P.Source(str(f), "loop.pl", "tests"), "native",
                   tmp_path / "cache", REPO_ROOT)
    assert n["preds"] == {"loop/1": "timeout", "ok/1": ["[1]"]}, n


def test_depth_categories():
    ok = _side(tests={"t": "pass"})
    err = _side(tests={"t": "error: E"})
    ref = _side(load="refused", error="x")
    assert P.category(ok, ok) == "deep"
    assert P.category(err, err) == "errors_only"
    assert P.category(_side(preds={}), _side(preds={})) == "nothing"
    assert P.category(ref, ok) == "native_only"
    assert P.category(ok, ref) == "translator_only"
    assert P.category(ref, ref) == "both_refused"
    assert P.category({"crash": "x"}, ok) == "crash"


def test_the_child_must_prove_its_engine():
    root = REPO_ROOT
    good = {"frontend": "native", "loader": None,
            "clausal_file": str(root / "clausal" / "__init__.py")}
    assert P._engine_problem(good, "native", root) is None
    # A refusal (loader None) still proves its front end and engine.
    assert "wrong front end" in P._engine_problem(good, "translator", root)
    elsewhere = dict(good, clausal_file="/elsewhere/clausal/__init__.py")
    assert "wrong engine" in P._engine_problem(elsewhere, "native", root)
    wrong_loader = dict(good, loader="PrologLoader")
    assert "wrong loader" in P._engine_problem(wrong_loader, "native", root)


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
        assert e.get("native_sha") and e.get("translator_sha"), e
    obs = json.loads((FIXTURE.parent / data["observations"]).read_text())
    assert len(obs["native"]) == len(obs["translator_sha"]) > 0


# About 2 minutes (about 200 children at -j 6, each test or call forked).
# Move this behind CLAUSAL_SLOW_TESTS when that convention lands (planned
# with the CLP(Q) port); main has no slow-test convention yet.
REPORT = (REPO_ROOT / "implementation_plans"
          / "native-iso-reader-step2-2026-09-29" / "parity-2026-10-12.md")


@pytest.mark.timeout(1500)
def test_repository_parity_matches_the_pinned_differences(tmp_path):
    summary = tmp_path / "summary.md"
    proc = subprocess.run(
        [sys.executable, "-m", "clausal.tools.pl_parity", "-j", "6",
         "--check", str(FIXTURE), "--summary-md", str(summary)],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=1500,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)})
    out = proc.stdout + proc.stderr
    assert "files read" in out, out
    first = out.splitlines()[0]
    read = int(first.split()[1])
    compared = int(first.split()[4])
    assert read > 0 and compared == read, out
    assert "pl_parity: depth: deep " in out, out
    deep = int(out.split("pl_parity: depth: deep ", 1)[1].split(",")[0])
    assert deep > 0, out
    assert proc.returncode == 0, out
    # The report's numbers are the tool's: its generated block equals this
    # run's, byte for byte.
    text = REPORT.read_text(encoding="utf-8")
    begin = text.index(P.SUMMARY_BEGIN)
    end = text.index(P.SUMMARY_END) + len(P.SUMMARY_END) + 1
    assert text[begin:end] == summary.read_text(encoding="utf-8"), (
        "parity-2026-10-12.md's generated block is stale; paste the "
        "--summary-md output")
