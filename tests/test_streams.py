"""ISO streams (8.11-8.13): the stream table, the standard streams, the
builtins over files, the writers' routing through the current output, the
``.pl`` and ``.clausal`` surfaces, and the sandbox.  The row-by-row
conformity checks against Scryer are ``tests/iso/test_streams_scryer.py``.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import textwrap

import pytest

from clausal.logic import streams as st
from clausal.logic.database import Module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Trail, Var

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _clean_table():
    st.reset_for_tests()
    yield
    st.reset_for_tests()


@pytest.fixture
def mod():
    return Module("test_streams")


def run(mod, goal, *vars):
    """The first answer: the walked values of *vars* (or True), ``"FAIL"``,
    or ``("ERR", formal)`` for a Prolog error."""
    trail = Trail()
    mark = trail.mark()
    try:
        for _ in solve(("call", goal), mod, trail):
            out = [_deref_walk(v) for v in vars] if vars else True
            trail.undo(mark)          # the answer's bindings do not leak
            return out
        return "FAIL"
    except LogicException as e:
        return ("ERR", e.term[1])


def answers(mod, goal, *vars):
    trail = Trail()
    return [tuple(_deref_walk(v) for v in vars) for _ in solve(goal, mod, trail)]


def opened(mod, path, mode, options=None):
    s = Var()
    goal = ("open", path, mode, s) if options is None else ("open", path, mode, s, options)
    r = run(mod, goal, s)
    assert r != "FAIL" and r[0] != "ERR", r
    return r[0]


# ── the table ───────────────────────────────────────────────────────────────


def test_standard_streams_resolve_sys_dynamically():
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        st.USER_OUTPUT.write("hi")
    finally:
        sys.stdout = old
    assert buf.getvalue() == "hi"
    assert st.USER_OUTPUT.term == ("$stream", 1)
    assert st.by_alias("user_error") is st.USER_ERROR
    assert st.by_term(("$stream", 0)) is st.USER_INPUT
    assert st.by_term(("$stream", 99)) is None


def test_open_close_and_lookup(tmp_path):
    f = os.fspath(tmp_path / "a.txt")
    s = st.open_stream(f, "write", aliases=["mine"])
    assert st.by_alias("mine") is s and st.by_term(s.term) is s
    assert s in st.open_streams()
    s.write("x\ny")
    assert (s.char_count, s.line_count, s.line_pos) == (3, 1, 1)
    st.close_stream(s)
    assert st.by_alias("mine") is None and st.by_term(s.term) is None
    assert s.closed
    with open(f) as fh:
        assert fh.read() == "x\ny"


def test_closing_the_current_streams_restores_the_standard_ones(tmp_path):
    f = os.fspath(tmp_path / "a.txt")
    out = st.open_stream(f, "write")
    st.set_current_output(out)
    st.close_stream(out)
    assert st.current_output() is st.USER_OUTPUT
    inp = st.open_stream(f, "read")
    st.set_current_input(inp)
    st.close_stream(inp)
    assert st.current_input() is st.USER_INPUT


def test_closing_a_standard_stream_is_a_no_op():
    st.close_stream(st.USER_OUTPUT)
    assert not st.USER_OUTPUT.closed and st.by_alias("user_output") is st.USER_OUTPUT


def test_get_peek_and_end_of_stream(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("ab", encoding="utf-8")
    s = st.open_stream(os.fspath(f), "read")
    assert s.end_of_stream() == "not"
    assert s.peek() == "a" and s.peek() == "a"
    assert s.get() == "a" and s.get() == "b"
    assert s.end_of_stream() == "at"
    assert s.peek() is None and s.end_of_stream() == "at"
    assert s.get() is None and s.end_of_stream() == "past"
    st.close_stream(s)


def test_position_with_a_pushed_back_char_and_seek(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("héllo\nwörld", encoding="utf-8")
    s = st.open_stream(os.fspath(f), "read")
    assert s.get() == "h"
    assert s.peek() == "é"            # read ahead, pushed back
    p1 = s.position()
    assert p1[:4] == (st.POSITION_TAG, 1, 0, 1)
    assert s.get() == "é"
    s.read_chunk()                     # the rest of the line, pushed back
    s.unread("llo\n")
    p2 = s.position()
    assert p2[:4] == (st.POSITION_TAG, 2, 0, 2)
    assert s.get() == "l"
    s.seek_to(p1)
    assert "".join(iter(s.get, None)) == "éllo\nwörld"
    assert s.end_of_stream() == "past"
    s.seek_to(p2)
    assert s.end_of_stream() == "not" and s.get() == "l"
    assert s.line_count == 0
    st.close_stream(s)


def test_binary_stream(tmp_path):
    f = os.fspath(tmp_path / "a.bin")
    s = st.open_stream(f, "write", kind="binary")
    s.write_bytes(bytes([0, 200, 255]))
    st.close_stream(s)
    r = st.open_stream(f, "read", kind="binary")
    assert r.peek() == 0 and r.get() == 0 and r.get() == 200
    p = r.position()
    assert r.get() == 255 and r.get() is None
    r.seek_to(p)
    assert r.get() == 255
    st.close_stream(r)


def test_open_failures(tmp_path):
    with pytest.raises(st.OpenFailed) as e:
        st.open_stream(os.fspath(tmp_path / "missing"), "read")
    assert e.value.why == "existence"
    with pytest.raises(st.OpenFailed) as e:
        st.open_stream(os.fspath(tmp_path), "write")
    assert e.value.why == "permission"
    with pytest.raises(st.OpenFailed) as e:
        st.open_stream(os.fspath(tmp_path / "missing" / "x"), "write")
    assert e.value.why == "existence"


# ── the builtins ────────────────────────────────────────────────────────────


def test_open_write_read_round_trip(mod, tmp_path):
    f = os.fspath(tmp_path / "t.txt")
    w = opened(mod, f, "write")
    assert w == ("$stream", 3)
    assert run(mod, ("write", w, ("foo", "X", ("$chars", "ab")))) is True
    assert run(mod, ("nl", w)) is True
    assert run(mod, ("writeq", w, "hello world")) is True
    assert run(mod, ("put_char", w, ".")) is True
    assert run(mod, ("put_code", w, 10)) is True
    assert run(mod, ("write_canonical", w, [1, 2])) is True
    assert run(mod, ("write_term", w, "a b", [("quoted", True)])) is True
    assert run(mod, ("format", w, ("$chars", "~w-~a"), [1, "x"])) is True
    assert run(mod, ("tab", w, 2)) is True
    assert run(mod, ("flush_output", w)) is True
    assert run(mod, ("close", w)) is True
    with open(f, encoding="utf-8") as fh:
        assert fh.read() == "foo(X,[a,b])\n'hello world'.\n'.'(1,'.'(2,[]))'a b'1-x  "
    r = opened(mod, f, "read")
    c = Var()
    assert run(mod, ("get_char", r, c), c) == ["f"]
    assert run(mod, ("peek_char", r, c), c) == ["o"]
    assert run(mod, ("get_code", r, c), c) == [ord("o")]
    assert run(mod, ("close", r)) is True
    assert run(mod, ("get_char", r, c)) == ("ERR", ("existence_error", "stream", r))


def test_stream_term_is_opaque_and_prints_quoted(mod, tmp_path):
    from clausal.terms import term_writeq
    f = os.fspath(tmp_path / "t.txt")
    w = opened(mod, f, "write")
    assert term_writeq(w) == "'$stream'(3)"
    run(mod, ("close", w))


def test_aliases_and_current_streams(mod, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("ab", encoding="utf-8")
    r = opened(mod, os.fspath(f), "read", [("alias", "inp")])
    s = Var()
    assert run(mod, ("stream_property", s, ("alias", "inp")), s) == [r]
    assert run(mod, ("set_input", "inp")) is True
    cur = Var()
    assert run(mod, ("current_input", cur), cur) == [r]
    c = Var()
    assert run(mod, ("get_char", c), c) == ["a"]
    assert run(mod, ("peek_code", c), c) == [ord("b")]
    assert run(mod, ("close", "inp")) is True
    assert run(mod, ("current_input", cur), cur) == [("$stream", 0)]
    assert run(mod, ("set_input", "inp")) == ("ERR", ("existence_error", "stream", "inp"))
    # the alias is free again
    r2 = opened(mod, os.fspath(f), "read", [("alias", "inp")])
    assert run(mod, ("open", os.fspath(f), "read", Var(), [("alias", "inp")])) == \
        ("ERR", ("permission_error", "open", "source_sink", ("alias", "inp")))
    run(mod, ("close", r2))


def test_write_1_writes_to_the_current_output_which_is_stdout(mod, capsys, tmp_path):
    assert run(mod, ("write", ("f", 1))) is True
    assert run(mod, "nl") is True
    assert run(mod, ("writeln", "x")) is True
    assert run(mod, ("print_term", ("$chars", "s"))) is True
    assert run(mod, ("format", ("$chars", "~w~n"), ["y"])) is True
    assert capsys.readouterr().out == "f(1)\nx\n\"s\"\ny\n"
    f = os.fspath(tmp_path / "t.txt")
    w = opened(mod, f, "write")
    assert run(mod, ("set_output", w)) is True
    assert run(mod, ("write", "to_file")) is True
    assert run(mod, ("writeq", "A")) is True
    assert run(mod, ("write_canonical", "x")) is True
    assert run(mod, ("write_term", "a", [])) is True
    assert run(mod, ("write_text", ("$chars", "txt"))) is True
    assert run(mod, ("writeln_text", ("$chars", "t"))) is True
    assert run(mod, ("tab", 1)) is True
    assert run(mod, ("put_char", "c")) is True
    assert run(mod, ("put_code", 100)) is True
    assert run(mod, ("portray_clause", ("foo", "x"))) is True
    assert run(mod, ("close", w)) is True
    assert run(mod, ("write", "back")) is True
    assert capsys.readouterr().out == "back"
    with open(f, encoding="utf-8") as fh:
        assert fh.read() == "to_file'A'xatxtt\n cdfoo(x)\n"


def test_writers_refuse_a_binary_or_input_stream(mod, tmp_path):
    f = os.fspath(tmp_path / "t.bin")
    b = opened(mod, f, "write", [("type", "binary")])
    for goal in (("write", b, "a"), ("nl", b), ("put_char", b, "a"),
                 ("write_term", b, "a", []), ("format", b, ("$chars", "x"), [])):
        assert run(mod, goal) == ("ERR", ("permission_error", "output", "binary_stream", b)), goal
    assert run(mod, ("set_output", b)) is True
    assert run(mod, ("write", "a")) == ("ERR", ("permission_error", "output", "binary_stream", b))
    assert run(mod, "nl") == ("ERR", ("permission_error", "output", "binary_stream", b))
    assert run(mod, ("put_byte", 7)) is True
    assert run(mod, ("set_output", "user_output")) is True
    run(mod, ("close", b))
    r = opened(mod, f, "read")
    assert run(mod, ("write", r, "a")) == ("ERR", ("permission_error", "output", "stream", r))
    assert run(mod, ("put_byte", r, 1)) == ("ERR", ("permission_error", "output", "stream", r))
    run(mod, ("close", r))


def test_eof_actions(mod, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("a", encoding="utf-8")
    c = Var()
    r = opened(mod, os.fspath(f), "read", [("eof_action", "error")])
    assert run(mod, ("get_char", r, c), c) == ["a"]
    assert run(mod, ("get_char", r, c), c) == ["end_of_file"]
    e = Var()
    assert run(mod, ("stream_property", r, ("end_of_stream", e)), e) == ["past"]
    assert run(mod, ("get_char", r, c)) == \
        ("ERR", ("permission_error", "input", "past_end_of_stream", r))
    assert run(mod, ("peek_char", r, c)) == \
        ("ERR", ("permission_error", "input", "past_end_of_stream", r))
    assert run(mod, ("read", r, c)) == \
        ("ERR", ("permission_error", "input", "past_end_of_stream", r))
    run(mod, ("close", r))
    # eof_code (the default): end_of_file again and again
    r = opened(mod, os.fspath(f), "read")
    assert run(mod, ("get_code", r, c), c) == [ord("a")]
    assert run(mod, ("get_code", r, c), c) == [-1]
    assert run(mod, ("get_code", r, c), c) == [-1]
    assert run(mod, ("get_char", r, c), c) == ["end_of_file"]
    run(mod, ("close", r))
    # reset: a file that grew is read on
    r = opened(mod, os.fspath(f), "read", [("eof_action", "reset")])
    assert run(mod, ("get_char", r, c), c) == ["a"]
    assert run(mod, ("get_char", r, c), c) == ["end_of_file"]
    with open(f, "a", encoding="utf-8") as fh:
        fh.write("b")
    assert run(mod, ("get_char", r, c), c) == ["b"]
    assert run(mod, ("stream_property", r, ("end_of_stream", e)), e) == ["at"]
    run(mod, ("close", r))


def test_stream_property_enumerates_streams_and_properties(mod, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("a", encoding="utf-8")
    r = opened(mod, os.fspath(f), "read", [("alias", "aa")])
    s, p = Var(), Var()
    rows = answers(mod, ("stream_property", s, p), s, p)
    streams = {row[0] for row in rows}
    assert streams == {("$stream", 0), ("$stream", 1), ("$stream", 2), r}
    props = [row[1] for row in rows if row[0] == r]
    pos = [x for x in props if type(x) is tuple and x[0] == "position"]
    assert len(pos) == 1 and st.is_position_term(pos[0][1])
    assert [x for x in props if not (type(x) is tuple and x[0] == "position")] == [
        ("file_name", os.fspath(f)), ("mode", "read"), "input", ("alias", "aa"),
        ("end_of_stream", "not"), ("eof_action", "eof_code"),
        ("reposition", True), ("type", "text")]
    # a given property enumerates the streams having it
    assert answers(mod, ("stream_property", s, "input"), s) == [(("$stream", 0),), (r,)]
    # an alias as the stream is accepted and left as it is
    m = Var()
    assert run(mod, ("stream_property", "aa", ("mode", m)), m) == ["read"]
    assert run(mod, ("stream_property", "user_input", ("eof_action", m)), m) == ["reset"]
    assert run(mod, ("stream_property", "user_output", ("mode", m)), m) == ["append"]
    assert run(mod, ("stream_property", s, ("file_name", os.fspath(f))), s) == [r]
    assert run(mod, ("stream_property", r, ("alias", "zz"))) == "FAIL"
    assert run(mod, ("stream_property", r, ("bogus", 1))) == \
        ("ERR", ("domain_error", "stream_property", ("bogus", 1)))
    assert run(mod, ("stream_property", 1, p)) == ("ERR", ("domain_error", "stream", 1))
    run(mod, ("close", r))
    assert run(mod, ("stream_property", r, p)) == ("ERR", ("existence_error", "stream", r))


def test_set_stream_position(mod, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("abc", encoding="utf-8")
    r = opened(mod, os.fspath(f), "read")
    c, p = Var(), Var()
    assert run(mod, ("get_char", r, c), c) == ["a"]
    (pos,) = run(mod, ("stream_property", r, ("position", p)), p)
    assert run(mod, ("get_char", r, c), c) == ["b"]
    assert run(mod, ("set_stream_position", r, pos)) is True
    assert run(mod, ("get_char", r, c), c) == ["b"]
    assert run(mod, ("set_stream_position", r, ("$stream_position", 1))) == \
        ("ERR", ("domain_error", "stream_position", ("$stream_position", 1)))
    run(mod, ("close", r))
    a = opened(mod, os.fspath(f), "append")
    assert run(mod, ("set_stream_position", a, pos)) == \
        ("ERR", ("permission_error", "reposition", "stream", a))
    run(mod, ("close", a))
    nr = opened(mod, os.fspath(f), "read", [("reposition", False)])
    assert run(mod, ("set_stream_position", nr, pos)) == \
        ("ERR", ("permission_error", "reposition", "stream", nr))
    run(mod, ("close", nr))


def test_at_end_of_stream(mod, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("a", encoding="utf-8")
    r = opened(mod, os.fspath(f), "read")
    assert run(mod, ("at_end_of_stream", r)) == "FAIL"
    assert run(mod, ("set_input", r)) is True
    assert run(mod, "at_end_of_stream") == "FAIL"
    c = Var()
    run(mod, ("get_char", c))
    assert run(mod, "at_end_of_stream") is True
    assert run(mod, ("at_end_of_stream", r)) is True
    assert run(mod, ("at_end_of_stream", "user_output")) == "FAIL"
    run(mod, ("close", r))


def test_close_force_and_options(mod, tmp_path):
    f = os.fspath(tmp_path / "t.txt")
    w = opened(mod, f, "write")
    assert run(mod, ("close", w, [("force", True)])) is True
    w = opened(mod, f, "write")
    assert run(mod, ("close", w, [("force", "maybe")])) == \
        ("ERR", ("domain_error", "close_option", ("force", "maybe")))
    assert run(mod, ("close", w, "x")) == ("ERR", ("type_error", "list", "x"))
    assert run(mod, ("close", w, [("force", False)])) is True
    assert run(mod, ("close", w)) == ("ERR", ("existence_error", "stream", w))
    assert run(mod, ("close", "user_output")) is True
    assert run(mod, ("write", "user_output", "")) is True


def test_open_option_shapes(mod, tmp_path):
    f = os.fspath(tmp_path / "t.txt")
    s = Var()
    assert run(mod, ("open", f, "write", s, [("type", "binary"), ("alias", "b1"),
                                            ("eof_action", "reset"), ("reposition", True)]), s) \
        == [("$stream", 3)]
    t, a, e, rp = Var(), Var(), Var(), Var()
    assert run(mod, ("stream_property", "b1", ("type", t)), t) == ["binary"]
    assert run(mod, ("stream_property", "b1", ("eof_action", e)), e) == ["reset"]
    assert run(mod, ("stream_property", "b1", ("reposition", rp)), rp) == [True]
    run(mod, ("close", "b1"))
    # append may be repositioned when asked (a seekable file)
    a1 = opened(mod, f, "append", [("reposition", True)])
    assert run(mod, ("stream_property", a1, ("reposition", rp)), rp) == [True]
    run(mod, ("close", a1))
    assert run(mod, ("open", f, "read", Var(), [("alias", "b1"), "junk"])) == \
        ("ERR", ("domain_error", "stream_option", "junk"))
    assert run(mod, ("open", f, "read", Var(), [Var()])) == ("ERR", "instantiation_error")
    # an option with an unbound argument: ISO 8.11.5.3 a, as Scryer and SWI
    assert run(mod, ("open", f, "read", Var(), [("alias", Var())])) == ("ERR", "instantiation_error")
    assert run(mod, ("open", f, "read", Var(), [("type", Var())])) == ("ERR", "instantiation_error")


def test_byte_predicates(mod, tmp_path):
    f = os.fspath(tmp_path / "t.bin")
    w = opened(mod, f, "write", [("type", "binary")])
    assert run(mod, ("put_byte", w, 0)) is True
    assert run(mod, ("put_byte", w, 255)) is True
    assert run(mod, ("put_byte", w, 256)) == ("ERR", ("type_error", "byte", 256))
    assert run(mod, ("put_byte", w, Var())) == ("ERR", "instantiation_error")
    run(mod, ("close", w))
    r = opened(mod, f, "read", [("type", "binary")])
    b = Var()
    assert run(mod, ("peek_byte", r, b), b) == [0]
    assert run(mod, ("get_byte", r, b), b) == [0]
    assert run(mod, ("get_byte", r, 255)) is True
    assert run(mod, ("get_byte", r, b), b) == [-1]
    assert run(mod, ("get_byte", r, "a")) == ("ERR", ("type_error", "in_byte", "a"))
    assert run(mod, ("get_byte", r, 300)) == ("ERR", ("type_error", "in_byte", 300))
    assert run(mod, ("get_char", r, b)) == ("ERR", ("permission_error", "input", "binary_stream", r))
    assert run(mod, ("get_byte", "user_input", b)) == \
        ("ERR", ("permission_error", "input", "text_stream", "user_input"))
    run(mod, ("close", r))


def test_char_and_code_argument_checks(mod):
    assert run(mod, ("put_char", "user_output", "ab")) == ("ERR", ("type_error", "character", "ab"))
    assert run(mod, ("put_char", "user_output", 1)) == ("ERR", ("type_error", "character", 1))
    assert run(mod, ("put_code", "user_output", "a")) == ("ERR", ("type_error", "integer", "a"))
    assert run(mod, ("put_code", "user_output", -1)) == ("ERR", ("representation_error", "character_code"))
    assert run(mod, ("put_code", "user_output", 0xD800)) == ("ERR", ("representation_error", "character_code"))
    assert run(mod, ("get_char", "user_input", "ab")) == ("ERR", ("type_error", "in_character", "ab"))
    assert run(mod, ("get_code", "user_input", -2)) == ("ERR", ("representation_error", "in_character_code"))
    assert run(mod, ("get_code", "user_input", 2.0)) == ("ERR", ("type_error", "integer", 2.0))
    assert run(mod, ("get_char", "user_output", Var())) == \
        ("ERR", ("permission_error", "input", "stream", "user_output"))
    assert run(mod, ("get_char", Var(), Var())) == ("ERR", "instantiation_error")
    assert run(mod, ("get_char", ("f", 1), Var())) == ("ERR", ("domain_error", "stream_or_alias", ("f", 1)))
    assert run(mod, ("get_char", "nothing", Var())) == ("ERR", ("existence_error", "stream", "nothing"))


def test_open_errors(mod, tmp_path):
    missing = os.fspath(tmp_path / "missing.txt")
    assert run(mod, ("open", missing, "read", Var())) == ("ERR", ("existence_error", "source_sink", missing))
    assert run(mod, ("open", os.fspath(tmp_path), "write", Var())) == \
        ("ERR", ("permission_error", "open", "source_sink", os.fspath(tmp_path)))
    assert run(mod, ("open", 1, "read", Var())) == ("ERR", ("domain_error", "source_sink", 1))
    assert run(mod, ("open", missing, "rw", Var())) == ("ERR", ("domain_error", "io_mode", "rw"))
    assert run(mod, ("open", missing, 7, Var())) == ("ERR", ("type_error", "atom", 7))
    assert run(mod, ("open", missing, "read", "s")) == ("ERR", ("uninstantiation_error", "s"))
    assert run(mod, ("open", missing, "read", Var(), [("type", "text")] + [Var()][:0] + ["x"])) == \
        ("ERR", ("domain_error", "stream_option", "x"))
    assert run(mod, ("open", Var(), "read", Var())) == ("ERR", "instantiation_error")


def test_source_sink_as_string_or_code_list(mod, tmp_path):
    f = tmp_path / "named.txt"
    f.write_text("x", encoding="utf-8")
    c = Var()
    for name in (("$chars", os.fspath(f)), list(os.fspath(f)),
                 [ord(ch) for ch in os.fspath(f)]):
        r = opened(mod, name, "read")
        assert run(mod, ("get_char", r, c), c) == ["x"]
        fn = Var()
        assert run(mod, ("stream_property", r, ("file_name", fn)), fn) == [os.fspath(f)]
        run(mod, ("close", r))
    assert run(mod, ("open", [], "read", Var())) == ("ERR", ("domain_error", "source_sink", []))
    assert run(mod, ("open", [1, "a"], "read", Var())) == \
        ("ERR", ("domain_error", "source_sink", [1, "a"]))


def test_flush_output_reports_an_os_error(mod):
    if not os.path.exists("/dev/full"):
        pytest.skip("no /dev/full")
    w = opened(mod, "/dev/full", "write")
    assert run(mod, ("write", w, "x")) is True
    r = run(mod, ("flush_output", w))
    assert r[0] == "ERR" and r[1] == ("system_error", "io"), r
    assert run(mod, ("set_output", w)) is True
    r = run(mod, "flush_output")
    assert r[0] == "ERR" and r[1] == ("system_error", "io"), r
    run(mod, ("set_output", "user_output"))
    assert run(mod, ("close", w, [("force", True)])) is True


def test_a_file_closed_underneath_is_a_system_error(mod, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("ab", encoding="utf-8")
    r = opened(mod, os.fspath(f), "read")
    st.by_term(r)._f.close()                      # the Python file, not the stream
    c = Var()
    for goal in (("get_char", r, c), ("peek_char", r, c), ("read", r, c),
                 ("at_end_of_stream", r)):
        res = run(mod, goal)
        assert res[0] == "ERR" and res[1] == ("system_error", "io"), (goal, res)
    assert run(mod, ("close", r, [("force", True)])) is True
    w = opened(mod, os.fspath(f), "write")
    st.by_term(w)._f.close()
    for goal in (("write", w, "x"), ("nl", w), ("put_char", w, "x"), ("flush_output", w),
                 ("write_term", w, "x", []), ("format", w, ("$chars", "x"), [])):
        res = run(mod, goal)
        assert res[0] == "ERR" and res[1] == ("system_error", "io"), (goal, res)
    assert run(mod, ("close", w, [("force", True)])) is True


def test_standard_streams_that_cannot_be_read_or_written(mod, monkeypatch):
    monkeypatch.setattr(sys, "stdin", None)
    c = Var()
    for goal in (("get_char", "user_input", c), ("get_char", c), ("read", c)):
        res = run(mod, goal)
        assert res[0] == "ERR" and res[1] == ("system_error", "io"), (goal, res)

    class Closed:
        def write(self, text):
            raise ValueError("I/O operation on closed file")
    monkeypatch.setattr(sys, "stdout", Closed())
    res = run(mod, ("write", "x"))
    assert res[0] == "ERR" and res[1] == ("system_error", "io"), res


def test_writers_accept_a_flushless_stdout(mod, monkeypatch):
    class Sink:
        def __init__(self):
            self.parts = []

        def write(self, text):
            self.parts.append(text)
    sink = Sink()
    monkeypatch.setattr(sys, "stdout", sink)
    for goal in (("write", "a"), ("writeln", "b"), "nl", ("print_term", "c"),
                 ("portray_clause", "d"), ("write_text", ("$chars", "e")),
                 ("format", ("$chars", "f"), [])):
        assert run(mod, goal) is True, goal
    assert "".join(sink.parts) == "ab\n\nc\nd\nef"


def test_standard_streams_flush_only_a_terminal(mod, monkeypatch):
    class Sink:
        def __init__(self, tty):
            self.tty = tty
            self.flushes = 0

        def write(self, text):
            pass

        def flush(self):
            self.flushes += 1

        def isatty(self):
            return self.tty
    for tty, flushes in ((False, 0), (True, 2)):
        sink = Sink(tty)
        monkeypatch.setattr(sys, "stdout", sink)
        run(mod, ("write", "x"))
        run(mod, "nl")
        assert sink.flushes == flushes


def test_a_hand_built_position_is_a_domain_error(mod, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("abc", encoding="utf-8")
    r = opened(mod, os.fspath(f), "read")
    bad = ("$stream_position", 1, 0, 1, -7)
    assert run(mod, ("set_stream_position", r, bad)) == \
        ("ERR", ("domain_error", "stream_position", bad))
    run(mod, ("close", r))


def test_alias_check_and_registration_are_one_step(tmp_path):
    f = os.fspath(tmp_path / "a.txt")
    s = st.open_stream(f, "write", aliases=["one"])
    with pytest.raises(st.AliasInUse):
        st.open_stream(f, "write", aliases=["one"])
    st.close_stream(s)


# ── surfaces ────────────────────────────────────────────────────────────────


def _load(tmp_path, name, suffix, text):
    from clausal.import_hook import _load_module
    path = tmp_path / f"{name}{suffix}"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return _load_module(name, str(path))


def test_pl_program_uses_streams(tmp_path, capsys):
    f = os.fspath(tmp_path / "data.txt")
    mod = _load(tmp_path, "pl_streams", ".pl", f"""
        :- use_module(library(lists)).
        dump(File, Terms) :-
            open(File, write, S),
            forall(member(T, Terms), (writeq(S, T), write(S, '.'), nl(S))),
            close(S).
        slurp(File, Terms) :-
            open(File, read, S), read_all(S, Terms), close(S).
        read_all(S, Terms) :-
            read(S, T),
            ( T == end_of_file -> Terms = [] ; Terms = [T|Rest], read_all(S, Rest) ).
        main :- dump('{f}', [a, f(X, Y, X), "str", [1,2|T]]), slurp('{f}', Ts),
                writeq(Ts), nl.
        """)
    for _ in solve("main", mod, Trail()):
        break
    out = re.sub(r"_G?[0-9]+", "_", capsys.readouterr().out)
    assert out == "[a,f(_,_,_),[s,t,r],[1,2|_]]\n"
    with open(f, encoding="utf-8") as fh:
        assert fh.read().splitlines()[0] == "a."


def test_clausal_program_uses_streams(tmp_path, capsys):
    f = os.fspath(tmp_path / "data.txt")
    mod = _load(tmp_path, "clausal_streams", ".clausal", f"""
        :- module(clausal_streams, [main/0]).
        copy_chars(In, Out) :- get_char(In, C), copy_rest(C, In, Out).
        copy_rest(end_of_file, _, _).
        copy_rest(C, In, Out) :-
            C \\== end_of_file, put_char(Out, C), copy_chars(In, Out).
        main :-
            open('{f}', write, W), write(W, hello(world)), write(W, '.'), nl(W), close(W),
            open('{f}', read, R), copy_chars(R, user_output), close(R),
            open("{f}", read, R2), read(R2, T), close(R2), T = hello(X), write(X), nl.
        :- end_module(clausal_streams).
        """)
    for _ in solve("main", mod, Trail()):
        break
    assert capsys.readouterr().out == "hello(world).\nworld\n"


def test_sandbox_refuses_the_stream_builtins(tmp_path):
    code = textwrap.dedent("""
        import clausal.sandbox
        clausal.sandbox.enable()
        import clausal
        from clausal.logic.database import Module
        from clausal.logic.exceptions import LogicException
        from clausal.logic.solve import solve
        from clausal.logic.variables import Trail, Var
        mod = Module("sandboxed")
        for goal in (("open", "x.txt", "read", Var()), ("current_output", Var()),
                     ("get_char", Var()), ("read", Var()), ("close", "user_output"),
                     ("stream_property", Var(), Var())):
            try:
                for _ in solve(goal, mod, Trail()):
                    pass
                print("ran", goal[0])
            except LogicException as e:
                print(e.term[1])
        """)
    env = dict(os.environ, PYTHONPATH=ROOT)
    env.pop("CLAUSAL_SANDBOX", None)
    proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert proc.stdout.splitlines() == [
        "('permission_error', 'access', 'private_procedure', ('/', 'open', 3))",
        "('permission_error', 'access', 'private_procedure', ('/', 'current_output', 1))",
        "('permission_error', 'access', 'private_procedure', ('/', 'get_char', 1))",
        "('permission_error', 'access', 'private_procedure', ('/', 'read', 1))",
        "('permission_error', 'access', 'private_procedure', ('/', 'close', 1))",
        "('permission_error', 'access', 'private_procedure', ('/', 'stream_property', 2))",
    ]
