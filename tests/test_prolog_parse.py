"""Tests for Phase 3.1 (tokenizer) and Phase 3.2 (Pratt parser)."""

from __future__ import annotations

import pytest

from clausal.tools.prolog_tokenizer import Token, TokenType, tokenize, TokenizeError
from clausal.tools.prolog_parser import parse, parse_term, ParseError, PrologParser
from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PQuery, PModule,
)
from clausal.tools.prolog_operators import OperatorTable


# ═══════════════════════════════════════════════════════════════════════
# Tokenizer tests
# ═══════════════════════════════════════════════════════════════════════


class TestTokenizeAtoms:
    def test_word_atom(self):
        # nv
        toks = tokenize("foo")
        assert toks[0] == Token(TokenType.ATOM, "foo", 1, 1)

    def test_quoted_atom(self):
        # nv
        toks = tokenize("'hello world'")
        # A11-F035: quoted atoms carry quoted=True.
        assert toks[0] == Token(TokenType.ATOM, "hello world", 1, 1, quoted=True)

    def test_quoted_atom_doubled_quote(self):
        # nv
        toks = tokenize("'it''s'")
        assert toks[0].value == "it's"

    def test_graphic_atom(self):
        # nv
        toks = tokenize("=..")
        assert toks[0] == Token(TokenType.ATOM, "=..", 1, 1)

    def test_graphic_op(self):
        # nv
        toks = tokenize("\\+")
        assert toks[0] == Token(TokenType.ATOM, "\\+", 1, 1)

    def test_semicolon(self):
        # nv
        toks = tokenize(";")
        assert toks[0] == Token(TokenType.ATOM, ";", 1, 1)

    def test_cut(self):
        # nv
        toks = tokenize("!")
        assert toks[0] == Token(TokenType.ATOM, "!", 1, 1)

    def test_arrow(self):
        # nv
        toks = tokenize(":-")
        assert toks[0] == Token(TokenType.ATOM, ":-", 1, 1)

    def test_dcg_arrow(self):
        # nv
        toks = tokenize("-->")
        assert toks[0] == Token(TokenType.ATOM, "-->", 1, 1)


class TestTokenizeVariables:
    def test_uppercase(self):
        # nv
        toks = tokenize("X")
        assert toks[0] == Token(TokenType.VAR, "X", 1, 1)

    def test_longer_var(self):
        # nv
        toks = tokenize("Head")
        assert toks[0] == Token(TokenType.VAR, "Head", 1, 1)

    def test_anonymous(self):
        # nv
        toks = tokenize("_")
        assert toks[0] == Token(TokenType.VAR, "_", 1, 1)

    def test_named_underscore(self):
        # nv
        toks = tokenize("_Ignored")
        assert toks[0] == Token(TokenType.VAR, "_Ignored", 1, 1)


class TestTokenizeNumbers:
    def test_integer(self):
        # nv
        toks = tokenize("42")
        assert toks[0] == Token(TokenType.INTEGER, 42, 1, 1)

    def test_float(self):
        # nv
        toks = tokenize("3.14")
        assert toks[0] == Token(TokenType.FLOAT, 3.14, 1, 1)

    def test_float_exponent(self):
        # nv
        toks = tokenize("1.0e-5")
        assert toks[0].type == TokenType.FLOAT
        assert abs(toks[0].value - 1.0e-5) < 1e-15

    def test_hex(self):
        # nv
        toks = tokenize("0x1F")
        assert toks[0] == Token(TokenType.INTEGER, 31, 1, 1)

    def test_binary(self):
        # nv
        toks = tokenize("0b1010")
        assert toks[0] == Token(TokenType.INTEGER, 10, 1, 1)

    def test_octal(self):
        # nv
        toks = tokenize("0o77")
        assert toks[0] == Token(TokenType.INTEGER, 63, 1, 1)

    def test_char_code(self):
        # nv
        toks = tokenize("0'a")
        assert toks[0] == Token(TokenType.INTEGER, 97, 1, 1)

    def test_char_code_space(self):
        # nv
        toks = tokenize("0' ")
        assert toks[0] == Token(TokenType.INTEGER, 32, 1, 1)


