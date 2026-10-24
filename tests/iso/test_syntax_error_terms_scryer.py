"""Syntax errors: the formal term is Scryer's, the context is Clausal's.

Operator ruling 2026-10-24: ``error(syntax_error(Atom), Context)`` follows
Scryer and is more useful than Scryer, each in a different slot.

* ISO 7.12.2 h leaves the *formal* argument implementation dependent, so
  for portability Clausal gives Scryer's atom for the same input:
  ``incomplete_reduction`` for every grammar fault (a missing end token,
  unbalanced brackets, an operator priority clash, ``f()``, ``1e+9``, a
  quote still open at the end of the text), ``invalid_single_quoted_character``
  (a raw newline, control character or bad escape in a quoted atom),
  ``missing_quote`` (the same in a string), ``unexpected_char`` (a
  character that starts no token, or a bad ``0'`` character),
  ``back_quoted_string``, ``infinite_float``, ``cannot_parse_big_int`` and
  ``utf8_conversion_error`` (an escape no character has).  Every row of
  ``ROWS`` is one malformed text, read as a term by the native ISO reader
  (``test_engine_kind``) and by Scryer's ``read_term/3`` from a file holding
  the same text (``test_oracle``); the third column is Scryer's atom
  measured 2026-10-24 against the clean build, and both halves must give it.
  ``None`` is a text that reads: a control row.

* ISO leaves the *context* implementation defined.  Scryer's is a bare
  ``read_term/3:Line``; Clausal's is ``context(read_term/3, Details)`` with
  ``Details`` a list of ``line(L)``, ``column(C)`` (1-based), and where the
  parser knows them ``expected(What)`` and ``found(Token)``
  (``test_engine_context_shape``).  Portable code matching
  ``error(syntax_error(_), _)`` sees no difference.

The same shape reaches every surface: a ``.pl``/``.clausal`` file that
fails to load (``PrologSyntaxError.term``, ``test_load_surface``),
``term_to_atom/2`` and ``atom_to_term/3`` (``test_text_surfaces``) and the
``number_chars/2`` family (``test_number_chars_context``), whose Scryer
atoms (``unexpected_end_of_file``, ``unexpected_char``, ...) are kept.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import PrologSyntaxError
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.tools.iso_l3 import read_iso
from clausal.tools.prolog_reader import EOF, SyntaxIssue

from tests._oracles import SCRYER

#: (row id, the text read as a term, Scryer's syntax_error atom or None).
ROWS = [
    ('sq_unterminated_eof', "X = 'abc", 'incomplete_reduction'),
    ('sq_unterminated_nl', "X = 'abc\n", 'invalid_single_quoted_character'),
    ('sq_unterminated_nl_more', "X = 'abc\nfoo.\n", 'invalid_single_quoted_character'),
    ('dq_unterminated_eof', 'X = "abc', 'incomplete_reduction'),
    ('dq_unterminated_nl', 'X = "abc\n', 'missing_quote'),
    ('bq_unterminated', 'X = `abc', 'incomplete_reduction'),
    ('bq_string', 'X = `abc`.\n', 'back_quoted_string'),
    ('sq_escape_quote_eof', "X = '\\'", 'incomplete_reduction'),
    ('sq_backslash_eof', "X = 'a\\", 'incomplete_reduction'),
    ('dq_backslash_eof', 'X = "a\\', 'incomplete_reduction'),
    ('charcode_eof', "X = 0'", 'incomplete_reduction'),
    ('charcode_nl', "X = 0'\n", 'unexpected_char'),
    ('sq_bad_escape_z', "X = '\\z'.\n", 'invalid_single_quoted_character'),
    ('dq_bad_escape_q', 'X = "\\q".\n', 'missing_quote'),
    ('dq_hex_no_close', 'X = "\\x41".\n', 'incomplete_reduction'),
    ('sq_hex_bad_digit', "X = '\\xZZ\\'.\n", 'incomplete_reduction'),
    ('sq_octal_no_close', "X = '\\0'.\n", 'incomplete_reduction'),
    ('sq_octal_huge', "X = '\\777777777\\'.\n", 'utf8_conversion_error'),
    ('sq_hex_huge', "X = '\\xFFFFFFFF\\'.\n", 'utf8_conversion_error'),
    ('charcode_bad_escape', "X = 0'\\z.\n", 'unexpected_char'),
    ('charcode_octal_no_close', "X = 0'\\08\\.\n", 'incomplete_reduction'),
    ('sq_u_escape', "X = '\\u0041'.\n", 'invalid_single_quoted_character'),
    ('dq_e_escape', 'X = "\\e".\n', 'missing_quote'),
    ('sq_continuation', "X = 'a\\\nb'.\n", None),
    ('no_end_eof', 'foo', 'incomplete_reduction'),
    ('no_end_nl', 'foo\n', 'incomplete_reduction'),
    ('open_paren_eof', 'foo(', 'incomplete_reduction'),
    ('open_args_eof', 'foo(a,\n', 'incomplete_reduction'),
    ('open_list_eof', '[a,b', 'incomplete_reduction'),
    ('open_curly_eof', '{a', 'incomplete_reduction'),
    ('open_group_eof', '(a', 'incomplete_reduction'),
    ('rule_no_end', 'a :- b\n', 'incomplete_reduction'),
    ('dot_then_name', 'X = foo.bar.\n', 'incomplete_reduction'),
    ('eq_dot', 'X = .\n', 'incomplete_reduction'),
    ('dot_only', '.\n', 'incomplete_reduction'),
    ('dir_empty', ':- .\n', None),
    ('rule_empty_body', 'foo :- .\n', 'incomplete_reduction'),
    ('extra_rparen', 'foo).\n', 'incomplete_reduction'),
    ('extra_rparen2', 'foo(a)).\n', 'incomplete_reduction'),
    ('extra_rbracket', '[a,b]].\n', 'incomplete_reduction'),
    ('bare_rbracket', 'a].\n', 'incomplete_reduction'),
    ('close_in_body', 'foo(X) :- X = ).\n', 'incomplete_reduction'),
    ('disj_missing_right', 'foo :- (a ; ).\n', 'incomplete_reduction'),
    ('neg_missing_arg', 'p :- \\+ .\n', 'incomplete_reduction'),
    ('open_conj_eof', 'X = (a, b', 'incomplete_reduction'),
    ('xfx_clash_neck', 'a :- b :- c.\n', 'incomplete_reduction'),
    ('xfx_clash_eq', 'X = 1 = 2.\n', 'incomplete_reduction'),
    ('eq_eq', 'a = = b.\n', 'incomplete_reduction'),
    ('plus_times', 'X is 1 + * 2.\n', 'incomplete_reduction'),
    ('neck_neck', ':- :- a.\n', 'incomplete_reduction'),
    ('arg_priority_1200', 'foo(a :- b).\n', 'incomplete_reduction'),
    ('list_elem_1200', 'X = [a :- b].\n', 'incomplete_reduction'),
    ('bar_bar', 'X = [a|b|c].\n', 'incomplete_reduction'),
    ('bar_nothing', 'X = [a|].\n', 'incomplete_reduction'),
    ('list_comma_only', 'X = [,].\n', 'incomplete_reduction'),
    ('args_comma_only', 'X = f(,).\n', 'incomplete_reduction'),
    ('empty_args', 'X = f().\n', 'incomplete_reduction'),
    ('args_trailing_comma', 'X = f(a,).\n', 'incomplete_reduction'),
    ('comma_comma', 'a , , b.\n', 'incomplete_reduction'),
    ('minus_then_end', 'X = - .\n', 'incomplete_reduction'),
    ('minus_in_parens', 'X = (- ).\n', None),
    ('juxtaposed_terms', 'foo(a) bar(b).\n', 'incomplete_reduction'),
    ('juxtaposed_atoms', 'X = a b.\n', 'incomplete_reduction'),
    ('call_of_call', 'X = f(a)(b).\n', 'incomplete_reduction'),
    ('quoted_then_name', "X = 'abc'def.\n", 'incomplete_reduction'),
    ('string_then_name', 'X = "abc"def.\n', 'incomplete_reduction'),
    ('charcode_then_name', "X = 0'ab.\n", 'incomplete_reduction'),
    ('bar_alone', 'X = |.\n', 'incomplete_reduction'),
    ('bar_in_args', 'X = f(a|b).\n', 'incomplete_reduction'),
    ('bar_tail_comma', 'X = [a|b,c].\n', 'incomplete_reduction'),
    ('neck_in_eq', 'X = a:-b.\n', None),
    ('float_exp_no_fraction', 'X = 1e+9.\n', 'incomplete_reduction'),
    ('float_dot_exp', 'X = 1.e2.\n', 'incomplete_reduction'),
    ('float_exp_eof', 'X = 1.0e', 'incomplete_reduction'),
    ('float_exp_sign_no_digits', 'X = 1.0e+.\n', 'incomplete_reduction'),
    ('hex_no_digits', 'X = 0x.\n', 'incomplete_reduction'),
    ('hex_bad_digit', 'X = 0xG.\n', 'incomplete_reduction'),
    ('bin_bad_digit', 'X = 0b2.\n', 'incomplete_reduction'),
    ('oct_bad_digit', 'X = 0o8.\n', 'incomplete_reduction'),
    ('charcode_two_quotes', "X = 0''.\n", 'incomplete_reduction'),
    ('charcode_two_quotes_a', "X = 0''a.\n", 'incomplete_reduction'),
    ('charcode_three_quotes', "X = 0'''.\n", None),
    ('float_overflow', 'X = 1.0e400.\n', 'infinite_float'),
    ('float_inf_spelling', 'X = 1.0Inf.\n', 'incomplete_reduction'),
    ('digit_group_trailing', 'X = 1_000_.\n', 'cannot_parse_big_int'),
    ('digit_group_double', 'X = 1__000.\n', 'cannot_parse_big_int'),
    ('leading_dot_float', 'X = .5.\n', 'incomplete_reduction'),
    ('big_int_ok', 'X = 123456789012345678901234567890.\n', None),
    ('control_char', 'X = a\x01.\n', 'unexpected_char'),
    ('pilcrow', 'X = ¶.\n', 'unexpected_char'),
    ('unclosed_block_comment', 'X = a /* never closed\n', 'incomplete_reduction'),
    ('unclosed_block_comment_then', 'X = a. /* never closed\nfoo.\n', None),
    ('tab_in_quoted', "X = 'a\tb'.\n", 'invalid_single_quoted_character'),
    ('nul_in_quoted', "X = 'a\x00b'.\n", 'invalid_single_quoted_character'),
    ('lone_backslash', 'X = \\.\n', 'incomplete_reduction'),
    ('valid_sanity', 'foo(X) :- bar(X, \'a b\', "s", 0\'c, 1.5e3).\n', None),
]

#: Rows where the reader reads a term Scryer refuses, by a lexical rule of
#: its own: the digit-group rule ``digit then (digit | '_')*`` of
#: ``clausal/tools/toklex/specs/iso.toklex.pl`` takes a trailing or doubled
#: ``_`` (``1_000_``, ``1__000`` read as 1000); Scryer's number reader
#: refuses both (``cannot_parse_big_int``).  A lexer question, not an error
#: term one (todo/reader-digit-group-trailing-underscore-2026-10-24.md).
KNOWN_DIFFERENCES = {"digit_group_trailing", "digit_group_double"}

_IDS = [r[0] for r in ROWS]

#: Vocabulary of the formal (Scryer's ``ParserErrorKind::as_atom``).
SCRYER_ATOMS = {
    "incomplete_reduction", "invalid_single_quoted_character",
    "missing_quote", "unexpected_char", "back_quoted_string",
    "infinite_float", "cannot_parse_big_int", "utf8_conversion_error",
    "unexpected_end_of_file", "non_prolog_character", "parse_float",
    "invalid_data", "input_output_error",
}


def _read(text: str):
    """The first item the native front end's reader gives for *text*."""
    items = read_iso(text)
    return items[0] if items else EOF


