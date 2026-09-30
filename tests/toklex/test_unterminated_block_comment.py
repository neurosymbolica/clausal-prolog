"""An unterminated ``/*`` block comment is a SYNTAX ERROR (operator ruling
2026-09-30, reversing toklex locked design decision #4 "lenient
nest-at-EOF").

Before the ruling both lexers (``IncrementalLexer`` and ``RegexLexer``)
consumed an unclosed comment to EOF as trivia and returned a plain EOF, so
``read_module("foo(a).\\n/* never closed")`` gave one clause and no issue,
and a ``.pl`` file ending in an unclosed comment loaded as if the rest of
the file were not there.  Now the L0 layer emits ONE
``('unterminated', <comment text>)`` error token spanning the comment from
its outermost opener, and every front end that reads Prolog text turns it
into a syntax error: the reader (a ``resumable=False`` ``SyntaxIssue``),
the public ``tokenize()`` (``TokenizeError``), and both ``.pl`` loaders.

Scryer (clean clpq build) for the same inputs: consulting a file with an
unclosed ``/*`` prints ``error(syntax_error(incomplete_reduction),
load/1:_)`` and abandons the load; ``read/1`` on a stream returns the terms
before the comment, then raises ``syntax_error(incomplete_reduction)``.
"""
import itertools
import sys

import pytest

from clausal.tools.prolog_reader import (EOF, Clause, PrologReader,
                                         SyntaxIssue, read_module)
from clausal.tools.prolog_tokenizer import TokenizeError, tokenize
from clausal.tools.toklex import load_lexer
from clausal.tools.toklex.driver import EOF as LEX_EOF
from clausal.tools.toklex.driver import NEED_MORE, IncrementalLexer
from clausal.tools.toklex.regex_target import RegexLexer

LEXERS = [IncrementalLexer, RegexLexer]


def _stream(cls, text, **kw):
    return [(t.kind, t.value, t.lexeme, t.start, t.end, t.glue)
            for t in cls(load_lexer(), **kw).run(text)]


def _chunked(cls, text, **kw):
    """Feed one character at a time, draining between feeds."""
    lx = cls(load_lexer(), **kw)
    out = []
    for ch in text:
        lx.feed(ch)
        while (t := lx.next_token()) is not NEED_MORE:
            if t is LEX_EOF:
                break
            out.append(t)
    lx.close()
    while (t := lx.next_token()) is not LEX_EOF:
        assert t is not NEED_MORE
        out.append(t)
    return [(t.kind, t.value, t.lexeme, t.start, t.end, t.glue) for t in out]


# ── L0: both lexers emit the error token, in parity ─────────────────────

@pytest.mark.parametrize("cls", LEXERS)
def test_unclosed_comment_is_one_unterminated_error_token(cls):
    toks = _stream(cls, "foo(a).\n/* never\nclosed")
    assert [k for k, *_ in toks] == ["name_atom", "lparen", "name_atom", "rparen",
                                     "end", "error"]
    kind, value, lexeme, start, end, _glue = toks[-1]
    assert value == ("unterminated", "/* never\nclosed")
    assert lexeme == "/* never\nclosed"
    assert start == (8, 2, 1)          # the opener: offset, line, column
    assert end == (23, 3, 7)


@pytest.mark.parametrize("cls", LEXERS)
def test_unclosed_inner_comment_is_unterminated_when_nesting(cls):
    # nested_comments=True (the dialect default): the inner `/*` opens a
    # second level, the one `*/` closes only it, so the outer never closes.
    toks = _stream(cls, "a. /* outer /* inner */ still open\n")
    assert toks[-1][1] == ("unterminated",
                           "/* outer /* inner */ still open\n")
    assert toks[-1][3][0] == 3         # spans from the OUTERMOST opener


@pytest.mark.parametrize("cls", LEXERS)
def test_same_text_without_nesting_is_closed(cls):
    toks = _stream(cls, "a. /* outer /* inner */ b.\n", nested_comments=False)
    assert all(k != "error" for k, *_ in toks)
    assert [v for k, v, *_ in toks if k == "name_atom"] == ["a", "b"]


