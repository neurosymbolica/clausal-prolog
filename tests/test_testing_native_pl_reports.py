"""Slice 7 of the native ISO front-end plan: the runner on the native path.

A ``.pl`` file under ``CLAUSAL_PL_FRONTEND=native`` (and every Clausal
Prolog ``.clausal`` file) is lowered straight from its source, so each body
goal carries the span it was read from.  A failure report quotes that span
(``Y =:= 5``, not the canonical ``=:=(_, 5)``), names the clause's own
variables, prints values in Prolog syntax, and puts a line on every result
that has one: a failing or raising test, a ``test(Name, fail)`` that found a
solution (D14, ruled 2026-09-29: plunit's ``fail``), a ``<load>`` refusal and
a ``<collect>`` error.  No translation note appears.

Every output shape is pinned by a golden file under ``tests/golden/``
(regenerate with ``CLAUSAL_REGEN_GOLDEN=1``).  Each run asserts which front
end loaded the file, so a golden can never be recorded from the translator.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from clausal.testing import (
    EXIT_NO_TESTS,
    EXIT_OK,
    EXIT_TESTS_FAILED,
    load_clausal_module,
    main,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN = REPO_ROOT / "tests" / "golden"

# Lines 1..16.  Line numbers are part of every golden below.
FAILS_PL = textwrap.dedent("""\
    double(X, Y) :- Y is X * 2.
    colour(red).
    colour(green).

    test('double of two is four') :- double(2, 4).
    test('double of two is five') :-
        double(2, Y),
        Y =:= 5.
    test(raises) :- X is foo + 1, X > 0.
    test('double of three is seven') :- double(3, 7).
    test('no double of two is five', fail) :- double(2, 5).
    test('no double of two is four', fail) :-
        double(2, 4).
    test('a colour is blue') :- colour(C), C == blue.
    small(N) :- N < 3.
    test('five is small') :- small(5).