def test_infinite_float_names_the_literal():
    """found/1 carries the literal's text: a float infinity is no ISO term."""
    item = _read("X = 1.0e400.\n")
    assert isinstance(item, SyntaxIssue) and item.kind == "infinite_float"
    assert item.found == "1.0e400" and item.column == 5
    item = _read("X = -1.0e400.\n")
    assert isinstance(item, SyntaxIssue) and item.found == "1.0e400"


def test_rows_are_well_formed():
    assert len(ROWS) >= 60 and len(set(_IDS)) == len(ROWS)
    for _, _, atom in ROWS:
        assert atom is None or atom in SCRYER_ATOMS, atom
    assert KNOWN_DIFFERENCES <= set(_IDS)


@pytest.mark.parametrize("i", range(len(ROWS)), ids=_IDS)
def test_engine_kind(i):
    ident, text, atom = ROWS[i]
    item = _read(text)
    if ident in KNOWN_DIFFERENCES:
        assert not isinstance(item, SyntaxIssue), item
        return
    if atom is None:
        assert not isinstance(item, SyntaxIssue), item
    else:
        assert isinstance(item, SyntaxIssue), item
        assert item.kind == atom, (item.kind, item.message)


@pytest.mark.parametrize("i", range(len(ROWS)), ids=_IDS)
def test_engine_context_shape(i):
    ident, text, atom = ROWS[i]
    item = _read(text)
    if not isinstance(item, SyntaxIssue):
        return
    term = item.error_term()
    assert term[0] == "error" and len(term) == 3
    assert term[1] == ("syntax_error", item.kind)
    context = term[2]
    assert context[0] == "context" and context[1] == ("/", "read_term", 3)
    details = context[2]
    names = [d[0] for d in details]
    # line and column first, always; expected and found when known.
    assert names[:2] == ["line", "column"], details
    assert names == [n for n in ("line", "column", "expected", "found")
                     if n in names], details
    line, column = details[0][1], details[1][1]
    assert type(line) is int and line >= 1 and type(column) is int and column >= 1
    for name, value in details[2:]:
        assert type(value) in (str, int, float) or (
            type(value) is tuple and value[0] == "priority"), (name, value)
    # the message locates the fault at the same place (the unclosed block
    # comment names its opener's line alone)
    assert f"{line}:{column}" in item.message or f"line {line}" in item.message


