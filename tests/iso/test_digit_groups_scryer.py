"""Digit groups in number tokens, as Scryer reads them (operator ruling
2026-11-03).

Three edges follow Scryer exactly:

* no ``_`` in a fraction: ``1.0_0`` is the float ``1.0`` glued to the
  variable ``_0``, a syntax error (``incomplete_reduction``);
* no ``_`` in a ``0x``/``0o``/``0b`` integer: ``0x1_2``, ``0x_1`` and
  ``0x1_`` are syntax errors (``incomplete_reduction``);
* layout and comments may follow a digit group ``_``: ``1_ 000``,
  ``1_/*c*/000`` and ``1_%c<newline>000`` are the one integer 1000.  The
  digits after the layout continue the decimal number, fraction and
  exponent included (``1_ 0.5`` is 10.5); anything else after the layout
  is ``cannot_parse_big_int``, as a ``_`` with no digit after it was before.

``READER_ROWS`` is read by the native ISO reader (``test_reader``) and by
Scryer's ``read_term/3`` from a file holding the same text
(``test_reader_oracle``).  ``NUMBER_CHARS_ROWS`` does the same for
``number_chars/2``, whose reading of the same text differs from Scryer's
in the rows of ``NUMBER_CHARS_DIFFERENCES`` (see there).
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.tools.iso_l3 import read_iso
from clausal.tools.prolog_reader import EOF, SyntaxIssue

from tests._oracles import SCRYER

#: (row id, text, expected): expected is ``("ok", value)`` for the value
#: of ``X`` in ``X = ...``, or ``("error", formal)``.  Measured against
#: Scryer 2026-11-03.
READER_ROWS = [
    # an underscore in a fraction
    ("fraction", "X = 1.0_0.\n", ("error", "incomplete_reduction")),
    ("fraction_long", "X = 1.00_0.\n", ("error", "incomplete_reduction")),
    ("fraction_exp", "X = 1.0_0e1.\n", ("error", "incomplete_reduction")),
    ("fraction_layout", "X = 1.0_ 0.\n", ("error", "incomplete_reduction")),
    ("exponent", "X = 1.0e1_0.\n", ("error", "incomplete_reduction")),
    # underscores in a radix integer
    ("hex_mid", "X = 0x1_2.\n", ("error", "incomplete_reduction")),
    ("hex_lead", "X = 0x_1.\n", ("error", "incomplete_reduction")),
    ("hex_trail", "X = 0x1_.\n", ("error", "incomplete_reduction")),
    ("hex_only", "X = 0x_.\n", ("error", "incomplete_reduction")),
    ("hex_var", "X = 0x1_A.\n", ("error", "incomplete_reduction")),
    ("hex_layout", "X = 0x1_ 2.\n", ("error", "incomplete_reduction")),
    ("oct_mid", "X = 0o1_2.\n", ("error", "incomplete_reduction")),
    ("oct_lead", "X = 0o_1.\n", ("error", "incomplete_reduction")),
    ("oct_trail", "X = 0o1_.\n", ("error", "incomplete_reduction")),
    ("bin_mid", "X = 0b1_0.\n", ("error", "incomplete_reduction")),
    ("bin_lead", "X = 0b_1.\n", ("error", "incomplete_reduction")),
    ("bin_trail", "X = 0b1_.\n", ("error", "incomplete_reduction")),
    ("charcode_us", "X = 0'a_.\n", ("error", "incomplete_reduction")),
    ("charcode_us_layout", "X = 0'a_ 1.\n", ("error", "incomplete_reduction")),
    # layout and comments after a digit group underscore
    ("layout_space", "X = 1_ 000.\n", ("ok", 1000)),
    ("layout_newline", "X = 1_\n000.\n", ("ok", 1000)),
    ("layout_tab", "X = 1_\t000.\n", ("ok", 1000)),
    ("layout_block", "X = 1_/*c*/000.\n", ("ok", 1000)),
    ("layout_block_empty", "X = 1_/**/000.\n", ("ok", 1000)),
    ("layout_line", "X = 1_%c\n000.\n", ("ok", 1000)),
    ("layout_mixed", "X = 1_ /*c*/ %d\n 000.\n", ("ok", 1000)),
    ("layout_twice", "X = 1_ 000_ 000.\n", ("ok", 1000000)),
    ("layout_after_group", "X = 1_000_ 000_000.\n", ("ok", 1000000000)),
    ("layout_group_after", "X = 1_ 0_0.\n", ("ok", 100)),
    ("layout_leading_zero", "X = 0_ 7.\n", ("ok", 7)),
    ("layout_big", "X = 123_ 456789012345678901234567890.\n",
     ("ok", 123456789012345678901234567890)),
    ("layout_float", "X = 1_ 0.5.\n", ("ok", 10.5)),
    ("layout_float_int", "X = 1_ 000.5.\n", ("ok", 1000.5)),
    ("layout_float_group", "X = 1_ 0_0.5.\n", ("ok", 100.5)),
    ("layout_float_exp", "X = 1_ 0.5e3.\n", ("ok", 10500.0)),
    ("layout_float_overflow", "X = 1_ 0.0e400.\n", ("error", "infinite_float")),
    ("layout_float_then_group", "X = 1_ 0.5_ 0.\n", ("error", "incomplete_reduction")),
    ("layout_negative", "X = - 1_ 000.\n", ("ok", -1000)),
    ("layout_negative_glued", "X = -1_ 000.\n", ("ok", -1000)),
    ("layout_in_args", "X = f(1_ 000).\n", ("ok", ("f", 1000))),
    ("layout_in_list", "X = [1_ 2,3].\n", ("ok", [12, 3])),
    ("layout_in_operand", "X = a- 1_ 0.\n", ("ok", ("-", "a", 10))),
    ("layout_then_layout_end", "X = 1_ 0 .\n", ("ok", 10)),
    # layout after the underscore, then no digit
    ("layout_then_var", "X = 1_ A.\n", ("error", "cannot_parse_big_int")),
    ("layout_then_us_var", "X = 1_ _000.\n", ("error", "cannot_parse_big_int")),
    ("layout_then_atom", "X = 1_ a.\n", ("error", "cannot_parse_big_int")),
    ("layout_then_paren", "X = 1_ (2).\n", ("error", "cannot_parse_big_int")),
    ("layout_then_minus", "X = 1_ -2.\n", ("error", "cannot_parse_big_int")),
    ("layout_then_op", "X = 1_ + 2.\n", ("error", "cannot_parse_big_int")),
    ("layout_then_dot_digit", "X = 1_ .5.\n", ("error", "cannot_parse_big_int")),
    ("layout_then_end", "X = 1_ .\n", ("error", "cannot_parse_big_int")),
    ("layout_then_trailing", "X = 1_ 000_.\n", ("error", "cannot_parse_big_int")),
    ("layout_double_us", "X = 1__ 000.\n", ("error", "cannot_parse_big_int")),
    ("layout_then_eof", "X = 1_ ", ("error", "incomplete_reduction")),
    ("layout_then_open_comment", "X = 1_ /* unterminated",
     ("error", "incomplete_reduction")),
    ("layout_then_hex", "X = 1_ 0x1.\n", ("error", "incomplete_reduction")),
    ("layout_then_oct", "X = 1_ 0o1.\n", ("error", "incomplete_reduction")),
    ("layout_then_e", "X = 1_ 0e1.\n", ("error", "incomplete_reduction")),
    ("layout_before_us", "X = 1 _000.\n", ("error", "incomplete_reduction")),
    # unchanged controls
    ("group_ok", "X = 1_000.\n", ("ok", 1000)),
    ("group_float_ok", "X = 1_0.5.\n", ("ok", 10.5)),
    ("group_trailing", "X = 1_000_.\n", ("error", "cannot_parse_big_int")),
    ("group_double", "X = 1__000.\n", ("error", "cannot_parse_big_int")),
    ("group_end", "X = 1_.\n", ("error", "cannot_parse_big_int")),
    ("hex_ok", "X = 0xff.\n", ("ok", 255)),
]

#: Where Clausal's reader gives another formal than Scryer for the same
#: text, ``(text, ours, Scryer's)``; both refuse it.  A char code after the
#: layout: Scryer continues the number with the digit ``0`` and reads the
#: rest from the quote on as a quoted atom, while here ``0'a`` is one
#: char-code token, which no digit group continues.  So in ``1_ 0'a.``
#: Scryer's quoted atom ``'a.`` meets the newline, and here the ``_`` is
#: refused; in ``1_ 0'a'.`` Scryer reads ``10`` then the atom ``a``, and
#: here the quoted atom ``'.`` after the code meets the newline.
READER_DIFFERENCES = {
    "layout_then_charcode": ("X = 1_ 0'a.\n", "incomplete_reduction",
                             "invalid_single_quoted_character"),
    "layout_then_charcode_quoted": ("X = 1_ 0'a'.\n",
                                    "invalid_single_quoted_character",
                                    "incomplete_reduction"),
}

_READER_IDS = [r[0] for r in READER_ROWS]


def _value(term):
    """A reader term as plain Python: compounds as tuples, lists as lists."""
    if isinstance(term, tuple):
        return tuple(_value(a) for a in term)
    if isinstance(term, list):
        return [_value(a) for a in term]
    return term


def _read_x(text):
    """``("ok", value of X)`` or ``("error", formal)`` for ``X = ...``."""
    items = read_iso(text)
    item = items[0] if items else EOF
    if isinstance(item, SyntaxIssue):
        return ("error", item.kind)
    term = item.term
    assert term[0] == "=", term
    return ("ok", _value(term[2]))


def test_rows_are_well_formed():
    assert len(set(_READER_IDS)) == len(READER_ROWS)
    assert not set(READER_DIFFERENCES) & set(_READER_IDS)


@pytest.mark.parametrize("i", range(len(READER_ROWS)), ids=_READER_IDS)
def test_reader(i):
    _, text, expected = READER_ROWS[i]
    got = _read_x(text)
    assert got == expected
    if expected[0] == "ok":
        assert type(got[1]) is type(expected[1])


@pytest.mark.parametrize("ident", sorted(READER_DIFFERENCES))
def test_reader_difference(ident):
    text, ours, _scryer = READER_DIFFERENCES[ident]
    assert _read_x(text) == ("error", ours)


def _scryer_text(value):
    """*value* as Scryer's writeq/1 prints it."""
    if isinstance(value, tuple):
        if value[0] == "-" and len(value) == 3:
            return f"{_scryer_text(value[1])}-{_scryer_text(value[2])}"
        return f"{value[0]}({','.join(_scryer_text(a) for a in value[1:])})"
    if isinstance(value, list):
        return f"[{','.join(_scryer_text(a) for a in value)}]"
    return repr(value) if isinstance(value, float) else str(value)