""")


@pytest.fixture
def native(monkeypatch):
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")


def _cli(capsys, monkeypatch, cwd: Path, argv: list[str]):
    monkeypatch.chdir(cwd)
    rc = main(argv)
    return rc, capsys.readouterr().out


def _assert_native(path: Path) -> None:
    """The file loads through the NATIVE front end (never a golden of the
    translator's output)."""
    from clausal.import_hook import NativePrologLoader
    mod = load_clausal_module(path)
    assert isinstance(mod.__spec__.loader, NativePrologLoader), path


def _golden(name: str, actual: str) -> None:
    path = GOLDEN / f"runner_native_{name}.txt"
    if os.environ.get("CLAUSAL_REGEN_GOLDEN"):
        path.write_text(actual)
    assert path.exists(), (
        f"missing golden {path}; regenerate with CLAUSAL_REGEN_GOLDEN=1")
    assert actual == path.read_text(), (
        f"runner output differs from {path.name}:\n{actual}")


# ── the report quotes the source ─────────────────────────────────────────────


def test_failing_goal_is_quoted_from_its_span(native, capsys, monkeypatch,
                                             tmp_path):
    (tmp_path / "arith.pl").write_text(FAILS_PL)
    _assert_native(tmp_path / "arith.pl")
    rc, out = _cli(capsys, monkeypatch, tmp_path, ["arith.pl"])
    assert rc == EXIT_TESTS_FAILED
    assert "arith.pl:6 :: double of two is five" in out, out
    assert "      Y =:= 5\n" in out, out
    assert "=:=(_, 5)" not in out, out
    # The clause's own variable names, values in Prolog syntax.
    assert "bindings at failure: Y = 4" in out, out
    assert "translated" not in out, out


def test_raising_goal_is_quoted_from_its_span(native, capsys, monkeypatch,
                                             tmp_path):
    (tmp_path / "arith.pl").write_text(FAILS_PL)
    rc, out = _cli(capsys, monkeypatch, tmp_path, ["arith.pl"])
    assert "arith.pl:9 :: raises" in out, out
    assert "      X is foo + 1\n" in out, out
    assert "is(_, +(foo, 1))" not in out, out


def test_a_failing_builtin_test_is_not_blamed_on_a_predicate(
        native, capsys, monkeypatch, tmp_path):
    """``Y =:= 5`` is a built-in comparison: "no solution for ANY arguments
    ... check its own clauses" is the predicate-call diagnosis, and wrong."""
    (tmp_path / "arith.pl").write_text(FAILS_PL)
    rc, out = _cli(capsys, monkeypatch, tmp_path, ["arith.pl"])
    block = out.split("double of two is five", 1)[1].split("::", 1)[0]
    assert "for ANY arguments" not in block, out
    assert "built-in" in block, out
    assert "C == blue" in out and "C = red" in out, out
    # A fact the producer did not use is a head mismatch, not a failing
    # ``Unify`` leaf (the compiler hoists a fact's arguments into its body).
    assert "(_ is green)" not in out and "re-ran satisfiable" not in out, out


def test_descent_quotes_the_callee_goal_from_its_span(native, capsys,
                                                      monkeypatch, tmp_path):
    (tmp_path / "arith.pl").write_text(FAILS_PL)
    rc, out = _cli(capsys, monkeypatch, tmp_path, ["arith.pl"])
    assert "arith.pl:16 :: five is small" in out, out
    assert "arith.pl:15  N < 3" in out, out
    assert "    N = 5" in out, out


def test_nearest_solution_is_printed_in_prolog_syntax(native, capsys,
                                                      monkeypatch, tmp_path):
    (tmp_path / "arith.pl").write_text(FAILS_PL)
    rc, out = _cli(capsys, monkeypatch, tmp_path, ["arith.pl"])
    assert "arith.pl:10 :: double of three is seven" in out, out
    assert "double(3,6)" in out, out


def test_d14_negative_test_with_a_solution_goes_red_with_its_line(
        native, capsys, monkeypatch, tmp_path):
    (tmp_path / "arith.pl").write_text(FAILS_PL)
    rc, out = _cli(capsys, monkeypatch, tmp_path, ["-v", "arith.pl"])
    assert rc == EXIT_TESTS_FAILED
    assert "PASS  arith.pl::no double of two is five" in out, out
    assert "FAIL  arith.pl::no double of two is four" in out, out
    assert ("arith.pl:12 :: no double of two is four — test(..., fail) "
            "succeeded") in out, out


def test_d14_alone_decides_the_exit_status(native, capsys, monkeypatch,
                                           tmp_path):
    (tmp_path / "neg.pl").write_text("p(1).\ntest(none, fail) :- p(1).\n")
    rc, out = _cli(capsys, monkeypatch, tmp_path, ["neg.pl"])
    assert rc == EXIT_TESTS_FAILED, out
    assert "1 tests: 0 passed, 1 failed [FAILED]" in out, out
    (tmp_path / "neg.pl").write_text("p(1).\ntest(none, fail) :- p(2).\n")
    rc, out = _cli(capsys, monkeypatch, tmp_path, ["neg.pl"])
    assert rc == EXIT_OK, out


def test_load_refusal_names_its_line(native, capsys, monkeypatch, tmp_path):
    (tmp_path / "cut.pl").write_text("p(1).\np(X) :- !, X = 2.\n"
                                     "test(t) :- p(1).\n")
    rc, out = _cli(capsys, monkeypatch, tmp_path, ["cut.pl"])
    assert rc == EXIT_TESTS_FAILED
    assert "cut.pl:2 :: <load>" in out, out


def test_collection_error_names_its_line(native, capsys, monkeypatch,
                                         tmp_path):
    (tmp_path / "opt.pl").write_text("p(1).\n\ntest(t, throws(x)) :- p(1).\n")
    rc, out = _cli(capsys, monkeypatch, tmp_path, ["opt.pl"])
    assert rc == EXIT_TESTS_FAILED
    assert "opt.pl:3 :: <collect>" in out, out


#: The seam twin of FAILS_PL, for the unchanged-output controls.
FAILS_SEAM = """\
-private([red, green, blue, foo])
double(X, Y) <- eval_(X * 2, Y)
colour(red),
colour(green),
small(N) <- (N < 3)
test("double of two is four") <- double(2, 4)
test("double of two is five") <- (double(2, Y), Y == 5)
test("raises") <- (eval_(foo + 1, X), X > 0)
test("double of three is seven") <- double(3, 7)
test("no double of two is four", fail) <- double(2, 4)
test("a colour is blue") <- (colour(C), C == blue)
test("five is small") <- small(5)
"""


#: A translator .pl whose wrong-value producer (``len/2``) has a fact with a
#: hoisted head argument (``len([], 0)``): its descent route and note are
#: the translator's 7c0379db shape, which the native-only head-mismatch
#: rule must not touch.
HOISTED_PL = """\
:- module(q, []).
len([], 0).
len([_|T], N) :- len(T, M), N is M + 1.
shape(circle).
shape(square).
test(len_three) :- len([a,b,c], 3).
test(len_wrong) :- len([a,b], N), N =:= 5.
test(shape_tri) :- shape(S), S == triangle.
test(unify_bad) :- X = f(1), X = f(2).
test(less) :- 3 < 2.
test(raise_it) :- atom_length(X, _), X > 1.
test(neg, fail) :- shape(circle).
"""


@pytest.mark.parametrize("runner", ["cli", "plugin"])
@pytest.mark.parametrize("name,text,suffix", [
    ("arith.pl", FAILS_PL, "pl"), ("arith.seam", FAILS_SEAM, "seam"),
    ("q.pl", HOISTED_PL, "hoisted_pl")], ids=["pl", "seam", "hoisted_pl"])
def test_translator_and_seam_reports_are_unchanged(runner, name, text,
                                                   suffix, tmp_path):
    """Negative control, EXACT: the translator (no source map) and the seam
    report byte-for-byte as they did on 7c0379db, before this slice.  The
    goldens ``runner_unchanged_*.txt`` were recorded from that commit and
    are never regenerated from this one."""
    import re
    (tmp_path / name).write_text(text)
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    env["CLAUSAL_PL_FRONTEND"] = "translator"         # the goldens' .pl path
    if runner == "cli":
        argv = [sys.executable, "-m", "clausal.testing", "-v", name]
    else:
        (tmp_path / "conftest.py").write_text(
            _SHIM.format(path=str(REPO_ROOT / "conftest.py")))
        argv = [sys.executable, "-m", "pytest", "-q", "-rfE",
                "-p", "no:cacheprovider", name]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          cwd=tmp_path, env=env)
    out = re.sub(r"in [0-9.]+s", "in Xs", proc.stdout + proc.stderr)
    golden = GOLDEN / f"runner_unchanged_{runner}_{suffix}.txt"
    assert out == golden.read_text(), out


