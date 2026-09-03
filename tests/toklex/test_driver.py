from clausal.tools.toklex.spec import parse_spec_text
from clausal.tools.toklex.annotate import annotate
from clausal.tools.toklex.driver import IncrementalLexer, NEED_MORE, EOF

SPEC = parse_spec_text("""
encoding(chars).
class(digit, range('0','9')).
class(small, range(a, z)).
class(layout, [' ', '\\n']).
class(graphic, ['=','.','/','*','+']).
def(exp, 'e' then ('+' | '-')? then digit then digit*).
token(integer, digit then (digit | '_')*).
token(float_num, digit then digit* then '.' then digit then digit* then exp?).
token(name, small then (small | digit)*).
token(end, '.' followed_by (layout | '%' | eof)).
token(graphic_tok, graphic+ but_not ('/' then '*' then any*)).
token(lparen, '(').
trivia(ws, layout then layout*).
trivia(block, '/' then '*' then body('*' then '/')) nest self.
""")


def lex(text):
    return IncrementalLexer(annotate(SPEC)).run(text)


def kinds(text):
    return [(t.kind, t.lexeme) for t in lex(text)]


class TestMaximalMunch:
    def test_graphic_extension(self):
        assert kinds("=.. ") == [("graphic_tok", "=..")]
        assert kinds("= x") == [("graphic_tok", "="), ("name", "x")]

    def test_numbers_and_backup(self):
        assert kinds("1.5 ") == [("float_num", "1.5")]
        assert kinds("1. ") == [("integer", "1"), ("end", ".")]
        assert kinds("1.2e7 ") == [("float_num", "1.2e7")]
        # the B=2 witness: emit 1.2, push back 'e+', relex as name then graphic
        assert kinds("1.2e+ ")[0] == ("float_num", "1.2")
        assert [k for k, _ in kinds("1.2e+ ")] == ["float_num", "name", "graphic_tok"]

    def test_dot_cases(self):
        assert kinds(".( ") == [("graphic_tok", "."), ("lparen", "(")]
        assert kinds(". ") == [("end", ".")]


class TestIncrementality:
    def test_need_more_mid_token(self):
        lx = IncrementalLexer(annotate(SPEC))
        lx.feed("=")
        assert lx.next_token() is NEED_MORE       # '=' could become '=..'
        lx.feed(". x")
        toks = []
        while (t := lx.next_token()) is not NEED_MORE and t is not EOF:
            toks.append(t)
        lx.close()
        while (t := lx.next_token()) is not EOF:
            toks.append(t)
        assert [t.lexeme for t in toks] == ["=.", "x"]

    def test_eof_resolves_extension(self):
        lx = IncrementalLexer(annotate(SPEC))
        lx.feed("=")
        lx.close()
        assert lx.next_token().lexeme == "="
        assert lx.next_token() is EOF

    def test_end_at_eof(self):
        assert kinds("ab.") == [("name", "ab"), ("end", ".")]


class TestTriviaGlueNest:
    def test_glue(self):
        a, b, c = lex("f( (")
        assert (a.glue, b.glue, c.glue) == ("spaced", "glued", "spaced")

    def test_nested_comment_is_skipped_and_spaces(self):
        toks = lex("f/* x /* y */ z */(")
        assert [(t.kind, t.glue) for t in toks] == [("name", "spaced"), ("lparen", "spaced")]

    def test_slash_before_comment_not_emitted_early(self):
        # '/' must NOT be emitted when '/*' opens a comment (combined-DFA extend)
        assert kinds("/* c */ x") == [("name", "x")]
        assert kinds("/ x") == [("graphic_tok", "/"), ("name", "x")]


class TestErrors:
    def test_unknown_char(self):
        toks = lex("\x01ab")
        assert toks[0].kind == "error"
        assert toks[1].kind == "name"

    def test_positions(self):
        a, b = lex("ab\ncd")
        assert a.start == (0, 1, 1) and a.end == (2, 1, 3)
        assert b.start == (3, 2, 1)


from clausal.tools.toklex.builders import ISO_BUILDERS


class TestBuilders:
    def test_quoted_atom_escapes(self):
        f = ISO_BUILDERS["quoted_atom_val"]
        assert f("'ab'") == "ab"
        assert f("'a''b'") == "a'b"
        assert f("'a\\nb'") == "a\nb"
        assert f("'a\\\nb'") == "ab"          # line continuation
        assert f("'\\x41\\b'") == "Ab"
        assert f("'\\q'") == "\\q"             # lenient unknown escape

    def test_numbers(self):
        assert ISO_BUILDERS["int_10"]("1_000") == 1000
        assert ISO_BUILDERS["int_16"]("0x1F_f") == 0x1FF
        assert ISO_BUILDERS["float_of"]("1.5e3") == 1500.0
        assert ISO_BUILDERS["char_code"]("0'a") == 97
        assert ISO_BUILDERS["char_code"]("0'''") == 39
        assert ISO_BUILDERS["char_code"]("0'\\n") == 10
