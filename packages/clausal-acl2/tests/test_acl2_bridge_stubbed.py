"""clausal-acl2 without ACL2: the term mapping, and the bridge protocol
against a fake server.

Runs without an ACL2 installation (``*_stubbed.py``): ``FakeBridge`` speaks
the protocol of ``books/centaur/bridge/bridge-raw.lsp`` -- an
``ACL2_BRIDGE_HELLO`` message, then ``READY`` before each command; commands
and replies are ``TYPE LEN\\nCONTENT\\n`` with LEN in characters; a command
answers with any ``STDOUT`` messages, then ``RETURN`` (``prin1`` of the first
value for ``LISP``, of the value list for ``LISP_MV``) or ``ERROR``.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from fractions import Fraction

import pytest

from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, deref, unify
from clausal.modules.py import acl2 as pyacl2
from clausal.terms import DictTerm


# ── the term mapping ─────────────────────────────────────────────────────

@pytest.mark.parametrize("text, term", [
    ("FOO", "foo"),
    ("NIL", "nil"),
    ("T", "t"),
    (":KEYWORD", ":keyword"),
    ("VL::FOO", "vl::foo"),
    ("|foo bar|", "|foo bar|"),
    ("COMMON-LISP::CAR", "car"),
    ("42", 42),
    ("-7", -7),
    ("-1/2", Fraction(-1, 2)),
    ("4/2", 2),
    ('"a \\"quoted\\" string"', chars('a "quoted" string')),
    ("#\\a", ("$char", "a")),
    ("#\\Space", ("$char", " ")),
    ("#C(1 -1/2)", ("$complex", 1, Fraction(-1, 2))),
    ("(IMPLIES (TRUE-LISTP X) (EQUAL (REV (REV X)) X))",
     ("implies", ("true-listp", "x"), ("equal", ("rev", ("rev", "x")), "x"))),
    ("(F)", ("()", "f")),
    ("(1 2 3)", ("()", 1, 2, 3)),
    ("(A . B)", ("$cons", "a", "b")),
    ("(A B . C)", ("$cons", "a", ("$cons", "b", "c"))),
    ("'X", ("quote", "x")),
])
def test_from_lisp(text, term):
    assert pyacl2.from_lisp(text) == term


@pytest.mark.parametrize("term", [
    "foo", "nil", ":keyword", "vl::foo", "|foo bar|", 42, Fraction(3, 4),
    chars('say "hi"'), ("$char", "a"), ("$char", " "),
    ("$complex", 1, 2),
    ("implies", ("true-listp", "x"), ("equal", ("rev", ("rev", "x")), "x")),
    ("()", "f"), ("()", 1, 2), ("$cons", "a", "b"),
    ("defun", "app", ("x", "y"), ("if", ("endp", "x"), "y", ("cons", ("car", "x"), ("app", ("cdr", "x"), "y")))),
])
def test_round_trip(term):
    """Every canonical term prints to ACL2 text that reads back as itself."""
    assert pyacl2.from_lisp(pyacl2.to_lisp(term)) == term


def test_to_lisp_spellings():
    assert pyacl2.to_lisp(("equal", ("+", 1, 2), 3)) == "(EQUAL (+ 1 2) 3)"
    assert pyacl2.to_lisp(["a", "b", [1, Fraction(1, 2)]]) == "(A B (1 1/2))"
    assert pyacl2.to_lisp([]) == "NIL"
    assert pyacl2.to_lisp("Mixed") == "|Mixed|"
    assert pyacl2.to_lisp("123") == "|123|"
    assert pyacl2.to_lisp(chars("x\\y")) == '"x\\\\y"'


def test_to_lisp_refuses_what_acl2_cannot_hold():
    with pytest.raises(LogicException) as info:
        pyacl2.to_lisp(("f", Var()))
    assert info.value.term[1] == "instantiation_error"
    with pytest.raises(LogicException) as info:
        pyacl2.to_lisp(DictTerm({"a": 1}))
    assert info.value.term[1][:2] == ("type_error", "acl2_term")


def test_to_lisp_follows_bindings():
    x = Var()
    unify(x, ("car", "y"), Trail())
    assert pyacl2.to_lisp(("cons", x, "nil")) == "(CONS (CAR Y) NIL)"


# ── a fake ACL2 Bridge ───────────────────────────────────────────────────

class FakeBridge:
    """A Unix-socket server with the ACL2 Bridge's protocol.  ``replies``
    maps a command's exact text to ``(stdout, return_text)``, or to an
    exception message for an ERROR reply.  ``delays`` maps a command's text
    to seconds to wait before replying; a command in ``hangups`` closes the
    connection instead of replying (the bridge died mid-command)."""

    def __init__(self, replies, delays=None, hangups=()):
        self.replies = replies
        self.delays = delays or {}
        self.hangups = set(hangups)
        self.commands = []
        self.dir = tempfile.mkdtemp(prefix="fake_bridge_")
        self.path = os.path.join(self.dir, "s")
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(4)
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._worker, args=(conn,), daemon=True).start()

    @staticmethod
    def _send(w, kind, content):
        w.write(f"{kind} {len(content)}\n{content}\n")

    def _worker(self, conn):
        try:
            self._converse(conn)
        except (OSError, ValueError):
            pass                       # the client hung up

    def _converse(self, conn):
        r = conn.makefile("r", encoding="utf-8", newline="")
        w = conn.makefile("w", encoding="utf-8", newline="")
        self._send(w, "ACL2_BRIDGE_HELLO", "worker-1")
        while True:
            self._send(w, "READY", "")
            w.flush()
            header = r.readline()
            if not header:
                return
            kind, length = header.split()
            text = r.read(int(length))
            r.read(1)
            self.commands.append((kind, text))
            if text in self.hangups:
                conn.close()
                return
            if text in self.delays:
                time.sleep(self.delays[text])
            reply = self.replies.get(text)
            if reply is None:
                self._send(w, "ERROR", f"Error executing command {text}:\nunknown")
            elif isinstance(reply, str):
                self._send(w, "ERROR", reply)
            else:
                stdout, returned = reply
                if stdout:
                    self._send(w, "STDOUT", stdout)
                self._send(w, "RETURN", returned)
            w.flush()

    def close(self):
        self.server.close()


def ld_text(event):
    return pyacl2._ld_form(event)


# What ``ld`` with ``:ld-error-action :return!`` answers (ACL2 8.7, measured
# against a real ACL2): ``(NIL :EOF state)`` when every form was accepted,
# ``(NIL (:STOP-LD n) state)`` when one was rejected -- ERP is NIL both ways.
LD_OK = "(NIL :EOF ACL2_INVISIBLE::|The Live State Itself|)"
LD_REJECTED = "(NIL (:STOP-LD 2) ACL2_INVISIBLE::|The Live State Itself|)"


@pytest.fixture
def bridge():
    fake = FakeBridge({
        "(+ 1 2)": ("", "3"),
        "(APPEND (QUOTE (A B)) (QUOTE (C)))": ("", "(A B C)"),
        "(CW \"hi~%\")": ("hi\n", "NIL"),
        "(MV 1 :TWO \"three\")": ("", '(1 :TWO "three")'),
        "(CAR 3)": "Error executing command (CAR 3):\nThe value 3 is not of type LIST",
        "(REV (QUOTE (1 2 \"é\")))": ("", '("é" 2 1)'),
        ld_text("(THM (EQUAL (REV (REV X)) X))"): ("Q.E.D.\n", LD_OK),
        ld_text("(THM (EQUAL X 1))"): ("******** FAILED ********\n", LD_REJECTED),
        ld_text("(DEFUN SQ (X) (* X X))"):
            ("Since SQ is non-recursive, its admission is trivial.\n", LD_OK),
        ld_text("(DEFUN SPIN (X Y) (SPIN X Y))"):
            ("ACL2 Error in ( DEFUN SPIN ...):  No :MEASURE was supplied\n",
             LD_REJECTED),
        ld_text("(DEFUN BAD)"):
            ("ACL2 Error in macro expansion of (DEFUN BAD)\n", LD_REJECTED),
        ld_text("(DEFTHM NOPE (EQUAL X 1))"):
            ("******** FAILED ********\n", LD_REJECTED),
        ld_text("(THM (EQUAL X 2))"):        # ld's own error triple: ERP non-NIL
            ("", "(T NIL ACL2_INVISIBLE::|The Live State Itself|)"),
        "(SLEEP 1)": ("", "NIL"),
    }, delays={"(SLEEP 1)": 1.0}, hangups={"(DIE)"})
    pyacl2._reset({"socket": fake.path})
    yield fake
    pyacl2._reset()
    fake.close()


def solutions(fn, *args):
    out = []
    for _ in fn(*args, Trail(), None):
        out.append(tuple(deref(a) for a in args))
    return out


def test_acl2_evaluates_a_form(bridge):
    [sol] = solutions(pyacl2._acl2_2, ("+", 1, 2), Var())
    assert sol[1] == 3
    [sol] = solutions(pyacl2._acl2_2, ("append", ("quote", ["a", "b"]), ("quote", ["c"])), Var())
    assert sol[1] == ("a", "b", "c")
    assert bridge.commands[0] == ("LISP", "(+ 1 2)")


def test_acl2_3_collects_what_acl2_printed(bridge):
    [sol] = solutions(pyacl2._acl2_3, ("cw", chars("hi~%")), Var(), Var())
    assert sol[1] == "nil" and sol[2] == chars("hi\n")


def test_acl2_mv_answers_every_value(bridge):
    [sol] = solutions(pyacl2._acl2_mv_2, ("mv", 1, ":two", chars("three")), Var())
    assert sol[1] == [1, ":two", chars("three")]
    assert bridge.commands[-1][0] == "LISP_MV"


def test_lengths_count_characters_not_bytes(bridge):
    [sol] = solutions(pyacl2._acl2_2, ("rev", ("quote", [1, 2, chars("é")])), Var())
    assert sol[1] == ("()", chars("é"), 2, 1)


def test_an_acl2_error_raises(bridge):
    with pytest.raises(LogicException) as info:
        solutions(pyacl2._acl2_2, ("car", 3), Var())
    assert info.value.term[1][0] == "acl2_error"


def test_thm_succeeds_when_acl2_proves_it(bridge):
    assert solutions(pyacl2._thm_1, ("equal", ("rev", ("rev", "x")), "x")) != []
    assert bridge.commands[-1] == ("LISP_MV", ld_text("(THM (EQUAL (REV (REV X)) X))"))


def test_thm_fails_when_acl2_cannot(bridge):
    assert solutions(pyacl2._thm_1, ("equal", "x", 1)) == []
    assert solutions(pyacl2._thm_2, ("equal", "x", 1), Var()) == []


def test_thm_fails_when_ld_signals_an_error(bridge):
    assert solutions(pyacl2._thm_1, ("equal", "x", 2)) == []


def test_event_fails_on_a_rejected_event(bridge):
    spin = ("defun", "spin", ("()", "x", "y"), ("spin", "x", "y"))
    assert solutions(pyacl2._event_1, spin) == []
    assert solutions(pyacl2._event_2, spin, Var()) == []
    assert solutions(pyacl2._event_1, ("()", "defun", "bad")) == []
    assert solutions(pyacl2._event_1, ("defthm", "nope", ("equal", "x", 1))) == []


def test_thm_2_answers_the_proof_output(bridge):
    [sol] = solutions(pyacl2._thm_2, ("equal", ("rev", ("rev", "x")), "x"), Var())
    assert sol[1] == chars("Q.E.D.\n")


def test_event_admits_a_definition(bridge):
    [sol] = solutions(pyacl2._event_2, ("defun", "sq", ("()", "x"), ("*", "x", "x")), Var())
    assert "admission is trivial" in sol[1][1]


def test_no_bridge_is_an_existence_error(tmp_path):
    pyacl2._reset({"socket": str(tmp_path / "nothing")})
    try:
        with pytest.raises(LogicException) as info:
            solutions(pyacl2._acl2_2, ("+", 1, 2), Var())
        assert info.value.term[1][:2] == ("existence_error", "acl2_bridge")
    finally:
        pyacl2._reset()


def test_a_bridge_that_dies_is_an_existence_error_then_reconnects(bridge):
    with pytest.raises(LogicException) as info:
        solutions(pyacl2._acl2_2, ("die",), Var())
    assert info.value.term[1][:2] == ("existence_error", "acl2_bridge")
    assert pyacl2._bridge is None              # the dead connection is dropped
    [sol] = solutions(pyacl2._acl2_2, ("+", 1, 2), Var())
    assert sol[1] == 3


def test_timeout_bounds_connecting_not_a_call(bridge):
    pyacl2._reset({"socket": bridge.path, "timeout": 0.2})
    [sol] = solutions(pyacl2._acl2_2, ("sleep", 1), Var())
    assert sol[1] == "nil"
    [sol] = solutions(pyacl2._acl2_2, ("+", 1, 2), Var())
    assert sol[1] == 3


def test_use_acl2_names_the_bridge(bridge):
    solutions(pyacl2._use_acl2_1, DictTerm({"socket": chars(bridge.path)}))
    assert pyacl2._settings == {"socket": bridge.path}
    [sol] = solutions(pyacl2._acl2_2, ("+", 1, 2), Var())
    assert sol[1] == 3


@pytest.mark.parametrize("options, error", [
    ({"bogus": 1}, ("domain_error", "acl2_option", "bogus")),
    ({"socket": 3}, ("type_error", "text", 3)),
    ({"port": chars("x")}, ("type_error", "integer", chars("x"))),
    ({"timeout": chars("x")}, ("type_error", "number", chars("x"))),
    ({"timeout": -1}, ("domain_error", "positive_number", -1)),
    ({"startup_timeout": -1}, ("domain_error", "positive_number", -1)),
])
def test_use_acl2_refuses_a_bad_option(options, error):
    pyacl2._reset({"socket": "/nonexistent"})
    with pytest.raises(LogicException) as info:
        solutions(pyacl2._use_acl2_1, DictTerm(options))
    assert info.value.term[1] == error
    assert pyacl2._settings == {"socket": "/nonexistent"}   # left unchanged
    pyacl2._reset()


# ── an ACL2 started here (a fake `acl2` command) ─────────────────────────

# Reads the two lines the package writes to a started ACL2's stdin, serves
# the bridge protocol at the socket path named by `(bridge::start "...")`,
# and keeps a child process in its process group, as a shell wrapper around
# Lisp would.  Answers "(+ 1 2)" with 3.
_FAKE_ACL2 = textwrap.dedent(r"""
    import os, re, socket, subprocess, sys, threading
    sys.stdin.readline()
    path = re.search(r'"(.*)"', sys.stdin.readline()).group(1)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    with open(os.path.join(os.path.dirname(path), "child.pid"), "w") as f:
        f.write(str(child.pid))
    def send(w, kind, content):
        w.write(f"{kind} {len(content)}\n{content}\n")
    def serve(conn):
        r = conn.makefile("r", encoding="utf-8", newline="")
        w = conn.makefile("w", encoding="utf-8", newline="")
        send(w, "ACL2_BRIDGE_HELLO", "worker")
        while True:
            send(w, "READY", "")
            w.flush()
            header = r.readline()
            if not header:
                return
            kind, length = header.split()
            text = r.read(int(length)); r.read(1)
            if text == "(EXIT)":
                os._exit(0)
            send(w, "RETURN", "3" if text == "(+ 1 2)" else "NIL")
            w.flush()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(4)
    while True:
        conn, _ = server.accept()
        threading.Thread(target=serve, args=(conn,), daemon=True).start()