# ── an empty scan fails, on the native path too ──────────────────────────────


def test_dir_of_testless_native_pl_exits_non_zero(native, capsys,
                                                  monkeypatch, tmp_path):
    (tmp_path / "a.pl").write_text("likes(mary, wine).\n")
    (tmp_path / "b.pl").write_text("p(1).\np(2).\n")
    _assert_native(tmp_path / "a.pl")
    rc, out = _cli(capsys, monkeypatch, tmp_path, ["."])
    assert rc == EXIT_NO_TESTS, out
    assert "2 file(s) collected, but no test/1 clauses found" in out, out


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
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT),
             "CLAUSAL_PL_FRONTEND": "native"},
    )


def test_plugin_empty_scan_of_native_pl_fails(tmp_path):
    proc = _run_plugin(tmp_path, {"a.pl": "likes(mary, wine).\n"})
    out = proc.stdout + proc.stderr
    assert proc.returncode == EXIT_NO_TESTS, out


def test_plugin_native_failure_quotes_the_span_and_line(tmp_path):
    proc = _run_plugin(tmp_path, {"arith.pl": FAILS_PL})
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert "at arith.pl:6" in out, out
    assert "Y =:= 5" in out, out
    assert "at arith.pl:12" in out, out          # the D14 red
    assert "translated" not in out, out


# ── golden: one per output shape ─────────────────────────────────────────────

GOLDEN_CASES = {
    # The verbose listing and every failure block shape.
    "failures": ({"arith.pl": FAILS_PL}, ["-v", "arith.pl"], EXIT_TESTS_FAILED),
    # All green.
    "passed": ({"ok.pl": "p(1).\ntest(one) :- p(1).\ntest(none, fail) :- "
                         "p(2).\n"}, ["-v", "ok.pl"], EXIT_OK),
    # A reader syntax error and a refused construct.
    "load": ({"broken.pl": "test(x) :- foo(.\n",
              "cut.pl": "p(1).\np(X) :- !, X = 2.\ntest(t) :- p(1).\n"},
             ["."], EXIT_TESTS_FAILED),
    # An unsupported test option.
    "collect": ({"opt.pl": "p(1).\n\ntest(t, throws(x)) :- p(1).\n"},
                ["opt.pl"], EXIT_TESTS_FAILED),
    # Files collected, no test/1 in any of them.
    "no_tests": ({"a.pl": "likes(mary, wine).\n", "b.pl": "p(1).\n"},
                 ["."], EXIT_NO_TESTS),
    # No test file at all.
    "no_files": ({"notes.md": "# notes\n"}, ["."], EXIT_NO_TESTS),
}


@pytest.mark.parametrize("shape", sorted(GOLDEN_CASES))
def test_golden_output_shape(shape, native, capsys, monkeypatch, tmp_path):
    files, argv, want_rc = GOLDEN_CASES[shape]
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    for name in files:
        if name.endswith(".pl") and shape not in ("load",):
            _assert_native(tmp_path / name)
    rc, out = _cli(capsys, monkeypatch, tmp_path, argv)
    assert rc == want_rc, out
    _golden(shape, out)


def test_clausal_prolog_report_quotes_the_span(capsys, monkeypatch, tmp_path):
    """Clausal Prolog is native whatever CLAUSAL_PL_FRONTEND says."""
    monkeypatch.delenv("CLAUSAL_PL_FRONTEND", raising=False)
    (tmp_path / "arith.clausal").write_text(
        ':- module(arith, []).\n'
        'double(X, Y) :- Y is X * 2.\n'
        'test("double of two is five") :-\n'
        '    double(2, Y),\n'
        '    Y =:= 5.\n'
        ':- end_module(arith).\n')
    rc, out = _cli(capsys, monkeypatch, tmp_path, ["arith.clausal"])
    assert rc == EXIT_TESTS_FAILED
    assert "arith.clausal:3 :: double of two is five" in out, out
    assert "      Y =:= 5\n" in out, out
    assert "bindings at failure: Y = 4" in out, out
