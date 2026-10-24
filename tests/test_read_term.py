"""ISO term input (8.14.1): ``read/1,2`` and ``read_term/2,3`` -- the
terms built, variable sharing and the option lists, the ``double_quotes``
flag of the reading module, operators, syntax errors and resync, the
stream's position after a read, and reading across chunk boundaries.  The
row-by-row conformity checks against Scryer are
``tests/iso/test_read_term_scryer.py``.
"""

from __future__ import annotations

import os
import textwrap

import pytest

from clausal.logic import streams as st
from clausal.logic.database import Module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Trail, Var, deref, is_var
from clausal.terms import SegList


@pytest.fixture(autouse=True)
def _clean_table():
    st.reset_for_tests()
    yield
    st.reset_for_tests()
    from clausal.tools.prolog_operators import reset_runtime_op_table
    reset_runtime_op_table()


@pytest.fixture
def mod():
    return Module("test_read_term")


def run(mod, goal, *vars):
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


def reader_over(mod, tmp_path, text: str):
    f = tmp_path / "in.txt"
    f.write_text(text, encoding="utf-8")
    s = Var()
    (stream,) = run(mod, ("open", os.fspath(f), "read", s), s)
    return stream


def read_all(mod, s):
    out = []
    while len(out) < 5000:
        t = Var()
        r = run(mod, ("read", s, t), t)
        if r[0] != "ERR" and r[0] == "end_of_file":
            return out
        out.append(r[0] if r[0] != "ERR" else r)
    raise AssertionError(f"no end_of_file: {out[:5]} ...")


def test_terms_are_the_engines_own(mod, tmp_path):
    s = reader_over(mod, tmp_path, 'foo(bar, 1, 2.5, "str", [a,b], [], \'A b\', {x}, 0\'c, - 1, -1, a- -1).')
    t = Var()
    assert run(mod, ("read", s, t), t) == [
        ("foo", "bar", 1, 2.5, ("$chars", "str"), ["a", "b"], [], "A b",
         ("{}", "x"), 99, -1, -1, ("-", "a", -1))]
    assert run(mod, ("read", s, t), t) == ["end_of_file"]


def test_variables_share_and_the_option_lists(mod, tmp_path):
    s = reader_over(mod, tmp_path, "foo(X, _Y, _, X, Z, _).")
    t, vs, vn, si = Var(), Var(), Var(), Var()
    (term, variables, names, singles) = run(
        mod, ("read_term", s, t, [("variables", vs), ("variable_names", vn),
                                   ("singletons", si)]), t, vs, vn, si)
    assert term[0] == "foo" and len(term) == 7
    x, y, anon1, x2, z, anon2 = term[1:]
    assert x is x2 and all(is_var(v) for v in (x, y, anon1, z, anon2))
    assert len({id(v) for v in (x, y, anon1, z, anon2)}) == 5
    assert variables == [x, y, anon1, z, anon2]
    assert names == [("=", "X", x), ("=", "_Y", y), ("=", "Z", z)]
    assert singles == [("=", "_Y", y), ("=", "Z", z)]


def test_read_then_unify(mod, tmp_path):
    s = reader_over(mod, tmp_path, "foo(bar). [a,b|T]. 7.")
    t, x = Var(), Var()
    assert run(mod, (",", ("read", s, t), ("=", t, ("foo", x))), x) == ["bar"]
    lst = Var()
    (walked,) = run(mod, ("read", s, lst), lst)
    assert isinstance(walked, SegList)
    assert run(mod, ("read", s, 7)) is True
    assert run(mod, ("read", s, 8)) == "FAIL"           # end_of_file \= 8


def test_partial_list_tail_unifies(mod, tmp_path):
    s = reader_over(mod, tmp_path, "[a,b|T].")
    lst = Var()
    r = run(mod, (",", ("read", s, lst), ("append", ["a", "b"], ["c"], lst)), lst)
    # a list of char atoms IS the string of them (one term, two spellings)
    assert r in ([["a", "b", "c"]], [("$chars", "abc")])


def test_double_quotes_follows_the_reading_module(tmp_path):
    from clausal.import_hook import _load_module
    f = tmp_path / "s.txt"
    f.write_text('"abc".', encoding="utf-8")
    results = {}
    for flag in ("chars", "codes", "atom"):
        path = tmp_path / f"dq_{flag}.pl"
        path.write_text(textwrap.dedent(f"""
            :- set_prolog_flag(double_quotes, {flag}).
            get(T) :- open('{os.fspath(f)}', read, S), read(S, T), close(S).
            """), encoding="utf-8")
        mod = _load_module(f"dq_{flag}", str(path))
        t = Var()
        results[flag] = run(mod, ("get", t), t)[0]
    assert results == {"chars": ("$chars", "abc"), "codes": [97, 98, 99], "atom": "abc"}