class TestTokenizeStrings:
    def test_simple(self):
        # nv
        toks = tokenize('"hello"')
        assert toks[0] == Token(TokenType.STRING, "hello", 1, 1)

    def test_escape(self):
        # nv
        toks = tokenize(r'"line\n"')
        assert toks[0].value == "line\n"

    def test_doubled_quote(self):
        # nv
        toks = tokenize('"say ""hi"""')
        assert toks[0].value == 'say "hi"'


class TestTokenizeStructural:
    def test_parens(self):
        # nv
        toks = tokenize("(X)")
        types = [t.type for t in toks[:-1]]
        assert types == [TokenType.LPAREN, TokenType.VAR, TokenType.RPAREN]

    def test_brackets(self):
        # nv
        toks = tokenize("[a, b]")
        types = [t.type for t in toks[:-1]]
        assert types == [
            TokenType.LBRACKET, TokenType.ATOM, TokenType.COMMA,
            TokenType.ATOM, TokenType.RBRACKET,
        ]

    def test_curly(self):
        # nv
        toks = tokenize("{X}")
        types = [t.type for t in toks[:-1]]
        assert types == [TokenType.LCURLY, TokenType.VAR, TokenType.RCURLY]

    def test_bar(self):
        # nv
        toks = tokenize("[H|T]")
        types = [t.type for t in toks[:-1]]
        assert types == [
            TokenType.LBRACKET, TokenType.VAR, TokenType.BAR,
            TokenType.VAR, TokenType.RBRACKET,
        ]


class TestTokenizeDot:
    def test_clause_terminator(self):
        # nv
        toks = tokenize("foo.")
        assert toks[-2] == Token(TokenType.DOT, ".", 1, 4)

    def test_dot_eof(self):
        # nv
        toks = tokenize("a.")
        types = [t.type for t in toks]
        assert types == [TokenType.ATOM, TokenType.DOT, TokenType.END]

    def test_dot_whitespace(self):
        # nv
        toks = tokenize("a. b.")
        types = [t.type for t in toks]
        assert types == [TokenType.ATOM, TokenType.DOT, TokenType.ATOM, TokenType.DOT, TokenType.END]

    def test_dot_in_float_not_terminator(self):
        # nv
        toks = tokenize("3.14")
        assert toks[0].type == TokenType.FLOAT


class TestTokenizeComments:
    def test_line_comment(self):
        # nv
        toks = tokenize("foo. % comment\nbar.")
        atoms = [t.value for t in toks if t.type == TokenType.ATOM]
        assert atoms == ["foo", "bar"]

    def test_block_comment(self):
        # nv
        toks = tokenize("foo. /* block */ bar.")
        atoms = [t.value for t in toks if t.type == TokenType.ATOM]
        assert atoms == ["foo", "bar"]

    def test_nested_block_comment(self):
        # nv
        toks = tokenize("foo. /* outer /* inner */ still comment */ bar.")
        atoms = [t.value for t in toks if t.type == TokenType.ATOM]
        assert atoms == ["foo", "bar"]


class TestTokenizeErrors:
    def test_unterminated_quoted_atom(self):
        # nv
        with pytest.raises(TokenizeError, match="Unterminated quoted atom"):
            tokenize("'hello")

    def test_unterminated_string(self):
        # nv
        with pytest.raises(TokenizeError, match="Unterminated string"):
            tokenize('"hello')


class TestTokenizeMultiple:
    def test_fact(self):
        # nv
        toks = tokenize("edge(1, 2).")
        types = [t.type for t in toks]
        assert types == [
            TokenType.ATOM, TokenType.LPAREN, TokenType.INTEGER,
            TokenType.COMMA, TokenType.INTEGER, TokenType.RPAREN,
            TokenType.DOT, TokenType.END,
        ]

    def test_rule(self):
        # nv
        toks = tokenize("reach(X, Y) :- edge(X, Y).")
        types = [t.type for t in toks]
        assert TokenType.ATOM in types
        assert TokenType.VAR in types
        assert types[-1] == TokenType.END

    def test_negative_number_in_expr(self):
        # nv
        toks = tokenize("-3")
        # - is a graphic atom, 3 is integer
        assert toks[0].type == TokenType.ATOM
        assert toks[0].value == "-"
        assert toks[1].type == TokenType.INTEGER


