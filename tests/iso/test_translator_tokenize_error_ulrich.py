"""A lexical error in a ``.pl`` file is a syntax error under the translator
front end too, not a leaked ``TokenizeError``.

Ulrich Neumerkel's syntax conformity suite
(https://www.complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing,
fetched 2026-10-14) marks each of these rows ``syntax err.`` for 13211-1:

* #121 ``X = 2'1.``
* #129 ``X is 0'mod'1.``
* #206 ``op(100,xf,f). writeq(0'f').``
* #281 ``writeq(00'a).``

Each lexes to a quoted atom that never closes.  The native front end
reported a ``SyntaxError``; the translator let the tokenizer's own
``TokenizeError`` escape the import, because ``prolog_parser.parse`` passed
it through and the translator's callers convert only ``ParseError`` and
``PrologTranslationError``.  The rows run here as clause bodies (#206 with
its ``op/3`` as a directive) through BOTH ``.pl`` front ends and through
the sandbox's translator route.
"""

from __future__ import annotations

import itertools

import pytest

from clausal import import_hook as ih
from clausal.tools.prolog_tokenizer import TokenizeError

FRONTENDS = ("native", "translator")

#: (row, file text) -- every one must refuse the load with a SyntaxError.
ROWS = [
    ("#121 X = 2'1", "r(R) :- X = 2'1, R = X.\n"),
    ("#129 X is 0'mod'1", "r(R) :- X is 0'mod'1, R = X.\n"),
    ("#206 writeq(0'f') after op(100,xf,f)",
     ":- op(100,xf,f).\nr(R) :- writeq(0'f'), R = true.\n"),
    ("#281 writeq(00'a)", "r(R) :- writeq(00'a), R = true.\n"),
    # Not a row of the suite: the plain shape all four lex to.
    ("plain unclosed 'abc", "r(R) :- X = 'abc, R = X.\n"),
]

_N = itertools.count()


def _write(tmp_path, stem, text):
    name = f"_tokerr_{stem}_{next(_N)}"
    p = tmp_path / f"{name}.pl"
    p.write_text(text, encoding="utf-8")
    return name, str(p)


@pytest.mark.parametrize("fe", FRONTENDS)
@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_row_is_a_syntax_error(tmp_path, monkeypatch, fe, i):
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, fe)
    name, path = _write(tmp_path, fe, ROWS[i][1])
    assert (ih._prolog_loader_class_for(path) is ih.NativePrologLoader) \
        == (fe == "native")
    with pytest.raises(SyntaxError) as ei:
        ih._load_module(name, path)
    # Not a TokenizeError wearing a SyntaxError: the load reports the file.
    assert not isinstance(ei.value, TokenizeError)
    assert path in str(ei.value)


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_translator_error_names_the_lexical_fault(tmp_path, monkeypatch, i):
    # The tokenizer's message and position survive the conversion, chained.
    #
    # 2026-10-15 (Ulrich conformity pass, Bug 1b): every row here is
    # written to a file via `_write`, which always ends in a trailing
    # `\n`. A raw, unescaped newline is no longer legal content inside a
    # quoted atom (ISO 6.4.2.1), so the still-open quoted atom from each
    # row's lexical fault now gets stuck AT that trailing newline instead
    # of running on to a clean end-of-input -- the message is "Unexpected
    # character" at the opening quote's position rather than "Unterminated
    # quoted atom" at EOF. Still unambiguously the same syntax error over
    # the same quoted-atom construct; accept either wording.
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, "translator")
    name, path = _write(tmp_path, "msg", ROWS[i][1])
    with pytest.raises(SyntaxError) as ei:
        ih._load_module(name, path)
    msg = str(ei.value)
    assert "Unterminated quoted atom" in msg or "Unexpected character" in msg
    cause = ei.value.__cause__
    assert cause is not None and isinstance(cause.__cause__, TokenizeError)
    line = 2 if i == 2 else 1
    assert (cause.line, cause.col) == (cause.__cause__.line,
                                       cause.__cause__.col)
    assert cause.line == line


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_sandbox_translator_route_is_a_syntax_error(tmp_path, i):
    # clausal/sandbox.py converts the same two exception types itself.
    from clausal import sandbox
    name, path = _write(tmp_path, "sbx", ROWS[i][1])
    loader = ih.PrologLoader(name, path)
    with pytest.raises(SyntaxError) as ei:
        sandbox.sandboxed_code(loader, name)
    assert not isinstance(ei.value, TokenizeError)


def test_control_parser_error_is_already_converted(tmp_path, monkeypatch):
    # A parser-level syntax error (no lexical fault) was converted before
    # this fix; the rows above must now match its shape.
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, "translator")
    name, path = _write(tmp_path, "ctl", "r(R) :- X = (a b), R = X.\n")
    with pytest.raises(SyntaxError) as ei:
        ih._load_module(name, path)
    assert str(ei.value).startswith(f"Cannot import {path}: ")
