"""Three lexer-grammar bugs found by a diagnostic sweep against Ciao's
``iso_tests_parsing_lexing`` corpus, sanity-checked against the ISO
13211-1 grammar text itself (not just Ciao's reading of it), ahead of the
2026-10-15 review with Ulrich Neumerkel.

Bug 1 -- ISO 6.4.2.1's escape-sequence set inside a quoted atom/string is
CLOSED: the named escapes (``\\a \\b \\f \\n \\r \\t \\v``), ``\\\\``,
``\\'``, ``\\"``, `` \\` ``, octal ``\\NNN\\`` (closing backslash
MANDATORY), hex ``\\xHH\\`` (closing backslash MANDATORY), and
backslash-newline (line continuation). Anything else after a backslash,
or a raw unescaped control/layout byte (other than space) inside the
quotes, is a syntax error. Clausal previously:
  (a) kept ANY unrecognized ``\\c`` verbatim as 2 literal chars instead of
      raising (``\\e`` ESC and ``\\s`` space are SWI/non-ISO extensions,
      not in the ISO set either);
  (b) accepted a raw unescaped control/layout byte (e.g. a literal
      newline) as 1 literal char;
  (c) treated an octal/hex escape's closing backslash as optional, so
      ``'\\141'`` (no closing ``\\``) was read as octal 141 = ``'a'``
      instead of raising.

Bug 2 -- ISO's ``<integer>`` token grammar names the hex/octal/binary
radix letters (``x``/``o``/``b``) as LOWERCASE-ONLY terminals. ``0X1``/
``0O17``/``0B101`` are not number tokens at all; Clausal accepted the
uppercase forms too. The float exponent char is ``e`` OR ``E`` (ISO 6.4.5),
so ``1.5E9`` is a float; ``1E9`` fails only for its missing fraction (Bug 3).

Bug 3 -- ISO's ``<float number>`` is
``<integer part> . <fraction part> [<exponent part>]``: the ``.`` and
fraction are MANDATORY, so an exponent can never appear without them.
``1e9`` (no ``.``) was read as the float 1000000000.0; per the grammar it
must instead lex as the integer ``1`` followed by a separate token (here,
the atom ``e9``, since ``e`` is small-initial).

See ``clausal/tools/toklex/specs/iso.toklex.pl``'s 2026-10-15 comments
(search "Ulrich conformity pass") for the grammar-level fix behind each
case tested here. All three bugs are fixed for the native ISO reader
(``iso.toklex.pl``) only; Bug 1 is left alone in the separate
``clausal.toklex.pl`` surface dialect (not trying to be ISO-conformant --
see that file's header), while Bugs 2/3 are fixed in both (accidental,
non-dialect-specific duplication -- see that file's "kept in sync"
comments).
"""

from __future__ import annotations

import shutil
import sys

import pytest

from clausal import import_hook as ih
from clausal.tools.prolog_tokenizer import TokenizeError, TokenType, tokenize

from .test_iso_answers_scryer import _engine_answers


def _kv(src, n=4):
    """First *n* (type, value) pairs, END excluded for brevity."""
    return [(t.type, t.value) for t in tokenize(src) if t.type != TokenType.END][:n]


# ── Bug 1a: the closed escape-sequence set (ISO 6.4.2.1) ────────────────

UNRECOGNIZED_ESCAPES = [
    "'\\ca'.",   # \c is not an escape letter at all
    "'\\e1'.",   # \e (ESC) is a SWI/non-ISO extension, not ISO's set
    "'\\s'.",    # \s (space) is likewise a SWI/non-ISO extension
    "'\\u1'.",   # incomplete hex-unicode-style escape; \u is not ISO either
    "'\\z'.",    # arbitrary unrecognized letter
    '"\\c".',    # the same hole, inside a double-quoted string
]


@pytest.mark.parametrize("src", UNRECOGNIZED_ESCAPES)
def test_unrecognized_escape_is_a_syntax_error(src):
    with pytest.raises(TokenizeError):
        tokenize(src)


