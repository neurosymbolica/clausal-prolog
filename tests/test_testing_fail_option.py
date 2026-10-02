"""Negative tests: plunit's ``test(Name, fail) :- Goal``.

Ruling 2026-09-29: a ``test/2`` clause whose option is ``fail`` passes iff
its goal has NO solution.  A solution fails the test; an exception is an
error, exactly as for ``test/1``.  Any other option is a collection error
naming it, never silently ignored.  The seam spelling is the same term,
``test(name, fail) <- Goal``, and ``.pl`` files spell it as plunit does.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from clausal.testing import (
    EXIT_OK,
    EXIT_TESTS_FAILED,
    TestCollectionError,
    collect_tests,
    load_clausal_module,
    main,
    run_file,
    run_test,
)
from tests._suffix import SEAM as SEAM_EXT

REPO_ROOT = Path(__file__).resolve().parent.parent

SEAM = """\
p(1),
test("positive") <- p(1)
test("no p of two", fail) <- p(2)
test("p of one exists", fail) <- p(1)
test("raises", fail) <- throw('boom')
"""

PL = """\
p(1).
test(positive) :- p(1).
test('no p of two', fail) :- p(2).
test('p of one exists', fail) :- p(1).
test(raises, fail) :- throw(boom).
"""

NAMES = ["positive", "no p of two", "p of one exists", "raises"]


@pytest.fixture(params=[("neg.clausal", SEAM), ("neg.seam", SEAM),
                        ("neg.pl", PL)], ids=["clausal", "seam", "pl"])
def neg_file(request, tmp_path):
    name, text = request.param
    p = tmp_path / name
    p.write_text(text)
    return p


def test_fail_tests_are_collected_in_source_order(neg_file):
    mod = load_clausal_module(neg_file)
    assert collect_tests(mod) == NAMES


def test_fail_test_passes_iff_the_goal_has_no_solution(neg_file):
    mod = load_clausal_module(neg_file)
    assert run_test(mod, "positive").passed
    ok = run_test(mod, "no p of two")
    assert ok.passed and ok.error is None
    bad = run_test(mod, "p of one exists")
    assert not bad.passed and bad.error is None
    assert bad.negative


def test_fail_test_that_raises_is_an_error_not_a_pass(neg_file):
    mod = load_clausal_module(neg_file)
    r = run_test(mod, "raises")
    assert not r.passed
    assert r.error is not None


def test_cli_reports_the_fail_spelling(capsys, neg_file):
    rc = main(["-v", str(neg_file)])
    out = capsys.readouterr().out
    assert rc == EXIT_TESTS_FAILED
    assert "4 tests: 2 passed, 2 failed [FAILED]" in out
    assert "p of one exists" in out
    assert "test(..., fail) succeeded" in out


def test_all_green_fail_file(capsys, tmp_path):
    p = tmp_path / f"ok{SEAM_EXT}"
    p.write_text('p(1),\ntest("none", fail) <- p(2)\n')
    assert main([str(p)]) == EXIT_OK


# ── unknown options are collection errors ────────────────────────────────────


@pytest.mark.parametrize("name,text,shown", [
    (f"o{SEAM_EXT}", 'p(1),\ntest("t", throws(\'x\')) <- p(1)\n', "throws"),
    (f"o{SEAM_EXT}", 'p(1),\ntest("t", \'nondet\') <- p(1)\n', "nondet"),
    (f"o{SEAM_EXT}", 'p(1),\ntest("t", [fail]) <- p(1)\n', "[fail]"),
    ("o.pl", "p(1).\ntest(t, throws(x)) :- p(1).\n", "throws"),
    ("o.pl", "p(1).\ntest(t, timeout(5)) :- p(1).\n", "timeout(5)"),
    ("o.pl", "p(1).\ntest(t, blocked(why)) :- p(1).\n", "blocked"),
])
def test_unknown_option_is_a_collection_error(tmp_path, name, text, shown):
    p = tmp_path / name
    p.write_text(text)
    mod = load_clausal_module(p)
    with pytest.raises(TestCollectionError) as ei:
        collect_tests(mod)
    msg = str(ei.value)
    assert shown in msg
    assert "only `fail` is supported" in msg
    # plunit's other options are listed, so the reader knows it was read
    assert "throws(Error)" in msg and "blocked(Reason)" in msg
    assert "line 2" in msg or name.endswith(".pl")


def test_unknown_option_fails_the_file_in_the_cli(capsys, tmp_path):
    p = tmp_path / f"o{SEAM_EXT}"
    p.write_text('p(1),\ntest("ok") <- p(1)\ntest("t", \'nondet\') <- p(1)\n')
    assert main([str(p)]) == EXIT_TESTS_FAILED
    out = capsys.readouterr().out
    assert f"o{SEAM_EXT} :: <collect>" in out
    assert "nondet" in out
    r = run_file(p)
    assert [x.name for x in r.results] == ["<collect>"]


# ── the pytest plugin ────────────────────────────────────────────────────────

_SHIM = """\
import importlib.util as _util

