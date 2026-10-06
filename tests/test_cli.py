"""The ``clausal`` command (``clausal.cli``): run a ``.clausal`` or ``.pl``
program -- its ``main/0``, ``-g`` goals with toplevel-style answers, its
tests, and ``argv`` -- with the documented exit statuses.

Every case runs the real command in a subprocess (``python -m clausal``),
pinned to this checkout, from the program's own directory.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

PROG = textwrap.dedent("""\
    :- module(prog, [fib/2]).
    :- use_module(library(clpz)).

    fib(0, 0).
    fib(1, 1).
    fib(N, F) :-
        N #> 1,
        N1 #= N - 1, N2 #= N - 2,
        F #= F1 + F2,
        fib(N1, F1), fib(N2, F2).

    colour(red).
    colour(green).

    args(L) :- current_prolog_flag(argv, L).

    main :- fib(10, F), write(F), nl.

    test("fib(10) = 55") :- fib(10, 55).

    :- end_module(prog).
""")


def _clausal(tmp_path, *argv):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "clausal", *argv], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=120)


@pytest.fixture
def prog(tmp_path):
    (tmp_path / "prog.clausal").write_text(PROG)
    return tmp_path


def test_main_0_runs_and_exits_0(prog):
    r = _clausal(prog, "prog.clausal")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "55\n"


def test_a_program_without_main_is_a_load_check(tmp_path):
    (tmp_path / "lib.clausal").write_text(
        ":- module(lib, [p/1]).\np(1).\n:- end_module(lib).\n")
    r = _clausal(tmp_path, "lib.clausal")
    assert (r.returncode, r.stdout) == (0, ""), r.stderr


def test_main_0_failing_exits_1(tmp_path):
    (tmp_path / "f.clausal").write_text(
        ":- module(f, []).\nmain :- 1 = 2.\n:- end_module(f).\n")
    r = _clausal(tmp_path, "f.clausal")
    assert r.returncode == 1
    assert "main/0 failed" in r.stderr


def test_a_program_that_does_not_load_exits_1(tmp_path):
    (tmp_path / "cut.clausal").write_text(
        ":- module(cut, [p/1]).\np(_) :- !.\n:- end_module(cut).\n")
    r = _clausal(tmp_path, "cut.clausal")
    assert r.returncode == 1
    assert "did not load" in r.stderr and "cut" in r.stderr


def test_g_prints_every_answer(prog):
    r = _clausal(prog, "-g", "colour(C)", "prog.clausal")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "C = red.\nC = green.\n"


def test_once_prints_the_first_answer(prog):
    r = _clausal(prog, "--once", "-g", "colour(C)", "prog.clausal")
    assert r.stdout == "C = red.\n"


def test_g_reads_the_programs_library_operators(prog):
    r = _clausal(prog, "-g", "X #= 3 * 4", "-g", "fib(10, F)",
                 "prog.clausal")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "X = 12.\nF = 55.\n"


def test_g_without_named_variables_prints_true(prog):
    r = _clausal(prog, "-g", "colour(red), _Unused = 1", "prog.clausal")
    assert (r.returncode, r.stdout) == (0, "true.\n"), r.stderr


def test_g_failing_prints_false_and_exits_1(prog):
    r = _clausal(prog, "-g", "colour(blue)", "prog.clausal")
    assert (r.returncode, r.stdout) == (1, "false.\n")


def test_g_raising_exits_1_with_the_error_term(prog):
    r = _clausal(prog, "-g", "atom_length(X, N)", "prog.clausal")
    assert r.returncode == 1
    assert "instantiation_error" in r.stderr


def test_g_syntax_error_is_a_usage_error(prog):
    r = _clausal(prog, "-g", "colour(", "prog.clausal")
    assert r.returncode == 2
    assert "syntax error" in r.stderr


def test_argv_is_what_follows_the_double_dash(prog):
    r = _clausal(prog, "-g", "args(L)", "prog.clausal", "--", "one", "2")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "L = [one,'2'].\n"


def test_argv_is_empty_without_arguments(prog):
    r = _clausal(prog, "-g", "args(L)", "prog.clausal")
    assert r.stdout == "L = [].\n"


def test_test_runs_the_programs_test_clauses(prog):
    r = _clausal(prog, "--test", "prog.clausal")
    assert r.returncode == 0, r.stderr
    assert "1 passed, 0 failed" in r.stdout


def test_an_iso_prolog_program_runs(tmp_path):
    (tmp_path / "count.pl").write_text(
        "len([], 0).\nlen([_|T], N) :- len(T, M), N is M + 1.\n"
        "main :- len([a, b, c], N), write(N), nl.\n")
    r = _clausal(tmp_path, "count.pl")
    assert (r.returncode, r.stdout) == (0, "3\n"), r.stderr


@pytest.mark.parametrize("argv, says", [
    (["notes.txt"], "a program is a .clausal or .pl file"),
    (["missing.clausal"], "no such file"),
    (["--once", "prog.clausal"], "--once applies to -g goals"),
    (["--test", "-g", "true", "prog.clausal"], "--test runs the program's tests"),
    (["-g", "true"], "need a FILE"),
])
def test_usage_errors_exit_2(prog, argv, says):
    if argv == ["notes.txt"]:
        (prog / "notes.txt").write_text("hello\n")
    r = _clausal(prog, *argv)
    assert r.returncode == 2
    assert says in r.stderr, r.stderr
