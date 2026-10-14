"""``0'`` followed by a backslash-newline is not a character code literal.

A backslash-newline inside quoted text is ISO's continuation escape: it
stands for NO character.  ``0'\\<newline>`` therefore names no character
and is not a ``0'c`` token at all; the reader backs up to the integer ``0``
and the ``'`` starts a quoted token of its own, in which the
backslash-newline is the continuation.

Ruled against Ulrich Neumerkel's syntax conformity suite
(https://www.complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing),
``<NL>`` below being a literal newline:

* #213 ``X is 0'\\<NL>+'1.`` -- ``X = 1``: tokens ``0``, ``'+'``, ``1``.
* ``X = 0'\\<NL>+'/*'. %*/1.`` -- ``X = 0+1``: the quoted atom is ``'+'``,
  so ``/*'. %*/`` is a block comment.
* ``X is 1'\\<NL>+'1.`` -- ``X = 2`` (``1'`` was never a prefix; a control).
* ``X = 0'\\<NL>a.`` -- syntax error: ``'\\<NL>a.`` is an unterminated
  quoted atom.

Before the fix the lexer read ``0'\\<NL>`` as one token with value 0
(``builders.char_code`` fell back to 0 for the empty decode).  That made
#213 an unterminated quoted atom, the comment row ``0+'/*'``, and the last
row a syntax error only because ``0 a`` does not parse -- so the token
shapes are pinned here as well as the answers.

Every row runs through BOTH ``.pl`` front ends.
"""

from __future__ import annotations

import pytest

from clausal.tools.prolog_tokenizer import TokenizeError, tokenize

from .test_iso_answers_scryer import _engine_answers
from .test_minus_layout_literal_ulrich import FRONTENDS, _Loads

BS_NL = "\\\n"  # backslash, newline

#: (row, goal) -- every goal must succeed.
READ_OK = [
    ("#213 0'\\<NL>+'1", f"X is 0'{BS_NL}+'1, X == 1"),
    ("0'\\<NL>+'/*'. %*/1", f"X = 0'{BS_NL}+'/*'. %*/1, X == 0+1"),
    ("1'\\<NL>+'1 (control)", f"X is 1'{BS_NL}+'1, X == 2"),
    # Not rows of the suite: the char-code escapes that stay tokens.
    ("0'\\n", "X = 0'\\n, X == 10"),
    ("0'\\\\", "X = 0'\\\\, X == 92"),
    ("0'\\x41\\", "X = 0'\\x41\\, X == 65"),
    ("0'''", "X = 0''', X == 39"),
]

#: (row, goal) -- every goal is a syntax error.
READ_ERR = [
    ("0'\\<NL>a", f"X = 0'{BS_NL}a"),
]


def _kinds_values(text):
    return [(t.type.value, t.value) for t in tokenize(text) if t.type.value != "end"]


def test_tokens_213():
    assert _kinds_values(f"X is 0'{BS_NL}+'1.") == [
        ("var", "X"), ("atom", "is"), ("integer", 0), ("atom", "+"),
        ("integer", 1), (".", ".")]


def test_tokens_comment_row():
    assert _kinds_values(f"X = 0'{BS_NL}+'/*'. %*/1.") == [
        ("var", "X"), ("atom", "="), ("integer", 0), ("atom", "+"),
        ("integer", 1), (".", ".")]


def test_tokens_radix_control():
    assert _kinds_values(f"X is 1'{BS_NL}+'1.") == [
        ("var", "X"), ("atom", "is"), ("integer", 1), ("atom", "+"),
        ("integer", 1), (".", ".")]


def test_tokens_error_row_is_an_unterminated_quoted_atom():
    """Not ``0`` then ``a``: the quote opens a quoted atom that never ends."""
    with pytest.raises(TokenizeError, match="[Uu]nterminated quoted"):
        list(tokenize(f"X = 0'{BS_NL}a."))


def test_lone_continuation_at_eof_is_not_a_char_code():
    with pytest.raises(TokenizeError):
        list(tokenize(f"X = 0'{BS_NL}"))


@pytest.fixture(scope="module")
def loads(tmp_path_factory):
    d = tmp_path_factory.mktemp("char_code_continuation")
    mp = pytest.MonkeyPatch()
    mp.syspath_prepend(str(d))
    lo = _Loads(d, mp)
    try:
        yield lo
    finally:
        import sys
        for n in lo.names:
            sys.modules.pop(n, None)
        mp.undo()


@pytest.mark.parametrize("fe", FRONTENDS)
@pytest.mark.parametrize("i", range(len(READ_OK)), ids=[r[0] for r in READ_OK])
def test_read(loads, fe, i):
    mod = loads.load(f"_ccnl_ok{i}_{fe}", f"r(R) :- {READ_OK[i][1]}, R = true.\n", fe)
    assert _engine_answers(mod, "r", 2) == ["true"]


@pytest.mark.parametrize("fe", FRONTENDS)
@pytest.mark.parametrize("i", range(len(READ_ERR)), ids=[r[0] for r in READ_ERR])
def test_syntax_error(loads, fe, i):
    """The translator front end lets every LEXICAL error out as a bare
    TokenizeError (not a SyntaxError subclass) -- a plain unterminated
    ``'abc`` does the same, independent of this row -- so it is accepted
    there; the native front end must raise SyntaxError.  Both must name the
    unterminated quoted atom: before the fix this was a syntax error only
    because ``0 a`` does not parse (``Expected '.', got 'atom'``)."""
    name, goal = f"_ccnl_err{i}_{fe}", READ_ERR[i][1]
    want = SyntaxError if fe == "native" else (SyntaxError, TokenizeError)
    with pytest.raises(want, match="[Uu]nterminated quoted"):
        loads.load(name, f"r(R) :- {goal}, R = true.\n", fe)
