import random
from clausal.tools.toklex import load_lexer
from clausal.tools.toklex.driver import IncrementalLexer, NEED_MORE, EOF
from clausal.tools.toklex.decode import Utf8Feeder

CORPUS = [
    "foo(X) :- bar(X, [1,2|T]), X =.. L, Y is 1.0e7 + 0'a. % done\n",
    "a. 1. 1.5. 'qu''ote'. \"str\\n\". /* c /* n */ c */ end.\n",
    "=.. = . .( 0x1F 0o17 0b101 1_000_000 X_1 _var !;,| {} [] ",
    "'\\x41\\' '\\q' 0''' 1.2e+ 1.2e-3 .\n",
]


def tokens_batch(text):
    return [(t.kind, t.value, t.lexeme) for t in IncrementalLexer(load_lexer()).run(text)]


def tokens_chunked(text, cuts):
    lx = IncrementalLexer(load_lexer())
    out, pieces = [], [text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])]
    for piece in pieces:
        lx.feed(piece)
        while (t := lx.next_token()) is not NEED_MORE:
            if t is EOF:
                break
            out.append((t.kind, t.value, t.lexeme))
    lx.close()
    while (t := lx.next_token()) is not EOF:
        assert t is not NEED_MORE
        out.append((t.kind, t.value, t.lexeme))
    return out


def test_chunk_insensitivity_chars():
    rng = random.Random(20260904)
    for text in CORPUS:
        want = tokens_batch(text)
        for trial in range(200):
            k = rng.randrange(0, min(8, len(text)))
            cuts = sorted(rng.sample(range(1, len(text)), k))
            got = tokens_chunked(text, cuts)
            assert got == want, (text, cuts)


def test_chunk_insensitivity_bytes_with_multibyte_splits():
    rng = random.Random(42)
    text = "père(luc). 'é' = X. % café\n".encode("utf-8") + b"a \xff b.\n"
    def run(cuts):
        f = Utf8Feeder(IncrementalLexer(load_lexer()))
        pieces = [text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])]
        out = []
        for p in pieces:
            f.feed(p)
            while (t := f.next_token()) is not NEED_MORE:
                if t is EOF:
                    break
                out.append((t.kind, t.lexeme))
        f.close()
        while (t := f.next_token()) is not EOF:
            out.append((t.kind, t.lexeme))
        return out
    want = run([])
    for trial in range(200):
        k = rng.randrange(0, 8)
        cuts = sorted(rng.sample(range(1, len(text)), k))
        assert run(cuts) == want, cuts
