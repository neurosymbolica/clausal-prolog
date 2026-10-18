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


def _clausal(tmp_path, *argv, **extra_env):
    env = dict(os.environ)
    env.pop("CLAUSAL_PL_FRONTEND", None)
    env.update(extra_env)
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


#: Ulrich's conformity rows #186 and #187: ISO block comments do not nest,
#: so ``/*`` closes at the first ``*/``. A -g goal is read as a file is
#: (``PL_SOURCE_NESTED_COMMENTS``), not with the reader's nesting default.
@pytest.mark.parametrize("goal", ["X/* /*/=7", "X/*/*/=7"])
def test_g_block_comments_do_not_nest(prog, goal):
    r = _clausal(prog, "-g", goal, "prog.clausal")
    assert (r.returncode, r.stdout) == (0, "X = 7.\n"), r.stderr


#: Ulrich's conformity row #224: a goal is read as a term, as a toplevel
#: reads it (priority 1201, ISO 6.2), so a lone operator atom is a goal.
#: Wrapping it as the operand of the prefix operator ?- refused it.
def test_g_a_lone_prefix_operator_atom_is_a_goal(prog):
    r = _clausal(prog, "-g", "\\ .", "prog.clausal")
    assert r.returncode == 1, r.stderr
    assert "existence_error(procedure,(\\)/0)" in r.stderr


def test_g_an_operator_atom_is_still_no_operand(prog):
    # ISO 6.3.4.3: a bare operator atom has priority 1201, above any operand.
    r = _clausal(prog, "-g", "X = \\ .", "prog.clausal")
    assert r.returncode == 2
    assert "syntax error" in r.stderr


def test_g_a_bracketed_operator_atom_is_an_operand(prog):
    r = _clausal(prog, "-g", "X = (\\), atom(X)", "prog.clausal")
    assert r.returncode == 0, r.stderr


def test_g_an_unclosed_block_comment_is_still_a_syntax_error(prog):
    r = _clausal(prog, "-g", "X = /* 7", "prog.clausal")
    assert r.returncode == 2
    assert "unterminated block comment" in r.stderr


def test_g_reads_the_programs_operators_past_a_comment_with_slash_star(tmp_path):
    # The program is scanned for its op/3 directives with the file reader's
    # comment rule too: a nesting scan would read the rest of the file as
    # comment and miss the operator.
    (tmp_path / "ops.pl").write_text(
        "/* a /* b */\n:- op(200, xfx, ~~).\n")
    r = _clausal(tmp_path, "-g", "_X = (a ~~ b), _X =.. L", "ops.pl")
    assert (r.returncode, r.stdout) == (0, "L = [~~,a,b].\n"), r.stderr


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


# ── answers: rationals, unbound variables, CLP(Q) residuals (2026-10-11) ──

CLPQ = textwrap.dedent("""\
    :- use_module(library(clpq)).
    dependent(X, Y) :- {X + Y = 3, 2*X + 2*Y = 6}.
    between_1_3(X) :- {X > 1, X < 3}.
    not_two(X) :- {X =\\= 2}.
    at_least_2(X) :- {X >= 2}.
    hidden(X) :- {X + Y = 3}, Y = Y.
    inside(S) :- {X + Y = 3}, S = f(X, Y).
    halves(S) :- {2*X = 1, 3*Y = 1}, S = X-Y.
    lin(A-B-C, D-E-F, X-Y) :- {A*X + B*Y = C, D*X + E*Y = F}.
""")


#: Task 14, output spelling: under CLAUSAL_CLPQ=holzbaur a residual is what
#: 1.3.3's dump/3 gives, in Clausal's braces, and so is Scryer's clpq
#: answer: {X + Y = 3} dumps [x=3-y], {X =\= 2} [x=2+_A,_A=\=0], and
#: {X >= 2}, {Y >= 2} dumps [y>=2,x>=2].  An internal variable is _Q1, as
#: legacy names one.
HOLZBAUR = os.environ.get("CLAUSAL_CLPQ", "legacy") == "holzbaur"
DEPENDENT = "{X = 3 - Y}." if HOLZBAUR else "{X + Y = 3}."


@pytest.fixture
def clpq_prog(tmp_path):
    (tmp_path / "lin.clausal").write_text(CLPQ)
    return tmp_path


@pytest.mark.parametrize("goal, answer", [
    ("X is 1 rdiv 2", "X = 1 rdiv 2."),
    ("X is -3 rdiv 2, Y = f(1-X, 2*X)", "X = -3 rdiv 2, Y = f(1- -3 rdiv 2,2*(-3 rdiv 2))."),
    ("halves(S)", "S = 1 rdiv 2-1 rdiv 3."),
    ("lin(1-1-3, 1-(-1)-1, S)", "S = 2-1."),
    ("dependent(X, Y)", DEPENDENT),
    ("between_1_3(X)", "{X > 1}, {X < 3}."),
    ("not_two(X)", "{X = 2 + _Q1}, {_Q1 =\\= 0}." if HOLZBAUR
     else "{X =\\= 2}."),
    ("at_least_2(X), at_least_2(Y)", "{Y >= 2}, {X >= 2}." if HOLZBAUR
     else "{X >= 2}, {Y >= 2}."),
    # Y is free once X is: projecting X + Y = 3 onto X leaves nothing.
    ("hidden(X)", "true."),
    ("inside(S)", None),
    ("X = f(Y)", "X = f(Y)."),
    ("X = Y", "Y = X."),
    ("X = _", "true."),
])
def test_g_answer_spelling(clpq_prog, goal, answer):
    r = _clausal(clpq_prog, "-g", goal, "lin.clausal")
    assert r.returncode == 0, r.stderr
    if answer is None:
        # S = f(_A, _B) and the constraint on the same two variables.
        line = r.stdout.strip()
        assert line.startswith("S = f(_") and "{_" in line, line
        names = line[len("S = f("):line.index(")")].split(",")
        constraint = (f"{names[0]} = 3 - {names[1]}" if HOLZBAUR
                      else f"{names[0]} + {names[1]} = 3")
        assert line.endswith(f", {{{constraint}}}."), line
    else:
        assert r.stdout == answer + "\n"


def test_g_clpq_answers_in_the_sandbox(clpq_prog):
    r = _clausal(clpq_prog, "-g", "dependent(X, Y)", "lin.clausal",
                 CLAUSAL_SANDBOX="1")
    assert (r.returncode, r.stdout) == (0, DEPENDENT + "\n"), r.stderr


@pytest.mark.parametrize("frontend", ["translator", "native"])
def test_a_pl_program_imports_library_clpq(tmp_path, frontend):
    # The translator read library(clpq) as a module named clpq ("No module
    # named 'clpq'"), and `{A = B, C = D}` as one set-goal element.
    (tmp_path / "lin.pl").write_text(CLPQ)
    r = _clausal(tmp_path, "-g", "dependent(X, Y)", "-g", "between_1_3(X)",
                 "lin.pl", CLAUSAL_PL_FRONTEND=frontend)
    assert (r.returncode, r.stdout) == (
        0, DEPENDENT + "\n{X > 1}, {X < 3}.\n"), r.stderr