# ═══════════════════════════════════════════════════════════════════════
# Parser tests
# ═══════════════════════════════════════════════════════════════════════


class TestParseTerm:
    def test_atom(self):
        # nv
        t = parse_term("foo")
        assert t == PAtom("foo")

    def test_variable(self):
        # nv
        t = parse_term("X")
        assert t == PVar("X")

    def test_integer(self):
        # nv
        t = parse_term("42")
        assert t == PNumber(42)

    def test_float(self):
        # nv
        t = parse_term("3.14")
        assert t == PNumber(3.14)

    def test_string(self):
        # nv
        t = parse_term('"hello"')
        assert t == PString("hello")

    def test_compound(self):
        # nv
        t = parse_term("foo(bar, baz)")
        assert isinstance(t, PCompound)
        assert t.functor == "foo"
        assert t.args == (PAtom("bar"), PAtom("baz"))

    def test_nested_compound(self):
        # nv
        t = parse_term("f(g(X), h(Y))")
        assert isinstance(t, PCompound)
        assert t.functor == "f"
        assert isinstance(t.args[0], PCompound) and t.args[0].functor == "g"
        assert isinstance(t.args[1], PCompound) and t.args[1].functor == "h"

    def test_empty_list(self):
        # nv
        t = parse_term("[]")
        assert t == PList((), None)

    def test_proper_list(self):
        # nv
        t = parse_term("[1, 2, 3]")
        assert isinstance(t, PList)
        assert t.elements == (PNumber(1), PNumber(2), PNumber(3))
        assert t.tail is None

    def test_partial_list(self):
        # nv
        t = parse_term("[H|T]")
        assert isinstance(t, PList)
        assert t.elements == (PVar("H"),)
        assert t.tail == PVar("T")

    def test_multi_head_list(self):
        # nv
        t = parse_term("[A, B|Rest]")
        assert isinstance(t, PList)
        assert t.elements == (PVar("A"), PVar("B"))
        assert t.tail == PVar("Rest")

    def test_curly(self):
        # nv
        t = parse_term("{foo}")
        assert isinstance(t, PCurly)
        assert t.body == PAtom("foo")

    def test_empty_curly(self):
        # nv
        t = parse_term("{}")
        assert t == PAtom("{}")

    def test_parenthesized(self):
        # nv
        t = parse_term("(foo)")
        assert t == PAtom("foo")

    def test_negative_number(self):
        # nv
        t = parse_term("-3")
        assert t == PNumber(-3)

    def test_quoted_atom(self):
        # nv
        t = parse_term("'hello world'")
        # A11-F035: parser sets quoted=True on quoted atoms.
        assert t == PAtom("hello world", quoted=True)