def test_closed_escape_set_still_lexes_every_iso_symbolic_escape():
    # ISO 6.4.2.1 Table 2's ten symbolic escapes, all in one quoted atom.
    toks = _kv("'\\a\\b\\f\\n\\r\\t\\v\\\\\\'\\\"\\`'.", n=1)
    assert toks == [(TokenType.ATOM, "\a\b\f\n\r\t\v\\'\"`")]


def test_closed_escape_set_applies_to_strings_too():
    assert _kv('"\\n\\t".', n=1) == [(TokenType.STRING, "\n\t")]


# ── Bug 1b: no raw control/layout byte (other than space) in quotes ─────

RAW_CONTROL_BYTES_REJECTED = [
    "'ab\ncd'.",   # raw newline
    "'ab\tcd'.",   # raw tab
    "'ab\rcd'.",   # raw carriage return
    '"ab\ncd".',   # same hole, string
]


@pytest.mark.parametrize("src", RAW_CONTROL_BYTES_REJECTED)
def test_raw_control_byte_in_quotes_is_a_syntax_error(src):
    with pytest.raises(TokenizeError):
        tokenize(src)


def test_literal_space_in_quotes_is_still_fine():
    # Space is explicitly permitted literal content, unlike other layout
    # bytes -- it must NOT be swept into the same exclusion.
    assert _kv("'a b'.", n=1) == [(TokenType.ATOM, "a b")]


def test_backslash_newline_continuation_still_fine():
    # The ONE way a newline may appear adjacent to quoted content: as the
    # escaped line-continuation, which stands for no character at all.
    assert _kv("'ab\\\ncd'.", n=1) == [(TokenType.ATOM, "abcd")]


# ── Bug 1c: octal/hex escape closing backslash is mandatory ─────────────

MISSING_CLOSING_BACKSLASH_REJECTED = [
    "'\\141'.",     # octal 141, no closing \
    "'\\x61'.",     # hex 61, no closing \
    "'ab\\141cd'.", # same hole, mid-string content after
]


@pytest.mark.parametrize("src", MISSING_CLOSING_BACKSLASH_REJECTED)
def test_octal_or_hex_escape_without_closing_backslash_is_a_syntax_error(src):
    with pytest.raises(TokenizeError):
        tokenize(src)


def test_octal_escape_with_closing_backslash_still_decodes():
    assert _kv("'\\141\\'.", n=1) == [(TokenType.ATOM, "a")]  # 0o141 == ord('a')


def test_hex_escape_with_closing_backslash_still_decodes():
    assert _kv("'\\x61\\'.", n=1) == [(TokenType.ATOM, "a")]  # 0x61 == ord('a')


# ── Bug 2: lowercase-only radix letters ──────────────────────────────────

UPPERCASE_RADIX_FALLBACKS = [
    # (src, expected (type, value) pairs for the fallback reading)
    ("0X1.", [(TokenType.INTEGER, 0), (TokenType.VAR, "X1")]),
    ("0O17.", [(TokenType.INTEGER, 0), (TokenType.VAR, "O17")]),
    ("0B101.", [(TokenType.INTEGER, 0), (TokenType.VAR, "B101")]),
    # No fraction, so no float (Bug 3); the capital remainder is a VARIABLE.
    ("1E9.", [(TokenType.INTEGER, 1), (TokenType.VAR, "E9")]),
]


@pytest.mark.parametrize("src,value", [
    ("1.5E9.", 1.5e9),
    ("1.0E-3.", 1.0e-3),
    ("1.0E+2.", 100.0),
])
def test_uppercase_exponent_char_with_fraction_is_a_float(src, value):
    # ISO 6.4.5: exponent char = "e" | "E" (Scryer and Trealla agree).
    assert _kv(src, n=1) == [(TokenType.FLOAT, value)]