_spec = _util.spec_from_file_location("_clausal_root_conftest", {path!r})
_plugin = _util.module_from_spec(_spec)
_spec.loader.exec_module(_plugin)

pytest_collect_file = _plugin.pytest_collect_file
"""


def _run_plugin(tmp_path: Path, files: dict[str, str]):
    (tmp_path / "conftest.py").write_text(
        _SHIM.format(path=str(REPO_ROOT / "conftest.py")))
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-rfE",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )


def test_plugin_runs_fail_tests(tmp_path):
    proc = _run_plugin(tmp_path, {f"neg{SEAM_EXT}": SEAM, "neg2.pl": PL})
    out = proc.stdout + proc.stderr
    assert "4 failed, 4 passed" in out, out
    assert "test('p of one exists', fail) succeeded" in out, out


def test_plugin_reports_an_unknown_option(tmp_path):
    proc = _run_plugin(tmp_path, {
        f"o{SEAM_EXT}": 'p(1),\ntest("t", \'nondet\') <- p(1)\n'})
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert f"o{SEAM_EXT}::<collect>" in out, out
    assert "nondet" in out, out


# ── review follow-ups ────────────────────────────────────────────────────────


def test_run_test_direct_refuses_an_unknown_option(tmp_path):
    """run_test without collect_tests must not run throws(...) as `fail`."""
    p = tmp_path / f"o{SEAM_EXT}"
    p.write_text("p(1),\ntest(\"t\", throws('x')) <- p(2)\n")
    mod = load_clausal_module(p)
    r = run_test(mod, "t")
    assert not r.passed
    assert isinstance(r.error, TestCollectionError)
    assert "throws('x')" in str(r.error)


def test_pl_test2_fact_and_call_still_unify(tmp_path):
    """A .pl test/2 predicate that is NOT a plunit test: the fact and a
    call of it translate the atom option the same way, so they unify."""
    p = tmp_path / "facts.pl"
    p.write_text("test(x, false).\ntest(y, fail).\n"
                 "test(ok) :- test(x, false), test(y, fail).\n")
    mod = load_clausal_module(p)
    lm = mod.__dict__["$module"]
    assert lm.db.is_defined("test", 2)
    # test/2 facts whose option is not `fail` are refused at collection ...
    with pytest.raises(TestCollectionError):
        collect_tests(mod)
    # ... but the translation itself is consistent: the call finds the facts.
    assert run_test(mod, "ok").passed


def test_same_description_under_test1_and_test2_warns(tmp_path):
    p = tmp_path / f"w{SEAM_EXT}"
    p.write_text('p(1),\ntest("t") <- p(1)\ntest("t", fail) <- p(2)\n')
    mod = load_clausal_module(p)
    with pytest.warns(UserWarning, match=r"more than one of test/1"):
        collect_tests(mod)
