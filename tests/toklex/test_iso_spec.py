from clausal.tools.toklex import load_lexer
from clausal.tools.toklex.driver import IncrementalLexer, NEED_MORE, EOF


def lex(text, **kw):
    return IncrementalLexer(load_lexer(), **kw).run(text)


def kv(text):
    return [(t.kind, t.value) for t in lex(text)]


class TestWorkedExamples:
    def test_univ_vs_eq(self):
        assert kv("=..")[0] == ("graphic_tok", "=..")
        assert kv("=, ")[0] == ("graphic_tok", "=")

    def test_number_family(self):
        assert kv("1 ")[0] == ("integer", 1)
        assert kv("1.5 ")[0] == ("float_num", 1.5)
        assert kv("1.0e7 ")[0] == ("float_num", 1.0e7)
        assert [k for k, _ in kv("1. ")] == ["integer", "end"]
        got = kv("1.0e+x ")
        assert got[0] == ("float_num", 1.0)
        assert [k for k, _ in got] == ["float_num", "name_atom", "graphic_tok", "name_atom"]

    def test_digit_group_separator_sits_between_digits(self):
        # One `_` between two digits, as Scryer and Python
        # (todo/done/reader-digit-group-trailing-underscore-2026-10-24.md):
        # a trailing or doubled `_` ends the integer, and the rest lexes as
        # a variable, which the parser refuses as cannot_parse_big_int.
        assert kv("1_000 ")[0] == ("integer", 1000)
        assert kv("1_0.5 ")[0] == ("float_num", 10.5)
        assert kv("1_000_ ")[:2] == [("integer", 1000), ("variable", "_")]
        assert kv("1__000 ")[:2] == [("integer", 1), ("variable", "__000")]
        assert kv("1_.5 ")[:2] == [("integer", 1), ("variable", "_")]
        assert kv("1.0_ ")[:2] == [("float_num", 1.0), ("variable", "_")]

    def test_fraction_and_radix_take_no_digit_group(self):
        # Scryer, operator ruling 2026-11-03: digit groups are for the
        # decimal integer part only.
        assert kv("1.0_0 ")[:2] == [("float_num", 1.0), ("variable", "_0")]
        assert kv("0x1_2 ")[:2] == [("hex_int", 1), ("variable", "_2")]
        assert kv("0x1_ ")[:2] == [("hex_int", 1), ("variable", "_")]
        assert kv("0x_1 ")[:2] == [("integer", 0), ("name_atom", "x_1")]
        assert kv("0o7_7 ")[:2] == [("oct_int", 7), ("variable", "_7")]
        assert kv("0b1_0 ")[:2] == [("bin_int", 1), ("variable", "_0")]
        # the joining of `1_ 000` happens after lexing, so the lexer itself
        # still ends the integer at the `_`
        assert kv("1_ 000 ")[:3] == [("integer", 1), ("variable", "_"),
                                     ("integer", 0)]

    def test_char_codes(self):
        assert kv("0'a ")[0] == ("char_code", 97)
        assert kv("0''' ")[0] == ("char_code", 39)
        assert kv("0'\\n ")[0] == ("char_code", 10)

    def test_quoted_atom_continuation_and_doubling(self):
        assert kv("'ab\\\ncd' ")[0] == ("quoted_atom", "abcd")
        assert kv("'a''b' ")[0] == ("quoted_atom", "a'b")

    def test_unterminated_quote_at_eof_is_error(self):
        toks = lex("'abc")
        assert toks[-1].kind == "error"

    def test_nested_comment(self):
        assert [k for k, _ in kv("/* a /* b */ c */ x ")] == ["name_atom"]

    def test_dot_completely(self):
        assert [k for k, _ in kv("a. ")] == ["name_atom", "end"]
        assert kv(".( ")[0] == ("graphic_tok", ".")
        assert kv("a.b ")[:3] == [("name_atom", "a"), ("graphic_tok", "."), ("name_atom", "b")]


class TestSuspension:
    def test_terminal_reader_waits_on_eq(self):
        lx = IncrementalLexer(load_lexer())
        lx.feed("X =")
        assert lx.next_token().kind == "variable"
        assert lx.next_token() is NEED_MORE
        lx.feed(".. Y")
        assert lx.next_token().value == "=.."

    def test_zero_quote_waits(self):
        lx = IncrementalLexer(load_lexer())
        lx.feed("0'")
        assert lx.next_token() is NEED_MORE


class TestCompilerClaims:
    def test_backup_bound_is_exactly_four(self):
        # The worst case is `0` + `'\xa`: a 0' hex escape needs its closing
        # backslash (ISO 6.4.2.1), so after `0'\x` and a hex digit the
        # scanner may be 4 characters past its last accept (`0`) before it
        # is stuck. (The digit loop itself is a commit region.) It was 2
        # while the 0' escape's closing backslash was optional.
        assert load_lexer().max_backup == 4

    def test_strict_iso_comments_flag(self):
        strict = IncrementalLexer(load_lexer(), nested_comments=False)
        toks = strict.run("/* a /* b */ c */ x ")
        # non-nesting: comment closes at first */, then 'c', then '*/' etc.
        assert toks[0].kind == "name_atom" and toks[0].lexeme == "c"