class TestParseOperators:
    def test_infix_plus(self):
        # nv
        t = parse_term("1 + 2")
        assert isinstance(t, PCompound)
        assert t.functor == "+"
        assert t.args == (PNumber(1), PNumber(2))

    def test_precedence(self):
        # nv
        t = parse_term("1 + 2 * 3")
        # * binds tighter than +
        assert isinstance(t, PCompound) and t.functor == "+"
        assert isinstance(t.args[1], PCompound) and t.args[1].functor == "*"

    def test_left_assoc(self):
        # nv
        t = parse_term("1 - 2 - 3")
        # - is yfx (left-associative)
        assert isinstance(t, PCompound) and t.functor == "-"
        assert isinstance(t.args[0], PCompound) and t.args[0].functor == "-"

    def test_right_assoc(self):
        # nv
        t = parse_term("1 ; 2 ; 3")
        # ; is xfy (right-associative)
        assert isinstance(t, PCompound) and t.functor == ";"
        assert isinstance(t.args[1], PCompound) and t.args[1].functor == ";"

    def test_negation_prefix(self):
        # nv
        t = parse_term("\\+ foo")
        assert isinstance(t, PCompound)
        assert t.functor == "\\+"
        assert t.args == (PAtom("foo"),)

    def test_unification(self):
        # nv
        t = parse_term("X = foo")
        assert isinstance(t, PCompound)
        assert t.functor == "="
        assert t.args == (PVar("X"), PAtom("foo"))

    def test_is_expr(self):
        # nv
        t = parse_term("Y is X + 1")
        assert isinstance(t, PCompound) and t.functor == "is"
        assert isinstance(t.args[1], PCompound) and t.args[1].functor == "+"

    def test_conjunction(self):
        # nv
        t = parse_term("a, b, c")
        # , is xfy (right-assoc)
        assert isinstance(t, PCompound) and t.functor == ","
        assert t.args[0] == PAtom("a")
        # Right side is (b, c)
        rhs = t.args[1]
        assert isinstance(rhs, PCompound) and rhs.functor == ","

    def test_clause_arrow(self):
        # nv
        t = parse_term("head :- body")
        assert isinstance(t, PCompound) and t.functor == ":-"
        assert t.args == (PAtom("head"), PAtom("body"))

    def test_comparison(self):
        # nv
        t = parse_term("X > 0")
        assert isinstance(t, PCompound) and t.functor == ">"

    def test_mod_operator(self):
        # nv
        t = parse_term("7 mod 2")
        assert isinstance(t, PCompound) and t.functor == "mod"

    def test_power(self):
        # nv
        t = parse_term("2 ** 3")
        assert isinstance(t, PCompound) and t.functor == "**"


class TestParseProgram:
    def test_simple_fact(self):
        # nv
        m = parse("edge(1, 2).")
        assert len(m.items) == 1
        item = m.items[0]
        assert isinstance(item, PClause)
        assert item.body is None
        assert isinstance(item.head, PCompound)
        assert item.head.functor == "edge"

    def test_simple_rule(self):
        # nv
        m = parse("reach(X, Y) :- edge(X, Y).")
        assert len(m.items) == 1
        item = m.items[0]
        assert isinstance(item, PClause)
        assert item.body is not None

    def test_multiple_clauses(self):
        # nv
        m = parse("edge(1, 2).\nedge(2, 3).")
        assert len(m.items) == 2

    def test_directive(self):
        # nv
        m = parse(":- module(test, []).")
        assert len(m.items) == 1
        assert isinstance(m.items[0], PDirective)

    def test_dcg_rule(self):
        # nv
        m = parse("greeting --> [hello, world].")
        assert len(m.items) == 1
        assert isinstance(m.items[0], PDCGRule)

    def test_atom_fact(self):
        # nv
        m = parse("halt.")
        assert len(m.items) == 1
        assert isinstance(m.items[0], PClause)
        assert isinstance(m.items[0].head, PAtom)

    def test_multiline_rule(self):
        # nv
        src = """\
reach(X, Y) :-
    edge(X, Z),
    reach(Z, Y).
"""
        m = parse(src)
        assert len(m.items) == 1
        clause = m.items[0]
        assert isinstance(clause, PClause)
        assert clause.body is not None

    def test_list_head(self):
        # nv
        m = parse("check_diagonals([]).")
        assert len(m.items) == 1

    def test_list_pattern(self):
        # nv
        m = parse("check_diagonals([Q|Rest]) :- safe_from(Q, Rest, 1).")
        assert len(m.items) == 1
        clause = m.items[0]
        assert isinstance(clause.head, PCompound)

    def test_query(self):
        # nv
        m = parse("?- foo(X).")
        assert len(m.items) == 1
        assert isinstance(m.items[0], PQuery)

    def test_cut_in_body(self):
        # nv
        m = parse("foo(X) :- bar(X), !.")
        clause = m.items[0]
        assert isinstance(clause, PClause)


class TestParseOpDirective:
    def test_op_directive_affects_parsing(self):
        # nv
        src = """:- op(700, xfx, <>).
foo <> bar.
"""
        m = parse(src)
        assert len(m.items) == 2
        assert isinstance(m.items[0], PDirective)
        clause = m.items[1]
        assert isinstance(clause, PClause)
        # The head should be <>(foo, bar)
        head = clause.head
        assert isinstance(head, PCompound)
        assert head.functor == "<>"