@pytest.mark.parametrize("src,want", UPPERCASE_RADIX_FALLBACKS)
def test_uppercase_radix_or_exponent_letter_is_not_a_number_token(src, want):
    # Established fallback convention (same shape as the pre-existing
    # EXPECTED_DIVERGENCES in tests/toklex/test_parity.py for `0x.`/
    # `1.5e.`): maximal munch backs up to the shorter number token, and
    # the uppercase-led remainder lexes as whatever token actually claims
    # a capital-initial run in this grammar -- a VARIABLE, not an atom,
    # since `token(variable, (capital | '_') then alnum*)` is the rule
    # that owns capital-led content here.
    assert _kv(src, n=2) == want


def test_lowercase_radix_letters_still_work():
    assert _kv("0x1F.", n=1) == [(TokenType.INTEGER, 31)]
    assert _kv("0o17.", n=1) == [(TokenType.INTEGER, 15)]
    assert _kv("0b101.", n=1) == [(TokenType.INTEGER, 5)]


# ── Bug 3: an exponent needs the mandatory '.'-fraction ──────────────────

EXPONENT_WITHOUT_FRACTION_FALLBACKS = [
    ("1e9.", [(TokenType.INTEGER, 1), (TokenType.ATOM, "e9")]),
    ("12e100.", [(TokenType.INTEGER, 12), (TokenType.ATOM, "e100")]),
    ("1e-9.", [(TokenType.INTEGER, 1), (TokenType.ATOM, "e")]),
]


@pytest.mark.parametrize("src,want", EXPONENT_WITHOUT_FRACTION_FALLBACKS)
def test_exponent_without_fraction_is_not_a_float_token(src, want):
    # `e9`/`e100` land as a single NAME_ATOM (`e...`/`e...` is small-initial,
    # and `alnum*` eats the digits) -- available, per the brief, to be
    # parsed as e.g. a postfix operator atom rather than silently fused
    # into the number. `1e-9.`'s `-` is not part of `name_atom`'s
    # `alnum*`, so only the bare `e` atom is claimed; the `-9` that
    # follows is a separate, ordinary read (unrelated to this bug --
    # sign/negative-number adjacency is out of scope here).
    got = [(t.type, t.value) for t in tokenize(src) if t.type != TokenType.END][:2]
    assert got == want


def test_exponent_with_mandatory_fraction_still_works():
    # The control case the brief asks to confirm: `1.5e9` HAS the
    # mandatory `.5`, so it is unaffected and still chains the exponent
    # onto one float token.
    assert _kv("1.5e9.", n=1) == [(TokenType.FLOAT, 1.5e9)]
    assert _kv("1.0e7.", n=1) == [(TokenType.FLOAT, 1.0e7)]


# ── End-to-end: the native .pl reader raises SyntaxError, not a leaked ──
# TokenizeError, for a representative case of each bug; and a
# representative legitimate program for each still runs correctly.


class _Loads:
    def __init__(self, tmp, monkeypatch):
        self.tmp, self.mp, self.names = tmp, monkeypatch, []

    def load(self, name: str, text: str):
        import importlib

        path = self.tmp / f"{name}.pl"
        path.write_text(text, encoding="utf-8")
        self.mp.setenv(ih.PL_FRONTEND_ENV, "native")
        for p in self.tmp.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        sys.modules.pop(name, None)
        self.names.append(name)
        importlib.invalidate_caches()
        mod = importlib.import_module(name)
        assert type(mod.__loader__) is ih.NativePrologLoader
        return mod


@pytest.fixture(scope="module")
def loads(tmp_path_factory):
    d = tmp_path_factory.mktemp("number_and_escape_lexing")
    mp = pytest.MonkeyPatch()
    mp.syspath_prepend(str(d))
    lo = _Loads(d, mp)
    try:
        yield lo
    finally:
        for n in lo.names:
            sys.modules.pop(n, None)
        mp.undo()


ENGINE_SYNTAX_ERROR_ROWS = [
    ("bug1a unrecognized escape", "r(R) :- X = '\\ca', R = X.\n"),
    ("bug1b raw newline in quotes", "r(R) :- X = 'ab\ncd', R = X.\n"),
    ("bug1c octal missing closing backslash", "r(R) :- X = '\\141', R = X.\n"),
]