""")


@pytest.fixture
def fake_acl2(tmp_path):
    exe = tmp_path / "fake-acl2"
    exe.write_text(f"#!{sys.executable}\n{_FAKE_ACL2}")
    exe.chmod(0o755)
    return str(exe)


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # a zombie is not running
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def _wait_gone(pid, seconds=10.0):
    deadline = time.monotonic() + seconds
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    return not _alive(pid)


def _child_pid(launched):
    with open(os.path.join(os.path.dirname(launched.socket_path), "child.pid")) as f:
        return int(f.read())


def test_a_started_acl2_that_dies_is_restarted(fake_acl2):
    pyacl2._reset({"command": fake_acl2})
    try:
        [sol] = solutions(pyacl2._acl2_2, ("+", 1, 2), Var())
        first = pyacl2._launched.proc.pid
        first_child = _child_pid(pyacl2._launched)
        with pytest.raises(LogicException) as info:
            solutions(pyacl2._acl2_2, ("exit",), Var())
        assert info.value.term[1][:2] == ("existence_error", "acl2_bridge")
        [sol] = solutions(pyacl2._acl2_2, ("+", 1, 2), Var())
        assert sol[1] == 3
        assert pyacl2._launched.proc.pid != first
        assert _wait_gone(first) and _wait_gone(first_child)
    finally:
        pyacl2._reset()


def test_reset_stops_a_started_acl2_and_its_process_group(fake_acl2):
    pyacl2._reset({"command": fake_acl2})
    pyacl2._get_bridge("test")
    launched = pyacl2._launched
    child = _child_pid(launched)
    pyacl2._reset()
    assert _wait_gone(launched.proc.pid) and _wait_gone(child)
    assert not os.path.exists(os.path.dirname(launched.socket_path))


def test_a_started_acl2_is_stopped_when_python_exits(fake_acl2):
    """No ``_reset``: the interpreter exits with the ACL2 still running."""
    module_dir = os.path.dirname(pyacl2.__file__)
    script = textwrap.dedent(f"""
        import os
        import clausal.modules.py as P
        if {module_dir!r} not in P.__path__:
            P.__path__.append({module_dir!r})
        from clausal.modules.py import acl2 as A
        A._reset({{"command": {fake_acl2!r}}})
        A._get_bridge("test")
        d = os.path.dirname(A._launched.socket_path)
        print(A._launched.proc.pid, open(os.path.join(d, "child.pid")).read(), d)
    """)
    out = subprocess.run([sys.executable, "-c", script], capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    pid, child, folder = out.stdout.split()
    assert _wait_gone(int(pid)) and _wait_gone(int(child))
    assert not os.path.exists(folder)


# ── the seam surface ─────────────────────────────────────────────────────

def test_seam_fixture_against_the_fake_bridge(bridge):
    from pathlib import Path
    from clausal.testing import run_file
    fixture = Path(__file__).parent / "fixtures" / "acl2_stubbed.seam"
    results = run_file(fixture).results
    failed = [(r.name, r.error) for r in results if not r.passed]
    assert results and not failed, failed


# ── acl2_text: terms <-> ACL2 text, no bridge needed ─────────────────────

def test_acl2_text_parses_text():
    [sol] = solutions(pyacl2._acl2_text_2, Var(), chars("(if (endp x) y (cons (car x) y))"))
    assert sol[0] == ("if", ("endp", "x"), "y", ("cons", ("car", "x"), "y"))


def test_acl2_text_prints_a_term():
    [sol] = solutions(pyacl2._acl2_text_2, ("equal", ":k", ("()", 1, 2)), Var())
    assert sol[1] == chars("(EQUAL :K (1 2))")


def test_acl2_text_checks_both_bound():
    assert solutions(pyacl2._acl2_text_2, "foo", chars("FOO")) != []
    assert solutions(pyacl2._acl2_text_2, "bar", chars("FOO")) == []


@pytest.mark.parametrize("text", [
    "(unclosed", ")", "(a) (b)", "a b", "(a . )", "(a . b c)", "(. a)",
    '"abc', "#\\", "|abc", "", "   ", "#C(1)", "#<FUNCTION CAR>", "'",
    "(a . b . c)",
])
def test_acl2_text_refuses_unreadable_text(text):
    with pytest.raises(LogicException) as info:
        solutions(pyacl2._acl2_text_2, Var(), chars(text))
    assert info.value.term[1] == ("syntax_error", "acl2_text")
    assert info.value.term[2] == ("/", "acl2_text", 2)
    message = info.value.message or ""
    assert message and "index" not in message and "unpack" not in message, message


def test_bare_name_import_reaches_the_adapter(tmp_path):
    """``-import_from(acl2, ...)`` means this adapter, on an engine whose
    alias tables carry ``acl2``."""
    from clausal.templating.term_rewriting import _IMPORT_ALIASES
    if "acl2" not in _IMPORT_ALIASES:
        pytest.skip("this engine predates the bare `acl2` import alias")
    from clausal.testing import run_file
    src = tmp_path / "bare_acl2.seam"
    src.write_text(
        "-import_from(acl2, [acl2_text])\n\n"
        'test("bare acl2") <- (acl2_text(\'nil\', T), T == "NIL")  # nv\n')
    results = run_file(src).results
    assert results and all(r.passed for r in results), [
        (r.name, r.error) for r in results]