class TestParseComplexPrograms:
    def test_edge_graph(self):
        # nv
        src = """\
edge(1, 2).
edge(2, 3).
edge(1, 3).

reach(X, Y) :-
    edge(X, Y).

reach(X, Y) :-
    edge(X, Z),
    reach(Z, Y).
"""
        m = parse(src)
        assert len(m.items) == 5

    def test_fibonacci(self):
        # nv
        src = """\
fib(0, 0).
fib(1, 1).
fib(N, Result) :-
    N > 1,
    N1 is N - 1,
    N2 is N - 2,
    fib(N1, A),
    fib(N2, B),
    Result is A + B.
"""
        m = parse(src)
        assert len(m.items) == 3
        rule = m.items[2]
        assert isinstance(rule, PClause) and rule.body is not None

    def test_dcg_grammar(self):
        # nv
        src = """\
:- module(dcg_grammar, [greeting/2, digit/3]).

greeting -->
    ["hello", "world"].

digit(D) -->
    [D], {D >= 0}, {D =< 9}.
"""
        m = parse(src)
        assert len(m.items) == 3
        assert isinstance(m.items[0], PDirective)
        assert isinstance(m.items[1], PDCGRule)
        assert isinstance(m.items[2], PDCGRule)

    def test_if_then_else(self):
        # nv
        src = "max(X, Y, Z) :- (X >= Y -> Z = X ; Z = Y)."
        m = parse(src)
        assert len(m.items) == 1

    def test_nested_negation(self):
        # nv
        src = "test :- \\+ \\+ 1 = 1."
        m = parse(src)
        clause = m.items[0]
        assert isinstance(clause, PClause)


class TestParseEdgeCases:
    def test_zero_arity_compound(self):
        # nv
        t = parse_term("foo()")
        assert isinstance(t, PCompound)
        assert t.functor == "foo"
        assert t.args == ()

    def test_operator_as_atom_in_compound(self):
        # nv
        t = parse_term("op(700, xfx, <>)")
        assert isinstance(t, PCompound)
        assert t.functor == "op"

    def test_nested_list(self):
        # nv
        t = parse_term("[[1, 2], [3, 4]]")
        assert isinstance(t, PList)
        assert len(t.elements) == 2

    def test_string_in_compound(self):
        # nv
        t = parse_term('test("hello")')
        assert isinstance(t, PCompound)
        assert isinstance(t.args[0], PString)

    def test_predicate_indicator(self):
        # nv
        t = parse_term("foo/2")
        assert isinstance(t, PCompound) and t.functor == "/"
        assert t.args == (PAtom("foo"), PNumber(2))


class TestSpans:
    def _term(self, src):
        from clausal.tools.prolog_parser import parse_term
        return parse_term(src)

    def test_atom_number_var_spans(self):
        t = self._term("foo")
        assert t.span == (0, 3)
        assert self._term("42").span == (0, 2)
        assert self._term("Xyz").span == (0, 3)

    def test_compound_and_arg_spans(self):
        t = self._term("foo(bar, 12)")
        assert t.span == (0, 12)
        assert t.args[0].span == (4, 7)
        assert t.args[1].span == (9, 11)

    def test_operator_compound_spans(self):
        t = self._term("a + b * c")
        assert t.span == (0, 9)          # the whole +
        assert t.args[0].span == (0, 1)  # a
        assert t.args[1].span == (4, 9)  # b * c

    def test_list_and_curly_spans(self):
        t = self._term("[a, b | T]")
        assert t.span == (0, 10)
        assert t.elements[1].span == (4, 5)
        assert t.tail.span == (8, 9)
        assert self._term("{x}").span == (0, 3)

    def test_parenthesized_span_covers_parens(self):
        t = self._term("( a )")
        assert t.span == (0, 5)

    def test_quoted_atom_span(self):
        t = self._term("'a b'")
        assert t.span == (0, 5)

    def test_equality_unaffected(self):
        from clausal.tools.prolog_ast import PAtom
        assert self._term("foo") == PAtom("foo")