@pytest.mark.parametrize("src", [
    "/*", "/* x", "a. /* x", "a /* x", "/* /* */", "a. /* x */ b. /* y",
    "/* a\n/* b\n/* c */\n", "f(/* x", "'q' /* x",
])
@pytest.mark.parametrize("nested", [True, False])
def test_parity_and_chunk_insensitivity(src, nested):
    ref = _stream(IncrementalLexer, src, nested_comments=nested)
    assert _stream(RegexLexer, src, nested_comments=nested) == ref
    assert _chunked(IncrementalLexer, src, nested_comments=nested) == ref
    assert _chunked(RegexLexer, src, nested_comments=nested) == ref


@pytest.mark.parametrize("cls", LEXERS)
def test_closed_comment_at_eof_is_not_an_error(cls):
    assert all(k != "error" for k, *_ in _stream(cls, "a. /* x */"))
    assert all(k != "error" for k, *_ in _stream(cls, "a. /**/"))


# ── L1: the reader ───────────────────────────────────────────────────────

def test_read_module_reports_the_unclosed_comment():
    items = read_module("foo(a).\n/* never closed")
    assert [type(i) for i in items] == [Clause, SyntaxIssue]
    issue = items[1]
    assert issue.resumable is False
    assert issue.span == (8, 23)
    assert "unterminated block comment" in issue.message
    assert "line 2" in issue.message
    assert "incomplete_reduction" in issue.message


def test_read_term_gives_the_terms_before_then_the_error():
    # Scryer's read/1: the first read returns foo, the next one raises.
    r = PrologReader()
    r.feed("foo.\nbar.\n/* x\n")
    r.close()
    assert type(r.read_term()) is Clause
    assert type(r.read_term()) is Clause
    issue = r.read_term()
    assert type(issue) is SyntaxIssue and issue.resumable is False
    assert r.read_term() is EOF


def test_comment_opened_inside_an_item_names_the_opener_line():
    items = read_module("foo(a)\n\n/* x\n")
    assert len(items) == 1 and type(items[0]) is SyntaxIssue
    assert items[0].span[0] == 0                 # the item's start ...
    assert "opened at line 3" in items[0].message  # ... and the opener's line


def test_stray_opener_in_a_header_comment():
    # The crypto.pl shape: a stray `/*` inside a comment. With nesting it
    # never closes -- an error now, not a silently empty file; read with
    # nested_comments=False (ISO, Scryer) the file reads normally.
    src = "/* see http://x/* for more */\nfoo(a).\n"
    items = read_module(src)
    assert [type(i) for i in items] == [SyntaxIssue]
    assert [type(i) for i in read_module(src, nested_comments=False)] == [Clause]


def test_tokenize_raises_at_the_opener():
    with pytest.raises(TokenizeError) as ei:
        tokenize("foo(a).\n\n  /* never closed\n")
    assert "Unterminated block comment" in str(ei.value)
    assert (ei.value.line, ei.value.col) == (3, 3)


# ── the .pl loaders ──────────────────────────────────────────────────────

_N = itertools.count()
PL = "foo(a).\nbar(b).\n\n/* never\nclosed\nbaz(c).\n"


def test_native_loader_refuses_the_whole_file(tmp_path, monkeypatch):
    from clausal.import_hook import _load_module
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    name = f"_unclosed_native_{next(_N)}"
    p = tmp_path / f"{name}.pl"
    p.write_text(PL)
    with pytest.raises(SyntaxError) as ei:
        _load_module(name, str(p))
    assert ei.value.lineno == 4                  # the line of the `/*`
    assert "unterminated block comment" in ei.value.msg
    assert "syntax_error(incomplete_reduction)" in ei.value.msg
    # The load is abandoned as a whole, as for any other syntax error:
    # _load_module leaves its module object registered, but with nothing
    # from the file in it -- not even foo/1, read before the comment. (The
    # exact class depends on what else defined an atom `foo` in the
    # process: PredicateNotFoundError alone, an existence_error
    # LogicException in the full suite; both subclass LogicException.)
    from clausal.logic.exceptions import LogicException
    mod = sys.modules[name]
    with pytest.raises(LogicException, match=r"foo"):
        list(solve(("foo", Var()), mod))