def test_reader_oracle(scryer):
    """Every row, and every recorded difference's Scryer side, in its own
    file read with read_term/3 by Scryer in one process."""
    del scryer
    rows = list(READER_ROWS) + [
        (ident, text, ("error", theirs))
        for ident, (text, _ours, theirs) in READER_DIFFERENCES.items()]
    with tempfile.TemporaryDirectory() as d:
        argv = [SCRYER]
        for ident, text, _ in rows:
            path = os.path.join(d, f"{ident}.pl")
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            argv += ["-g", (
                f"write('{ident}: '), open('{path}', read, S), "
                f"catch((read_term(S, (_ = V), []), R = ok(V)), E, R = E), "
                f"close(S), writeq(R), nl")]
        argv += ["-g", "halt"]
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=120, stdin=subprocess.DEVNULL)
    got = {}
    for line in proc.stdout.splitlines():
        ident, sep, rest = line.partition(": ")
        if sep:
            got[ident] = rest
    wrong = []
    for ident, _, (what, payload) in rows:
        if what == "ok":
            want = f"ok({_scryer_text(payload)})"
            ok = got.get(ident) == want
        else:
            want = f"error(syntax_error({payload}),"
            ok = (got.get(ident) or "").startswith(want)
        if not ok:
            wrong.append((ident, want, got.get(ident)))
    assert not wrong, wrong