def test_oracle(scryer):
    """Each row's text in its own file, read with read_term/3 by Scryer, in
    one process: the atom per row is the table's."""
    del scryer   # the fixture only asserts the binary is there
    with tempfile.TemporaryDirectory() as d:
        argv = [SCRYER]
        for ident, text, _ in ROWS:
            path = os.path.join(d, f"{ident}.pl")
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            argv += ["-g", (
                f"write('{ident}: '), open('{path}', read, S), "
                f"catch((read_term(S, T, []), R = ok), E, R = E), "
                f"close(S), writeq(R), nl")]
        argv += ["-g", "halt"]
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=120, stdin=subprocess.DEVNULL)
    got = {}
    for line in proc.stdout.splitlines():
        ident, sep, rest = line.partition(": ")
        if sep and ident in _IDS:
            got[ident] = rest
    assert set(got) == set(_IDS), proc.stdout[-2000:] + proc.stderr[-2000:]
    for ident, _, atom in ROWS:
        if atom is None:
            assert got[ident] == "ok", (ident, got[ident])
        else:
            assert got[ident].startswith(f"error(syntax_error({atom}),"), \
                (ident, got[ident])


# ── the surfaces ─────────────────────────────────────────────────────────────

_LOAD_ROWS = ["open_args_eof", "xfx_clash_neck", "float_exp_no_fraction",
              "sq_unterminated_nl_more", "dq_bad_escape_q", "float_overflow"]