@pytest.mark.parametrize(
    "i", range(len(ENGINE_SYNTAX_ERROR_ROWS)),
    ids=[r[0] for r in ENGINE_SYNTAX_ERROR_ROWS])
def test_engine_raises_syntax_error_not_a_leaked_tokenize_error(loads, i):
    name, text = f"_numesc_err{i}", ENGINE_SYNTAX_ERROR_ROWS[i][1]
    with pytest.raises(SyntaxError) as ei:
        loads.load(name, text)
    assert not isinstance(ei.value, TokenizeError)


#: (row, goal) -- every goal must succeed (as a real conjunction of
#: comparison GOALS, not structural unification -- matching the
#: ``, R = true`` idiom used throughout this test package).
ENGINE_OK_ROWS = [
    ("bug1 control: closed escapes + mandatory octal close",
     "X = '\\141\\', Y = '\\n\\t', X == a, Y == '\\n\\t'"),
    ("bug2 control: lowercase radix", "X is 0x1F, X == 31"),
    ("bug3 control: exponent with mandatory fraction",
     "X is 1.5e2, X == 150.0"),
]


@pytest.mark.parametrize(
    "i", range(len(ENGINE_OK_ROWS)), ids=[r[0] for r in ENGINE_OK_ROWS])
def test_engine_still_accepts_the_legitimate_control_case(loads, i):
    name, goal = f"_numesc_ok{i}", ENGINE_OK_ROWS[i][1]
    mod = loads.load(name, f"r(R) :- {goal}, R = true.\n")
    assert _engine_answers(mod, "r", 2) == ["true"]


# ── Bug 4: char_code's ``0'`` single quoted character ───────────────────
#
# ISO 6.4.4 / 6.4.2.1: after ``0'`` comes ONE single quoted character, and
# a lone quote is not one (a quote must be doubled, ``0'''``), nor is a raw
# layout byte other than space. ``0''`` must back up to the integer ``0``
# followed by the atom ``''`` (Ulrich #117 ``integer(0'').`` is a syntax
# error; #120 ``functor(0''1,F,A)`` under ``op(100,xfx,'')`` gives
# ``F = ''``), and ``0'<TAB>`` leaves a quoted token holding a raw tab
# (#177, syntax error).

def test_lone_quote_after_0_quote_is_integer_then_empty_atom():
    assert _kv("0''.", n=2) == [(TokenType.INTEGER, 0), (TokenType.ATOM, "")]


@pytest.mark.parametrize("src", ["0'\t.", "0'\n.", "X = 0'\t."])
def test_raw_layout_after_0_quote_is_a_syntax_error(src):
    with pytest.raises(TokenizeError):
        tokenize(src)


@pytest.mark.parametrize("src, code", [
    ("0'''.", 39),     # #115: the doubled quote
    ("0'\\'.", 39),    # #114: the escaped quote
    ("0' .", 32),      # space is a single quoted character
    ("0'a.", 97),
    ("0'\\t.", 9),     # the escape, not a raw tab
])
def test_legitimate_char_codes_still_read(src, code):
    assert _kv(src, n=1) == [(TokenType.INTEGER, code)]


CHAR_CODE_SYNTAX_ERROR_ROWS = [
    ("#117 integer(0'')", "r(R) :- integer(0''), R = true.\n"),
    ("#177 raw tab after 0'", "r(R) :- 0'\\t = 0'\t, R = true.\n"),
]


@pytest.mark.parametrize(
    "i", range(len(CHAR_CODE_SYNTAX_ERROR_ROWS)),
    ids=[r[0] for r in CHAR_CODE_SYNTAX_ERROR_ROWS])
def test_engine_char_code_row_is_a_syntax_error(loads, i):
    name, text = f"_numesc_cc{i}", CHAR_CODE_SYNTAX_ERROR_ROWS[i][1]
    with pytest.raises(SyntaxError) as ei:
        loads.load(name, text)
    assert not isinstance(ei.value, TokenizeError)