# ── number_chars/2 ───────────────────────────────────────────────────────────

#: (row id, the text as a list of chars, expected): ``("ok", N)`` or
#: ``("error", formal)``.
NUMBER_CHARS_ROWS = [
    ("group", "1_000", ("ok", 1000)),
    ("leading_layout", " 1_000", ("ok", 1000)),
    ("layout_space", "1_ 000", ("ok", 1000)),
    ("layout_newline", "1_\n000", ("ok", 1000)),
    ("layout_block", "1_/*c*/000", ("ok", 1000)),
    ("layout_line", "1_%c\n000", ("ok", 1000)),
    ("layout_twice", "1_ 000_ 000", ("ok", 1000000)),
    ("layout_group_after", "1_ 0_0", ("ok", 100)),
    ("layout_float", "1_ 0.5", ("ok", 10.5)),
    ("layout_negative", "- 1_ 000", ("ok", -1000)),
    ("fraction", "1.0_0", ("error", "unexpected_char")),
    ("fraction_trailing", "1.0_", ("error", "unexpected_char")),
    ("hex_mid", "0x1_2", ("error", "unexpected_char")),
    ("hex_lead", "0x_1", ("error", "unexpected_char")),
    ("hex_trail", "0x1_", ("error", "unexpected_char")),
    ("oct_mid", "0o1_2", ("error", "unexpected_char")),
    ("bin_mid", "0b1_0", ("error", "unexpected_char")),
    ("layout_then_hex", "1_ 0x1", ("error", "unexpected_char")),
    ("double", "1__000", ("error", "cannot_parse_big_int")),
    ("layout_then_atom", "1_ a", ("error", "cannot_parse_big_int")),
    ("layout_then_us", "1_ _0", ("error", "cannot_parse_big_int")),
    ("before_dot", "1_.5", ("error", "cannot_parse_big_int")),
    ("layout_then_dot", "1_ .5", ("error", "cannot_parse_big_int")),
]

