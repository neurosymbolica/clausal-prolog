"""The interactive ISO ``?-`` top-level (``clausal.toplevel``), driven through
a pseudo-terminal: one test per scenario of the Trealla comparison, with the
transcript pinned.  Piped-stdin cases use a plain pipe.
"""

from __future__ import annotations

import os
import pty
import re
import select
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

PROG = textwrap.dedent("""\
    :- use_module(library(clpz)).
    p(1). p(2). p(3).
    s("abc").
    side(X) :- member(X, [a, b]), write(side(X)), nl.
    spin(N) :- N1 is N + 1, spin(N1).
    loop :- spin(0).
    """)

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _env(home):
    env = dict(os.environ)
    env.pop("CLAUSAL_PL_FRONTEND", None)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["HOME"] = str(home)
    env["TERM"] = "xterm"
    return env


class Pty:
    """``clausal ARGS`` on a pty: ``send`` keystrokes, ``expect`` text."""

    def __init__(self, tmp_path, *argv):
        self.tmp = tmp_path
        self.buf = ""
        pid, self.fd = pty.fork()
        if pid == 0:
            os.chdir(tmp_path)
            # another test file may have left SIGINT ignored in this process
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            os.execvpe(sys.executable,
                       [sys.executable, "-m", "clausal", *argv],
                       _env(tmp_path))
        self.pid = pid
        self.status = None

    def _read(self, timeout):
        if select.select([self.fd], [], [], timeout)[0]:
            try:
                data = os.read(self.fd, 4096)
            except OSError:
                return False
            if not data:
                return False
            self.buf += data.decode("utf-8", "replace")
            return True
        return None

    def expect(self, text, timeout=10):
        end = time.time() + timeout
        while text not in self.text and time.time() < end:
            if self._read(0.2) is False:
                break
        assert text in self.text, f"{text!r} not in {self.text!r}"

    @property
    def text(self):
        return _ANSI.sub("", self.buf).replace("\r\n", "\n").replace("\r", "")

    def send(self, s):
        os.write(self.fd, s.encode())

    def query(self, q, wait):
        self.send(q + "\n")
        self.expect(wait)

    def finish(self, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            if self._read(0.2) is False:
                break
        _, st = os.waitpid(self.pid, 0)
        self.status = os.waitstatus_to_exitcode(st)
        return self.status

    def close(self):
        try:
            os.kill(self.pid, signal.SIGKILL)
            os.waitpid(self.pid, 0)
        except OSError:
            pass


@pytest.fixture
def tl(tmp_path):
    (tmp_path / "prog.pl").write_text(PROG)
    sessions = []

    def start(*argv):
        s = Pty(tmp_path, *(argv or ("prog.pl", "--toplevel")))
        sessions.append(s)
        s.expect("?- ")
        return s

    yield start
    for s in sessions:
        s.close()


def after_banner(s):
    return s.text.split("?- ", 1)[1]


# ── entry ─────────────────────────────────────────────────────────────────


def test_file_without_main_opens_prompt_on_a_terminal(tl):
    s = tl("prog.pl")                  # no --toplevel: a tty, no main/0
    assert "Clausal Prolog" in s.text
    s.send("halt.\n")
    assert s.finish() == 0


def test_bare_clausal_opens_the_prompt(tl):
    s = tl()
    s.send("halt.\n")
    assert s.finish() == 0


def test_bare_clausal_is_the_prompt_not_the_python_repl(tmp_path):
    s = Pty(tmp_path)
    s.expect("?- ")
    s.query("X = 1.", "X = 1.")
    s.send("halt(3).\n")
    assert s.finish() == 3


def test_python_switch_keeps_the_python_repl(tmp_path):
    s = Pty(tmp_path, "--python")
    try:
        s.expect(">>>", timeout=60)
    finally:
        s.close()


# ── answers ───────────────────────────────────────────────────────────────


def test_deterministic_answer(tl):
    s = tl()
    s.query("X = 1.", "   X = 1.\n")
    s.send("halt.\n")


def test_true_and_false(tl):
    s = tl()
    s.query("true.", "   true.\n")
    s.query("fail.", "   false.\n")
    s.send("halt.\n")


def test_member_steps_with_semicolon(tl):
    s = tl()
    s.send("member(X, [a,b,c]).\n")
    s.expect("   X = a")
    s.send(";")
    s.expect(";  X = b")
    s.send(";")
    s.expect(";  X = c")
    s.send(";")
    s.expect(";  false.")
    assert "X = a\n;  X = b\n;  X = c\n;  false.\n" in s.text


def test_space_and_n_are_next(tl):
    s = tl()
    s.send("p(X).\n")
    s.expect("   X = 1")
    s.send(" ")
    s.expect(";  X = 2")
    s.send("n")
    s.expect(";  X = 3")


def test_enter_stops(tl):
    s = tl()
    s.send("p(X).\n")
    s.expect("   X = 1")
    s.send("\r")
    s.expect(";  ... .")
    s.query("X = 2.", "   X = 2.")


def test_dot_stops(tl):
    s = tl()
    s.send("p(X).\n")
    s.expect("   X = 1")
    s.send(".")
    s.expect(";  ... .")


def test_a_prints_all(tl):
    s = tl()
    s.send("p(X).\n")
    s.expect("   X = 1")
    s.send("a")
    s.expect(";  X = 3")
    assert "X = 1\n;  X = 2\n;  X = 3" in s.text


def test_f_shows_five_more_and_hash_n(tl):
    s = tl()
    s.send("between(1, 20, X).\n")
    s.expect("   X = 1")
    s.send("f")
    s.expect("X = 6")
    assert "X = 2" in s.text and "X = 7" not in s.text
    s.send("#")
    s.send("3\r")
    s.expect("X = 9")
    assert "X = 10" not in after_banner(s)


def test_help_key_is_help_not_next(tl):
    s = tl()
    s.send("p(X).\n")
    s.expect("   X = 1")
    s.send("h")
    s.expect("Action:")
    assert "X = 2" not in s.text
    s.send("?")
    s.send(";")
    s.expect(";  X = 2")


def test_ctrl_c_at_answer_prompt_stops_never_next(tl):
    s = tl()
    s.send("p(X).\n")
    s.expect("   X = 1")
    time.sleep(0.3)
    s.send("\x03")
    s.expect(";  ... .")
    assert "X = 2" not in s.text


def test_unknown_key_is_ignored(tl):
    s = tl()
    s.send("p(X).\n")
    s.expect("   X = 1")
    s.send("z")
    s.send(";")
    s.expect(";  X = 2")


def test_next_solution_computed_only_on_request(tl):
    s = tl()
    s.send("side(X).\n")
    s.expect("   X = a")
    assert "side(b)" not in s.text
    s.send(".")
    s.expect(";  ... .")
    assert "side(b)" not in s.text


def test_length_enumerates(tl):
    s = tl()
    s.send("length(L, N).\n")
    s.expect("   L = [], N = 0")
    s.send(";")
    s.expect(";  L = [_")


# ── printing ──────────────────────────────────────────────────────────────


def test_sharing_cycles_strings_operators(tl):
    s = tl()
    s.query("X = f(Y,Z), Y = Z, W = V.", "   X = f(Y,Y), Z = Y, V = W.")
    s.query("X = f(X).", "   X = f(...).")
    s.query("s(S).", '   S = "abc"')
    s.send("\r")
    s.expect(";  ... .")
    s.query("X = 1+2*3.", "   X = 1+2*3.")
    s.query("X = 1+2*3, Y = (a:-b,c).", "   X = 1+2*3, Y = (a:-b,c).")


def test_underscore_variables_are_hidden(tl):
    s = tl()
    s.query("_A = 1, B = 2.", "   B = 2.")


def test_variables_in_order_of_appearance(tl):
    s = tl()
    s.query("Y = 1, X = 2.", "   Y = 1, X = 2.")


def test_residual_dif_and_clpz(tl):
    s = tl()
    s.query("dif(X, a).", "   dif(X,a).")
    s.query("X #> 3, X #< 6.", "   X in 4..5.")


def test_long_list_is_elided_and_w_prints_in_full(tl):
    s = tl()
    s.send("numlist(1, 150, L).\n")
    s.expect("100|...]")
    assert "101" not in after_banner(s)
    s.send("w")
    s.expect("150]")
    s.send("p")
    s.expect("100|...]")


# ── errors and recovery ───────────────────────────────────────────────────


def test_errors_are_one_line(tl):
    s = tl()
    s.query("foo(1).", "   error(existence_error(procedure,foo/1),foo/1).")
    s.query("atom_length(1, X).", "   error(type_error(atom,1),atom_length/2).")
    assert "Traceback" not in s.text


def test_syntax_error_recovers(tl):
    s = tl()
    s.query("foo bar baz.", "error(syntax_error(")
    s.query("X = 1.", "   X = 1.")


def test_multiline_query(tl):
    s = tl()
    s.send("X = 1,\n")
    s.expect("|    ")
    s.send("Y = 2.\n")
    s.expect("   X = 1, Y = 2.")


def test_dot_inside_quotes_and_comments_does_not_end_a_query(tl):
    s = tl()
    s.query("X = 'a. b'. % trailing", "   X = 'a. b'.")
    s.query("X = 1.5.", "   X = 1.5.")


def test_ctrl_c_during_search_returns_to_prompt(tl):
    s = tl()
    s.send("loop.\n")
    time.sleep(3)
    s.send("\x03")
    s.expect("% Execution Aborted")
    s.expect("?- ")
    s.query("X = 1.", "   X = 1.")


# ── commands ──────────────────────────────────────────────────────────────


def test_consult_and_bracket_load(tl, tmp_path):
    (tmp_path / "extra.pl").write_text("r(42).\n")
    s = tl()
    s.query("consult(extra).", "   true.")
    s.query("r(X).", "   X = 42")
    s.send("\r")
    s.expect(";  ... .")
    s.query("[extra].", "   true.")
    s.query("consult(nonesuch).", "existence_error(source_sink,nonesuch)")


def test_halt_forms(tl):
    s = tl()
    s.send("halt.\n")
    assert s.finish() == 0


def test_halt_status(tl):
    s = tl()
    s.send("halt(5).\n")
    assert s.finish() == 5


def test_ctrl_d_exits(tl):
    s = tl()
    s.send("\x04")
    assert s.finish() == 0


def test_history_file_is_written(tl, tmp_path):
    s = tl()
    s.send("halt.\n")
    s.finish()
    # the history file exists once readline is available (best effort)
    try:
        import readline  # noqa: F401
    except ImportError:
        pytest.skip("no readline")
    assert (tmp_path / ".clausal_history").exists()


# ── cut, ->, *-> in queries (operator ruling 2026-10-24) ─────────────────


def _clausal_file(tmp_path):
    (tmp_path / "m.clausal").write_text(
        ":- module(m, [a/1]).\na(1). a(2).\n:- end_module(m).\n")


def test_pl_file_accepts_cut_and_if_then_else(tl):
    s = tl()                            # prog.pl, no --prolog
    s.query("p(X), !.", "   X = 1.")
    s.query("(p(X) -> true ; fail).", "   X = 1")


def test_clausal_file_refuses_cut_arrow_and_softcut(tmp_path):
    _clausal_file(tmp_path)
    s = Pty(tmp_path, "m.clausal", "--toplevel")
    try:
        s.expect("?- ")
        s.query("a(X), !.", "syntax_error(cut_free)")
        s.query("(a(X) -> true ; fail).", "syntax_error(cut_free)")
        s.query("X = 1.", "   X = 1.")
    finally:
        s.close()


def test_prolog_flag_accepts_them_with_no_file(tmp_path):
    s = Pty(tmp_path, "--prolog")
    try:
        s.expect("?- ")
        s.query("true, !.", "   true.")
    finally:
        s.close()


def test_no_file_refuses_cut(tmp_path):
    s = Pty(tmp_path)
    try:
        s.expect("?- ")
        s.query("true, !.", "syntax_error(cut_free)")
    finally:
        s.close()


def test_control_symbols_as_data_are_not_refused(tmp_path):
    _clausal_file(tmp_path)
    s = Pty(tmp_path, "m.clausal", "--toplevel")
    try:
        s.expect("?- ")
        s.query("X = '!'.", "   X = !.")
        s.query("X = (a -> b).", "   X = (a->b).")
        s.query("X = [!, foo].", "   X = [!,foo].")
    finally:
        s.close()


def test_a_cut_commits_only_the_goals_before_it(tl):
    s = tl()
    s.send("!, member(X, [a,b,c]).\n")
    s.expect("   X = a")
    s.send(";")
    s.expect(";  X = b")
    s.send("\r")
    s.query("X = 1, !, member(Y, [p,q]).", "   X = 1, Y = p")
    s.send(";")
    s.expect(";  X = 1, Y = q")


# ── review fixes (2026-10-24) ─────────────────────────────────────────


def test_ctrl_c_at_the_prompt_drops_the_line_and_stays(tl):
    s = tl()
    s.send("foo(")
    time.sleep(0.3)
    s.send("\x03")
    time.sleep(0.5)
    assert "Traceback" not in s.text
    s.query("X = 1.", "   X = 1.")


def test_consult_errors_are_one_line(tl, tmp_path):
    (tmp_path / "bad.pl").write_text("p(.\n")
    s = tl()
    s.query("consult(nonexist).",
            "error(existence_error(source_sink,nonexist),consult/1).")
    s.query("[X].", "error(instantiation_error,consult/1).")
    s.query("consult(bad).", "   error(")
    s.query("consult(1).", "error(type_error(atom,1),consult/1).")
    assert "Traceback" not in s.text
    s.query("X = 1.", "   X = 1.")


def test_history_recalls_a_query(tl, tmp_path):
    s = tl()
    s.query("X = 12345.", "   X = 12345.")
    s.send("\x1b[A")
    time.sleep(0.5)
    s.send("\n")
    deadline = time.time() + 10
    while s.text.count("   X = 12345.") < 2 and time.time() < deadline:
        s._read(0.2)
    # the query echo, its answer, the recalled echo, its answer
    assert s.text.count("   X = 12345.") == 2, s.text
    s.send("halt.\n")
    s.finish()
    assert "X = 12345." in (tmp_path / ".clausal_history").read_text()


def test_relational_clpfd_constraints_are_printed(tl):
    s = tl()
    s.query("X #> Y.", "   Y #< X.")


def test_dif_on_an_underscore_variable_is_shown(tl):
    s = tl()
    s.query("dif(_A, a).", "   dif(_A,a).")


def test_a_ball_that_is_no_error_prints_as_throw(tl):
    s = tl()
    s.query("throw(foo).", "   throw(foo).")


def test_trailing_comment_after_the_end_does_not_continue(tl):
    s = tl()
    s.send("X = 1. % a comment\n")
    s.expect("   X = 1.\n?- ")
    assert "|    " not in s.text


def test_halt_with_a_non_integer_is_an_error(tl):
    s = tl()
    s.query("halt(foo).", "error(type_error(integer,foo),halt/1).")
    s.query("X = 1.", "   X = 1.")


def test_e_leaves_the_top_level(tl):
    s = tl()
    s.send("p(X).\n")
    s.expect("   X = 1")
    s.send("e")
    assert s.finish() == 0


def test_cyclic_list_is_not_unrolled(tl):
    s = tl()
    s.query("X = [1,2|X].", "   X = [1,2|...].")


def test_bracket_prefers_clausal_over_pl(tl, tmp_path):
    (tmp_path / "both.pl").write_text("w(from_pl).\n")
    (tmp_path / "both.clausal").write_text(
        ":- module(both, [w/1]).\nw(from_clausal).\n:- end_module(both).\n")
    s = tl()
    s.query("[both].", "   true.")
    s.query("w(X).", "   X = from_clausal")


def test_toplevel_flag_conflicts_exit_2(tmp_path):
    for argv in (["--toplevel", "-g", "true", "prog.pl"],
                 ["--toplevel", "--python"]):
        r = subprocess.run(
            [sys.executable, "-m", "clausal", *argv], cwd=tmp_path,
            env=_env(tmp_path), capture_output=True, text=True, timeout=60)
        assert r.returncode == 2, (argv, r.stderr)


# ── piped stdin ───────────────────────────────────────────────────────────


def _piped(tmp_path, stdin, *argv):
    (tmp_path / "prog.pl").write_text(PROG)
    return subprocess.run(
        [sys.executable, "-m", "clausal", *(argv or ("prog.pl", "--toplevel"))],
        input=stdin, cwd=tmp_path, env=_env(tmp_path),
        capture_output=True, text=True, timeout=120)


def test_piped_prints_first_answer_of_each_query(tmp_path):
    r = _piped(tmp_path, "p(X).\nX = 7.\nfail.\n")
    assert r.stdout == "   X = 1.\n   X = 7.\n   false.\n"
    assert r.returncode == 0


def test_piped_eof_is_clean(tmp_path):
    r = _piped(tmp_path, "member(X, [a,b]).")
    assert r.stdout == "   X = a.\n"
    assert "Traceback" not in r.stderr


def test_piped_next_line_is_not_eaten(tmp_path):
    r = _piped(tmp_path, "p(X).\np(Y).\n")
    assert r.stdout == "   X = 1.\n   Y = 1.\n"


def test_piped_nondeterministic_query_does_not_loop(tmp_path):
    r = _piped(tmp_path, "between(1, 1000000, X).\n")
    assert r.stdout == "   X = 1.\n"


def test_piped_bare_clausal(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "clausal"], input="X = 1.\nhalt.\n",
        cwd=tmp_path, env=_env(tmp_path), capture_output=True, text=True,
        timeout=120)
    assert r.stdout == "   X = 1.\n"
