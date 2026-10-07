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
import tempfile
import threading
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
    exception message for an ERROR reply."""

    def __init__(self, replies):
        self.replies = replies
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


@pytest.fixture
def bridge():
    fake = FakeBridge({
        "(+ 1 2)": ("", "3"),
        "(APPEND (QUOTE (A B)) (QUOTE (C)))": ("", "(A B C)"),
        "(CW \"hi~%\")": ("hi\n", "NIL"),
        "(MV 1 :TWO \"three\")": ("", '(1 :TWO "three")'),
        "(CAR 3)": "Error executing command (CAR 3):\nThe value 3 is not of type LIST",
        "(REV (QUOTE (1 2 \"é\")))": ("", '("é" 2 1)'),
        ld_text("(THM (EQUAL (REV (REV X)) X))"):
            ("Q.E.D.\n", "(NIL :EOF ACL2_INVISIBLE::|The Live State Itself|)"),
        ld_text("(THM (EQUAL X 1))"):
            ("******** FAILED ********\n", "(T :ERROR ACL2_INVISIBLE::|The Live State Itself|)"),
        ld_text("(DEFUN SQ (X) (* X X))"):
            ("Since SQ is non-recursive, its admission is trivial.\n",
             "(NIL :EOF ACL2_INVISIBLE::|The Live State Itself|)"),
    })
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


def test_use_acl2_names_the_bridge(bridge):
    solutions(pyacl2._use_acl2_1, DictTerm({"socket": chars(bridge.path)}))
    assert pyacl2._settings == {"socket": bridge.path}
    [sol] = solutions(pyacl2._acl2_2, ("+", 1, 2), Var())
    assert sol[1] == 3


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


def test_acl2_text_refuses_unreadable_text():
    with pytest.raises(LogicException) as info:
        solutions(pyacl2._acl2_text_2, Var(), chars("(unclosed"))
    assert info.value.term[1][0] == "syntax_error"


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