def test_operators_in_force_and_op_directives_read_as_data(mod, tmp_path):
    s = reader_over(mod, tmp_path, ":- op(700, xfx, ===). a === b. x ^^ y.")
    t = Var()
    assert run(mod, ("op", 200, "xfy", "^^")) is True
    assert run(mod, ("read", s, t), t) == [(":-", ("op", 700, "xfx", "==="))]
    # the directive was data: === is still no operator
    r = run(mod, ("read", s, t))
    assert r[0] == "ERR" and r[1][0] == "syntax_error", r
    assert run(mod, ("read", s, t), t) == [("^^", "x", "y")]
    assert run(mod, ("read", s, t), t) == ["end_of_file"]


def test_syntax_errors_resync_at_the_end_token(mod, tmp_path):
    s = reader_over(mod, tmp_path, "foo(. bar. )(. baz(1). qux")
    out = read_all(mod, s)
    assert [x[0] if isinstance(x, tuple) and x[0] == "ERR" else x for x in out] == \
        ["ERR", "bar", "ERR", ("baz", 1), "ERR"]
    for x in out:
        if isinstance(x, tuple) and x[0] == "ERR":
            assert x[1][0] == "syntax_error" and type(x[1][1]) is str
    e = Var()
    assert run(mod, ("stream_property", s, ("end_of_stream", e)), e) == ["past"]


def test_layout_after_the_end_token_stays(mod, tmp_path):
    s = reader_over(mod, tmp_path, "a. b.\n")
    t, c = Var(), Var()
    assert run(mod, ("read", s, t), t) == ["a"]
    assert run(mod, ("get_char", s, c), c) == [" "]
    assert run(mod, ("read", s, t), t) == ["b"]
    assert run(mod, ("get_char", s, c), c) == ["\n"]
    assert run(mod, ("read", s, t), t) == ["end_of_file"]


def test_layout_and_comments_before_the_end_give_end_of_file(mod, tmp_path):
    s = reader_over(mod, tmp_path, "a.\n% c\n /* d */ \n")
    t = Var()
    assert run(mod, ("read", s, t), t) == ["a"]
    assert run(mod, ("read", s, t), t) == ["end_of_file"]
    vs = Var()
    assert run(mod, ("read_term", s, t, [("variables", vs)]), t, vs) == ["end_of_file", []]


def test_terms_across_lines_and_several_per_line(mod, tmp_path):
    text = "f(\n  1,\n  2\n). g. h(X).\nlast.\n"
    s = reader_over(mod, tmp_path, text)
    out = read_all(mod, s)
    assert out[:2] == [("f", 1, 2), "g"]
    assert out[2][0] == "h" and is_var(out[2][1])
    assert out[3] == "last"
    # a position after a mid-line read is the logical one
    s = reader_over(mod, tmp_path, "aa. bb. cc.")
    t, p, c = Var(), Var(), Var()
    run(mod, ("read", s, t))
    (pos,) = run(mod, ("stream_property", s, ("position", p)), p)
    assert pos[1] == 3
    assert run(mod, ("read", s, t), t) == ["bb"]
    assert run(mod, ("set_stream_position", s, pos)) is True
    assert run(mod, ("get_char", s, c), c) == [" "]
    assert run(mod, ("read", s, t), t) == ["bb"]


def test_many_terms(mod, tmp_path):
    text = "".join(f"t({i}, [a, b, c], \"s{i}\").\n" for i in range(2000))
    s = reader_over(mod, tmp_path, text)
    out = read_all(mod, s)
    assert len(out) == 2000 and out[1999] == ("t", 1999, ["a", "b", "c"], ("$chars", "s1999"))


def test_read_1_uses_the_current_input(mod, tmp_path):
    s = reader_over(mod, tmp_path, "one. two.")
    t = Var()
    assert run(mod, ("set_input", s)) is True
    assert run(mod, ("read", t), t) == ["one"]
    vn = Var()
    assert run(mod, ("read_term", t, [("variable_names", vn)]), t, vn) == ["two", []]
    assert run(mod, ("read", t), t) == ["end_of_file"]


def test_read_option_errors(mod, tmp_path):
    s = reader_over(mod, tmp_path, "a.")
    t = Var()
    assert run(mod, ("read_term", s, t, Var())) == ("ERR", "instantiation_error")
    assert run(mod, ("read_term", s, t, [Var()])) == ("ERR", "instantiation_error")
    assert run(mod, ("read_term", s, t, "opts")) == ("ERR", ("type_error", "list", "opts"))
    assert run(mod, ("read_term", s, t, [("bogus", 1)])) == \
        ("ERR", ("domain_error", "read_option", ("bogus", 1)))
    assert run(mod, ("read_term", s, t, [("variables", "a")])) == "FAIL"
    assert run(mod, ("read", "user_output", t)) == \
        ("ERR", ("permission_error", "input", "stream", "user_output"))
    assert run(mod, ("read", Var(), t)) == ("ERR", "instantiation_error")
    assert run(mod, ("read", "nope", t)) == ("ERR", ("existence_error", "stream", "nope"))


def test_read_from_a_binary_stream_is_refused(mod, tmp_path):
    f = tmp_path / "b.bin"
    f.write_bytes(b"a.")
    s = Var()
    (s,) = run(mod, ("open", os.fspath(f), "read", s, [("type", "binary")]), s)
    assert run(mod, ("read", s, Var())) == ("ERR", ("permission_error", "input", "binary_stream", s))