@pytest.mark.parametrize("ident", _LOAD_ROWS)
def test_load_surface(tmp_path, monkeypatch, ident):
    """A .pl file that fails to load raises a SyntaxError carrying the
    reader's term: the same formal and context as reading the text."""
    text, atom = next((t, a) for i, t, a in ROWS if i == ident)
    name = f"_synerr_{ident}"
    (tmp_path / f"{name}.pl").write_text("ok(1).\n" + text, newline="")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    with pytest.raises(SyntaxError) as ei:
        importlib.import_module(name)
    err = ei.value
    assert isinstance(err, PrologSyntaxError)
    assert err.term[1] == ("syntax_error", atom), err.term
    assert err.term[2][:2] == ("context", ("/", "read_term", 3))
    details = dict(err.term[2][2])
    # the SyntaxError points its caret at the fault: the term's own line
    # (one further down than in the bare text) and column
    assert err.lineno == details["line"] and err.offset == details["column"]
    assert details["line"] >= 2
    assert "syntax error" in str(err) and f"{err.lineno}:{err.offset}" in str(err)


def _pl_module(tmp_path, monkeypatch, name, source):
    (tmp_path / f"{name}.pl").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    return importlib.import_module(name)


def _answer(mod, goal_name):
    r = Var()
    out = [deref(r) for _ in solve((goal_name, r), mod)]
    assert len(out) == 1, out
    return out[0]


TEXT_PROGRAM = """\
t1(E) :- catch(term_to_atom(_, 'foo('), E, true).
t2(E) :- catch(term_to_atom(_, 'a. b'), E, true).
t3(E) :- catch(term_to_atom(_, '  % c'), E, true).
t4(E) :- catch(atom_to_term('X = 1e+9', _, _), E, true).
t5(E) :- catch(atom_to_term('p(a :- b)', _, _), E, true).
t6(E) :- catch(term_to_atom(_, '\\'abc\\n'), E, true).
"""