# ── Bug 5: a 0' escape uses the quoted-token escape grammar ─────────────
#
# After ``0'\`` comes one ISO 6.4.2.1 escape: a symbolic escape from the
# closed set, or an octal/hex escape WITH its closing backslash. ``\e`` and
# ``\s`` are not escapes, and ``0'\141`` (no closing ``\``) is not 97 --
# the same rules ``'\e'`` and ``'\141'`` already follow inside quotes.

@pytest.mark.parametrize("src", [
    "X = 0'\\141.",    # octal, no closing backslash
    "X = 0'\\x41.",    # hex, no closing backslash
    "X = 0'\\e.",      # ESC: not an ISO escape
    "X = 0'\\s.",      # space: not an ISO escape
    "X = 0'\\z.",
])
def test_bad_escape_after_0_quote_is_a_syntax_error(src):
    with pytest.raises(TokenizeError):
        tokenize(src)


@pytest.mark.parametrize("src, code", [
    ("0'\\141\\.", 97),
    ("0'\\x41\\.", 65),
    ("0'\\n.", 10),
    ("0'\\\\.", 92),
    ("0'\\`.", 96),
])
def test_closed_escapes_after_0_quote_still_read(src, code):
    assert _kv(src, n=1) == [(TokenType.INTEGER, code)]


# ── Bug 6: no raw control character anywhere in a quoted token ──────────
#
# ISO 6.4.2.1's single quoted character is a graphic, alphanumeric, solo or
# space char, or an escape; a control character is none of these. Bug 1b
# excluded only the layout controls (TAB, NL, CR, FF, VT). Every Unicode
# ``Cc`` character -- C0, DEL and C1 -- is now refused, as Scryer does.

@pytest.mark.parametrize("cp", [0x00, 0x01, 0x1B, 0x1F, 0x7F, 0x85, 0x9F])
@pytest.mark.parametrize("shape", ["'a{c}b'.", '"a{c}b".', "0'{c}."])
def test_raw_control_character_is_a_syntax_error(shape, cp):
    with pytest.raises(TokenizeError):
        tokenize(shape.format(c=chr(cp)))


@pytest.mark.parametrize("ch", ["é", "λ", "—", "­"])
def test_non_control_unicode_in_quotes_still_reads(ch):
    assert _kv(f"'a{ch}b'.", n=1) == [(TokenType.ATOM, f"a{ch}b")]


# ── The error names the fault, at its own position ─────────────────────

@pytest.mark.parametrize("src, msg, line, col", [
    ("X = 'ab\\zcd'.", "Invalid escape sequence '\\z' in quoted atom", 1, 8),
    ("X = '\\ '.", "Invalid escape sequence \\ followed by U+0020 in quoted atom", 1, 6),
    ("X = '\\\t'.", "Invalid escape sequence \\ followed by U+0009 in quoted atom", 1, 6),
    ("X = 'a\x01b'.", "Raw control character U+0001 in quoted atom", 1, 7),
    ("X = '\\141'.", "Octal escape '\\141' needs a closing backslash", 1, 6),
    ('X = "a\\x41b".', "Hex escape '\\x41b' needs a closing backslash", 1, 7),
    ("X = 0'\\e.", "Invalid escape sequence '\\e' in 0' character code", 1, 7),
    ("X = 0'\\141.", "Octal escape '\\141' needs a closing backslash in 0'", 1, 7),
    ("Y = 1,\n X = 'q\\cz'.", "Invalid escape sequence '\\c' in quoted atom", 2, 8),
    ("X = 'ab\ncd'.", "Unterminated quoted atom", 1, 5),
])
def test_tokenize_error_names_the_fault_at_its_position(src, msg, line, col):
    with pytest.raises(TokenizeError) as ei:
        tokenize(src)
    assert msg in str(ei.value)
    assert (ei.value.line, ei.value.col) == (line, col)


def test_engine_error_names_the_bad_escape(loads):
    with pytest.raises(SyntaxError, match=r"invalid escape sequence '\\z' in quoted atom at 1:16"):
        loads.load("_numesc_diag", "r(R) :- X = 'ab\\zcd', R = X.\n")