#: Where number_chars/2 here and Scryer's differ.  Scryer's number_chars
#: takes a ``_`` that ends the text (``1_000_``, ``1_``, ``1_ ``) and its
#: own reader refuses the same ``_`` (``cannot_parse_big_int``); here
#: number_chars refuses it as the reader does (``unexpected_char`` at the
#: ``_``, the text's last digit group having no digit after it).
#: ``1_/*c``: a comment the text never closes; Scryer says
#: ``incomplete_reduction``, here the text ends where a number was due.
NUMBER_CHARS_DIFFERENCES = {
    "trailing": ("1_000_", ("error", "unexpected_char"), "ok(1000)"),
    "end": ("1_", ("error", "unexpected_char"), "ok(1)"),
    "end_layout": ("1_ ", ("error", "unexpected_char"), "ok(1)"),
    "open_comment": ("1_/*c", ("error", "unexpected_end_of_file"),
                     "syntax_error(incomplete_reduction)"),
}

_NC_IDS = [r[0] for r in NUMBER_CHARS_ROWS]

NC_PROGRAM = """\
t(A, R) :- atom_chars(A, L),
    catch((number_chars(N, L), R = ok(N)), error(F, _), R = F).
"""


@pytest.fixture(scope="module")
def nc_module(tmp_path_factory):
    d = tmp_path_factory.mktemp("digit_groups")
    (d / "_digit_groups_nc.pl").write_text(NC_PROGRAM)
    sys.path.insert(0, str(d))
    try:
        sys.modules.pop("_digit_groups_nc", None)
        importlib.invalidate_caches()
        yield importlib.import_module("_digit_groups_nc")
    finally:
        sys.path.remove(str(d))


def _number_chars(mod, text):
    r = Var()
    out = []
    for _ in solve(("t", text, r), mod):
        got = deref(r)
        out.append((got[0], deref(got[1])))
    assert len(out) == 1, out
    what, payload = out[0]
    if what == "ok":
        return ("ok", payload)
    assert what == "syntax_error", out
    return ("error", payload)


@pytest.mark.parametrize("i", range(len(NUMBER_CHARS_ROWS)), ids=_NC_IDS)
def test_number_chars(nc_module, i):
    _, text, expected = NUMBER_CHARS_ROWS[i]
    assert _number_chars(nc_module, text) == expected


@pytest.mark.parametrize("ident", sorted(NUMBER_CHARS_DIFFERENCES))
def test_number_chars_difference(nc_module, ident):
    text, ours, _scryer = NUMBER_CHARS_DIFFERENCES[ident]
    assert _number_chars(nc_module, text) == ours


def _quoted(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") \
        .replace("\n", "\\n") + "'"


def test_number_chars_oracle(scryer):
    del scryer
    rows = [(i, t, (f"ok({_scryer_text(v)})" if w == "ok"
                    else f"syntax_error({v})"))
            for i, t, (w, v) in NUMBER_CHARS_ROWS]
    rows += [(i, t, theirs)
             for i, (t, _ours, theirs) in NUMBER_CHARS_DIFFERENCES.items()]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "nc.pl")
        with open(path, "w") as f:
            f.write(NC_PROGRAM)
        argv = [SCRYER, path]
        for ident, text, _ in rows:
            argv += ["-g", f"t({_quoted(text)}, R), write('{ident}: '), "
                           f"writeq(R), nl"]
        argv += ["-g", "halt"]
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=60, stdin=subprocess.DEVNULL)
    got = {}
    for line in proc.stdout.splitlines():
        ident, sep, rest = line.partition(": ")
        if sep:
            got[ident] = rest
    wrong = [(i, want, got.get(i)) for i, _, want in rows if got.get(i) != want]
    assert not wrong, (wrong, proc.stderr[-1000:])