def test_translator_loader_refuses_the_file(tmp_path, monkeypatch):
    from clausal.import_hook import _load_module
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "translator")
    name = f"_unclosed_translator_{next(_N)}"
    p = tmp_path / f"{name}.pl"
    p.write_text(PL)
    with pytest.raises(TokenizeError) as ei:
        _load_module(name, str(p))
    assert "Unterminated block comment" in str(ei.value)
    assert ei.value.line == 4


def test_seam_source_is_not_affected(tmp_path, monkeypatch):
    # Seam files are Python syntax: `/*` there is not a comment opener.
    from clausal.import_hook import _load_module
    from clausal.logic.solve import _deref_walk, solve
    from clausal.logic.variables import Var
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    name = f"_unclosed_seam_{next(_N)}"
    p = tmp_path / f"{name}.seam"
    p.write_text("-private([red])\ncolour(red),\n# /* never closed\n")
    mod = _load_module(name, str(p))
    v = Var()
    assert [_deref_walk(v) for _ in solve(("colour", v), mod)] == ["red"]


# ── .pl source: block comments do NOT nest (ISO, Scryer) ─────────────────
#
# Both files from the Scryer measurement, 2026-09-30: N1 loads in Scryer
# (the `*/` closes the comment its `/*` opened; the inner `/*` is text) and
# N2 does not (` still */` is left over as code:
# syntax_error(incomplete_reduction)). Until then both .pl front ends read
# with nesting on and did the opposite: N1 refused, N2 loaded.

N1 = ":- module({name}, []).\n/* outer /* inner */\na(1).\ntest(t) :- a(1).\n"
N2 = ":- module({name}, []).\n/* outer /* inner */ still */\na(1).\ntest(t) :- a(1).\n"


@pytest.mark.parametrize("frontend", ["native", "translator"])
def test_pl_comment_closes_at_the_first_close(tmp_path, monkeypatch, frontend):
    from clausal.import_hook import _load_module
    from clausal.logic.solve import _deref_walk, solve
    from clausal.logic.variables import Var
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", frontend)
    name = f"nest_n1_{frontend}_{next(_N)}"
    p = tmp_path / f"{name}.pl"
    p.write_text(N1.format(name=name))
    mod = _load_module(name, str(p))
    v = Var()
    assert [_deref_walk(v) for _ in solve(("test", v), mod)] == ["t"]


@pytest.mark.parametrize("frontend", ["native", "translator"])
def test_pl_text_after_the_first_close_is_code(tmp_path, monkeypatch, frontend):
    from clausal.import_hook import _load_module
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", frontend)
    name = f"nest_n2_{frontend}_{next(_N)}"
    p = tmp_path / f"{name}.pl"
    p.write_text(N2.format(name=name))
    with pytest.raises(SyntaxError) as ei:
        _load_module(name, str(p))
    assert "*/" in str(ei.value)                 # the leftover ` still */`


def test_reader_default_still_nests():
    # The parameter stays: only the .pl loaders pass nested_comments=False.
    src = "/* outer /* inner */ still */\na(1).\n"
    assert [type(i) for i in read_module(src)] == [Clause]
    assert type(read_module(src, nested_comments=False)[0]) is SyntaxIssue


@pytest.mark.parametrize("text,loads", [(N1, True), (N2, False)])
def test_scryer_agrees(tmp_path, text, loads):
    import os
    from tests._oracles import SCRYER, run_scryer
    if not os.path.exists(SCRYER):
        pytest.skip("scryer binary not present")
    p = tmp_path / "nest.pl"
    p.write_text(text.format(name="nest"))
    out = run_scryer(str(p), ["nest:test(X)."], timeout=30)
    text_out = out.stdout + out.stderr
    assert ("X = t" in text_out) is loads, text_out
    assert ("syntax_error(incomplete_reduction)" in text_out) is (not loads)
