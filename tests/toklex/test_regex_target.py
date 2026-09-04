"""Regex rendering target: differential parity against the reference
table driver (which is itself parity-proven against the original
hand-written tokenizer), plus the chunk-boundary property."""

import glob
import random

import pytest

from clausal.tools.toklex import load_lexer
from clausal.tools.toklex.driver import EOF, NEED_MORE, IncrementalLexer
from clausal.tools.toklex.regex_target import RegexLexer

SCRYER_LIB = "/workspace/scryer-prolog/src/lib"


def _stream(lexer_cls, text, **kw):
    return [(t.kind, t.value, t.lexeme, t.start, t.end, t.glue)
            for t in lexer_cls(load_lexer(), **kw).run(text)]


SAMPLES = [
    "foo(X) :- bar(X, [1,2|T]), X =.. L, Y is 1.0e7 + 0'a. % done\n",
    "a. 1. 1.5. 'qu''ote'. \"str\\n\". /* c /* n */ c */ end.\n",
    "=.. = . .( 0x1F 0o17 0b101 1_000_000 X_1 _var !;,| {} [] ",
    "'\\x41\\' '\\q' 0''' 1.2e+ 1.2e-3 .\n",
    "'\\x41\\'. ",
    "1. ", "=.. = . ", "a.b ", "1e5. ", "0'''. ",
    # endgame-delegation shapes: unterminated / garbage / doubling tails
    "'abc", '"unterm', "\x01ab", "'ab''cc", "x. 'dangling",
    "0x_ ", "0'\\x ", "0'\\", "/* never closed",
    "",
]


class TestDifferentialVsTableDriver:
    @pytest.mark.parametrize("src", SAMPLES)
    def test_sample_streams_identical(self, src):
        assert _stream(RegexLexer, src) == _stream(IncrementalLexer, src)

    @pytest.mark.parametrize("src", SAMPLES[:6])
    def test_strict_iso_comments_flag(self, src):
        assert (_stream(RegexLexer, src, nested_comments=False)
                == _stream(IncrementalLexer, src, nested_comments=False))

    @pytest.mark.parametrize(
        "path",
        sorted(glob.glob(SCRYER_LIB + "/**/*.pl", recursive=True))
        or [pytest.param(None, marks=pytest.mark.skip(reason="scryer corpus absent"))])
    def test_corpus_streams_identical(self, path):
        src = open(path, encoding="utf-8").read()
        assert _stream(RegexLexer, src) == _stream(IncrementalLexer, src)


class TestClausalDialect:
    def test_dialect_streams_identical(self):
        lx = load_lexer("clausal")
        for src in ["-module(m, [f])\n-allow_singletons\n", "a. ", "f(a), g(b),\n"]:
            a = [(t.kind, t.value, t.lexeme, t.start, t.end, t.glue)
                 for t in IncrementalLexer(lx).run(src)]
            b = [(t.kind, t.value, t.lexeme, t.start, t.end, t.glue)
                 for t in RegexLexer(lx).run(src)]
            assert a == b, src


class TestIncremental:
    def test_holds_extensible_match_at_boundary(self):
        lx = RegexLexer(load_lexer())
        lx.feed("X =")
        assert lx.next_token().kind == "variable"
        assert lx.next_token() is NEED_MORE  # '=' could still become '=..'
        lx.feed(".. Y")
        assert lx.next_token().value == "=.."

    def test_chunk_boundary_insensitivity(self):
        rng = random.Random(20260904)
        for text in SAMPLES:
            want = _stream(RegexLexer, text)
            for _ in range(60):
                k = rng.randrange(0, min(6, len(text))) if text else 0
                cuts = sorted(rng.sample(range(1, len(text)), k)) if text else []
                lx = RegexLexer(load_lexer())
                out = []
                pieces = [text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])]
                for piece in pieces:
                    lx.feed(piece)
                    while (t := lx.next_token()) is not NEED_MORE:
                        if t is EOF:
                            break
                        out.append((t.kind, t.value, t.lexeme, t.start, t.end, t.glue))
                lx.close()
                while (t := lx.next_token()) is not EOF:
                    assert t is not NEED_MORE
                    out.append((t.kind, t.value, t.lexeme, t.start, t.end, t.glue))
                assert out == want, (text, cuts)


class TestShimIntegration:
    def test_public_tokenize_uses_regex_target(self):
        # the shim's chars-mode batch path should ride the fast target;
        # this pins the wiring (behavior is covered by the parity suites)
        import clausal.tools.prolog_tokenizer as pt
        toks = pt.tokenize("foo(X) :- 'b ar', 1.5e2. ")
        assert toks[5].quoted is True and toks[-1].type == pt.TokenType.END