def test_text_surfaces(tmp_path, monkeypatch):
    """term_to_atom/2 and atom_to_term/3 raise the reader's term with their
    own indicator as the context's: the same vocabulary, the same shape."""
    mod = _pl_module(tmp_path, monkeypatch, "_synerr_text", TEXT_PROGRAM)
    t1 = _answer(mod, "t1")
    assert t1[1] == ("syntax_error", "incomplete_reduction")
    assert t1[2][:2] == ("context", ("/", "term_to_atom", 2))
    d1 = dict(t1[2][2])
    # the text ended where an argument was due: located at its end
    assert d1 == {"line": 1, "column": 5, "expected": "term", "found": "end_of_file"}
    # SWI's two kinds for the text-reading predicates, located
    t2 = _answer(mod, "t2")
    assert t2[1] == ("syntax_error", "end_of_clause_expected")
    assert dict(t2[2][2])["column"] == 4         # where `b` starts
    t3 = _answer(mod, "t3")
    assert t3[1] == ("syntax_error", "end_of_string")
    assert dict(t3[2][2])["found"] == "end_of_file"
    t4 = _answer(mod, "t4")
    assert t4[1] == ("syntax_error", "incomplete_reduction")
    assert t4[2][1] == ("/", "atom_to_term", 3)
    assert dict(t4[2][2])["found"] == "e"
    t5 = _answer(mod, "t5")
    assert t5[1] == ("syntax_error", "incomplete_reduction")
    assert dict(t5[2][2])["expected"] == ")"
    t6 = _answer(mod, "t6")
    assert t6[1] == ("syntax_error", "invalid_single_quoted_character")


NUMBER_PROGRAM = """\
n1(E) :- catch(number_chars(_, [a]), E, true).
n2(E) :- catch(number_chars(_, ['1', ' ', '2']), E, true).
n3(E) :- catch(number_codes(_, [0'0, 0'x]), E, true).
n4(E) :- catch(number_chars(_, ['1', '.', '0', e, '4', '0', '0']), E, true).
n5(E) :- catch(number_chars(_, ['%', ' ', c, '\\n', '-', ' ', x]), E, true).
"""


def test_number_chars_context(tmp_path, monkeypatch):
    """number_chars/2 and number_codes/2 keep Scryer's atoms and get the
    same context shape, located in the text (line, column, found)."""
    mod = _pl_module(tmp_path, monkeypatch, "_synerr_number", NUMBER_PROGRAM)
    assert _answer(mod, "n1") == (
        "error", ("syntax_error", "unexpected_end_of_file"),
        ("context", ("/", "number_chars", 2),
         [("line", 1), ("column", 2), ("found", "end_of_file")]))
    assert _answer(mod, "n2") == (
        "error", ("syntax_error", "unexpected_char"),
        ("context", ("/", "number_chars", 2),
         [("line", 1), ("column", 2), ("found", " ")]))
    assert _answer(mod, "n3") == (
        "error", ("syntax_error", "unexpected_end_of_file"),
        ("context", ("/", "number_codes", 2),
         [("line", 1), ("column", 3), ("found", "end_of_file")]))
    # the literal as written is named, not the infinity (no ISO term)
    assert _answer(mod, "n4") == (
        "error", ("syntax_error", "infinite_float"),
        ("context", ("/", "number_chars", 2),
         [("line", 1), ("column", 1), ("found", "1.0e400")]))
    # a comment line before the fault: the position is on line 2 (the name
    # `x` is consumed to the end of the text, as Scryer consumes it)
    assert _answer(mod, "n5") == (
        "error", ("syntax_error", "unexpected_end_of_file"),
        ("context", ("/", "number_chars", 2),
         [("line", 2), ("column", 4), ("found", "end_of_file")]))


def test_oracle_number_chars_formal(scryer):
    """The number_chars rows above: Scryer's formal for each (its context,
    ``number_chars/2`` or ``number_chars/2:0``, is its own)."""
    del scryer
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "n.pl")
        with open(path, "w") as f:
            f.write(NUMBER_PROGRAM)
        goals = [f"n{i}(E), E = error(F, _), writeq(F), nl" for i in range(1, 6)]
        argv = [SCRYER, path]
        for g in goals:
            argv += ["-g", g]
        argv += ["-g", "halt"]
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=60, stdin=subprocess.DEVNULL)
    lines = [l for l in proc.stdout.splitlines() if l.startswith("syntax_error(")]
    assert lines == [
        "syntax_error(unexpected_end_of_file)", "syntax_error(unexpected_char)",
        "syntax_error(unexpected_end_of_file)", "syntax_error(infinite_float)",
        "syntax_error(unexpected_end_of_file)"], proc.stdout + proc.stderr
