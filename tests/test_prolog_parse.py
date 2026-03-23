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
        toks = tokenize("foo")
        assert toks[0] == Token(TokenType.ATOM, "foo", 1, 1)

    def test_quoted_atom(self):
        toks = tokenize("'hello world'")
        assert toks[0] == Token(TokenType.ATOM, "hello world", 1, 1)

    def test_quoted_atom_doubled_quote(self):
        toks = tokenize("'it''s'")
        assert toks[0].value == "it's"

    def test_graphic_atom(self):
        toks = tokenize("=..")
        assert toks[0] == Token(TokenType.ATOM, "=..", 1, 1)

    def test_graphic_op(self):
        toks = tokenize("\\+")
        assert toks[0] == Token(TokenType.ATOM, "\\+", 1, 1)

    def test_semicolon(self):
        toks = tokenize(";")
        assert toks[0] == Token(TokenType.ATOM, ";", 1, 1)

    def test_cut(self):
        toks = tokenize("!")
        assert toks[0] == Token(TokenType.ATOM, "!", 1, 1)

    def test_arrow(self):
        toks = tokenize(":-")
        assert toks[0] == Token(TokenType.ATOM, ":-", 1, 1)

    def test_dcg_arrow(self):
        toks = tokenize("-->")
        assert toks[0] == Token(TokenType.ATOM, "-->", 1, 1)


class TestTokenizeVariables:
    def test_uppercase(self):
        toks = tokenize("X")
        assert toks[0] == Token(TokenType.VAR, "X", 1, 1)

    def test_longer_var(self):
        toks = tokenize("Head")
        assert toks[0] == Token(TokenType.VAR, "Head", 1, 1)

    def test_anonymous(self):
        toks = tokenize("_")
        assert toks[0] == Token(TokenType.VAR, "_", 1, 1)

    def test_named_underscore(self):
        toks = tokenize("_Ignored")
        assert toks[0] == Token(TokenType.VAR, "_Ignored", 1, 1)


class TestTokenizeNumbers:
    def test_integer(self):
        toks = tokenize("42")
        assert toks[0] == Token(TokenType.INTEGER, 42, 1, 1)

    def test_float(self):
        toks = tokenize("3.14")
        assert toks[0] == Token(TokenType.FLOAT, 3.14, 1, 1)

    def test_float_exponent(self):
        toks = tokenize("1.0e-5")
        assert toks[0].type == TokenType.FLOAT
        assert abs(toks[0].value - 1.0e-5) < 1e-15

    def test_hex(self):
        toks = tokenize("0x1F")
        assert toks[0] == Token(TokenType.INTEGER, 31, 1, 1)

    def test_binary(self):
        toks = tokenize("0b1010")
        assert toks[0] == Token(TokenType.INTEGER, 10, 1, 1)

    def test_octal(self):
        toks = tokenize("0o77")
        assert toks[0] == Token(TokenType.INTEGER, 63, 1, 1)

    def test_char_code(self):
        toks = tokenize("0'a")
        assert toks[0] == Token(TokenType.INTEGER, 97, 1, 1)

    def test_char_code_space(self):
        toks = tokenize("0' ")
        assert toks[0] == Token(TokenType.INTEGER, 32, 1, 1)


class TestTokenizeStrings:
    def test_simple(self):
        toks = tokenize('"hello"')
        assert toks[0] == Token(TokenType.STRING, "hello", 1, 1)

    def test_escape(self):
        toks = tokenize(r'"line\n"')
        assert toks[0].value == "line\n"

    def test_doubled_quote(self):
        toks = tokenize('"say ""hi"""')
        assert toks[0].value == 'say "hi"'


class TestTokenizeStructural:
    def test_parens(self):
        toks = tokenize("(X)")
        types = [t.type for t in toks[:-1]]
        assert types == [TokenType.LPAREN, TokenType.VAR, TokenType.RPAREN]

    def test_brackets(self):
        toks = tokenize("[a, b]")
        types = [t.type for t in toks[:-1]]
        assert types == [
            TokenType.LBRACKET, TokenType.ATOM, TokenType.COMMA,
            TokenType.ATOM, TokenType.RBRACKET,
        ]

    def test_curly(self):
        toks = tokenize("{X}")
        types = [t.type for t in toks[:-1]]
        assert types == [TokenType.LCURLY, TokenType.VAR, TokenType.RCURLY]

    def test_bar(self):
        toks = tokenize("[H|T]")
        types = [t.type for t in toks[:-1]]
        assert types == [
            TokenType.LBRACKET, TokenType.VAR, TokenType.BAR,
            TokenType.VAR, TokenType.RBRACKET,
        ]


class TestTokenizeDot:
    def test_clause_terminator(self):
        toks = tokenize("foo.")
        assert toks[-2] == Token(TokenType.DOT, ".", 1, 4)

    def test_dot_eof(self):
        toks = tokenize("a.")
        types = [t.type for t in toks]
        assert types == [TokenType.ATOM, TokenType.DOT, TokenType.END]

    def test_dot_whitespace(self):
        toks = tokenize("a. b.")
        types = [t.type for t in toks]
        assert types == [TokenType.ATOM, TokenType.DOT, TokenType.ATOM, TokenType.DOT, TokenType.END]

    def test_dot_in_float_not_terminator(self):
        toks = tokenize("3.14")
        assert toks[0].type == TokenType.FLOAT


class TestTokenizeComments:
    def test_line_comment(self):
        toks = tokenize("foo. % comment\nbar.")
        atoms = [t.value for t in toks if t.type == TokenType.ATOM]
        assert atoms == ["foo", "bar"]

    def test_block_comment(self):
        toks = tokenize("foo. /* block */ bar.")
        atoms = [t.value for t in toks if t.type == TokenType.ATOM]
        assert atoms == ["foo", "bar"]

    def test_nested_block_comment(self):
        toks = tokenize("foo. /* outer /* inner */ still comment */ bar.")
        atoms = [t.value for t in toks if t.type == TokenType.ATOM]
        assert atoms == ["foo", "bar"]


class TestTokenizeErrors:
    def test_unterminated_quoted_atom(self):
        with pytest.raises(TokenizeError, match="Unterminated quoted atom"):
            tokenize("'hello")

    def test_unterminated_string(self):
        with pytest.raises(TokenizeError, match="Unterminated string"):
            tokenize('"hello')


class TestTokenizeMultiple:
    def test_fact(self):
        toks = tokenize("edge(1, 2).")
        types = [t.type for t in toks]
        assert types == [
            TokenType.ATOM, TokenType.LPAREN, TokenType.INTEGER,
            TokenType.COMMA, TokenType.INTEGER, TokenType.RPAREN,
            TokenType.DOT, TokenType.END,
        ]

    def test_rule(self):
        toks = tokenize("reach(X, Y) :- edge(X, Y).")
        types = [t.type for t in toks]
        assert TokenType.ATOM in types
        assert TokenType.VAR in types
        assert types[-1] == TokenType.END

    def test_negative_number_in_expr(self):
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
        t = parse_term("foo")
        assert t == PAtom("foo")

    def test_variable(self):
        t = parse_term("X")
        assert t == PVar("X")

    def test_integer(self):
        t = parse_term("42")
        assert t == PNumber(42)

    def test_float(self):
        t = parse_term("3.14")
        assert t == PNumber(3.14)

    def test_string(self):
        t = parse_term('"hello"')
        assert t == PString("hello")

    def test_compound(self):
        t = parse_term("foo(bar, baz)")
        assert isinstance(t, PCompound)
        assert t.functor == "foo"
        assert t.args == (PAtom("bar"), PAtom("baz"))

    def test_nested_compound(self):
        t = parse_term("f(g(X), h(Y))")
        assert isinstance(t, PCompound)
        assert t.functor == "f"
        assert isinstance(t.args[0], PCompound) and t.args[0].functor == "g"
        assert isinstance(t.args[1], PCompound) and t.args[1].functor == "h"

    def test_empty_list(self):
        t = parse_term("[]")
        assert t == PList((), None)

    def test_proper_list(self):
        t = parse_term("[1, 2, 3]")
        assert isinstance(t, PList)
        assert t.elements == (PNumber(1), PNumber(2), PNumber(3))
        assert t.tail is None

    def test_partial_list(self):
        t = parse_term("[H|T]")
        assert isinstance(t, PList)
        assert t.elements == (PVar("H"),)
        assert t.tail == PVar("T")

    def test_multi_head_list(self):
        t = parse_term("[A, B|Rest]")
        assert isinstance(t, PList)
        assert t.elements == (PVar("A"), PVar("B"))
        assert t.tail == PVar("Rest")

    def test_curly(self):
        t = parse_term("{foo}")
        assert isinstance(t, PCurly)
        assert t.body == PAtom("foo")

    def test_empty_curly(self):
        t = parse_term("{}")
        assert t == PAtom("{}")

    def test_parenthesized(self):
        t = parse_term("(foo)")
        assert t == PAtom("foo")

    def test_negative_number(self):
        t = parse_term("-3")
        assert t == PNumber(-3)

    def test_quoted_atom(self):
        t = parse_term("'hello world'")
        assert t == PAtom("hello world")


class TestParseOperators:
    def test_infix_plus(self):
        t = parse_term("1 + 2")
        assert isinstance(t, PCompound)
        assert t.functor == "+"
        assert t.args == (PNumber(1), PNumber(2))

    def test_precedence(self):
        t = parse_term("1 + 2 * 3")
        # * binds tighter than +
        assert isinstance(t, PCompound) and t.functor == "+"
        assert isinstance(t.args[1], PCompound) and t.args[1].functor == "*"

    def test_left_assoc(self):
        t = parse_term("1 - 2 - 3")
        # - is yfx (left-associative)
        assert isinstance(t, PCompound) and t.functor == "-"
        assert isinstance(t.args[0], PCompound) and t.args[0].functor == "-"

    def test_right_assoc(self):
        t = parse_term("1 ; 2 ; 3")
        # ; is xfy (right-associative)
        assert isinstance(t, PCompound) and t.functor == ";"
        assert isinstance(t.args[1], PCompound) and t.args[1].functor == ";"

    def test_negation_prefix(self):
        t = parse_term("\\+ foo")
        assert isinstance(t, PCompound)
        assert t.functor == "\\+"
        assert t.args == (PAtom("foo"),)

    def test_unification(self):
        t = parse_term("X = foo")
        assert isinstance(t, PCompound)
        assert t.functor == "="
        assert t.args == (PVar("X"), PAtom("foo"))

    def test_is_expr(self):
        t = parse_term("Y is X + 1")
        assert isinstance(t, PCompound) and t.functor == "is"
        assert isinstance(t.args[1], PCompound) and t.args[1].functor == "+"

    def test_conjunction(self):
        t = parse_term("a, b, c")
        # , is xfy (right-assoc)
        assert isinstance(t, PCompound) and t.functor == ","
        assert t.args[0] == PAtom("a")
        # Right side is (b, c)
        rhs = t.args[1]
        assert isinstance(rhs, PCompound) and rhs.functor == ","

    def test_clause_arrow(self):
        t = parse_term("head :- body")
        assert isinstance(t, PCompound) and t.functor == ":-"
        assert t.args == (PAtom("head"), PAtom("body"))

    def test_comparison(self):
        t = parse_term("X > 0")
        assert isinstance(t, PCompound) and t.functor == ">"

    def test_mod_operator(self):
        t = parse_term("7 mod 2")
        assert isinstance(t, PCompound) and t.functor == "mod"

    def test_power(self):
        t = parse_term("2 ** 3")
        assert isinstance(t, PCompound) and t.functor == "**"


class TestParseProgram:
    def test_simple_fact(self):
        m = parse("edge(1, 2).")
        assert len(m.items) == 1
        item = m.items[0]
        assert isinstance(item, PClause)
        assert item.body is None
        assert isinstance(item.head, PCompound)
        assert item.head.functor == "edge"

    def test_simple_rule(self):
        m = parse("reach(X, Y) :- edge(X, Y).")
        assert len(m.items) == 1
        item = m.items[0]
        assert isinstance(item, PClause)
        assert item.body is not None

    def test_multiple_clauses(self):
        m = parse("edge(1, 2).\nedge(2, 3).")
        assert len(m.items) == 2

    def test_directive(self):
        m = parse(":- module(test, []).")
        assert len(m.items) == 1
        assert isinstance(m.items[0], PDirective)

    def test_dcg_rule(self):
        m = parse("greeting --> [hello, world].")
        assert len(m.items) == 1
        assert isinstance(m.items[0], PDCGRule)

    def test_atom_fact(self):
        m = parse("halt.")
        assert len(m.items) == 1
        assert isinstance(m.items[0], PClause)
        assert isinstance(m.items[0].head, PAtom)

    def test_multiline_rule(self):
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
        m = parse("check_diagonals([]).")
        assert len(m.items) == 1

    def test_list_pattern(self):
        m = parse("check_diagonals([Q|Rest]) :- safe_from(Q, Rest, 1).")
        assert len(m.items) == 1
        clause = m.items[0]
        assert isinstance(clause.head, PCompound)

    def test_query(self):
        m = parse("?- foo(X).")
        assert len(m.items) == 1
        assert isinstance(m.items[0], PQuery)

    def test_cut_in_body(self):
        m = parse("foo(X) :- bar(X), !.")
        clause = m.items[0]
        assert isinstance(clause, PClause)


class TestParseOpDirective:
    def test_op_directive_affects_parsing(self):
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
        src = "max(X, Y, Z) :- (X >= Y -> Z = X ; Z = Y)."
        m = parse(src)
        assert len(m.items) == 1

    def test_nested_negation(self):
        src = "test :- \\+ \\+ 1 = 1."
        m = parse(src)
        clause = m.items[0]
        assert isinstance(clause, PClause)


class TestParseEdgeCases:
    def test_zero_arity_compound(self):
        t = parse_term("foo()")
        assert isinstance(t, PCompound)
        assert t.functor == "foo"
        assert t.args == ()

    def test_operator_as_atom_in_compound(self):
        t = parse_term("op(700, xfx, <>)")
        assert isinstance(t, PCompound)
        assert t.functor == "op"

    def test_nested_list(self):
        t = parse_term("[[1, 2], [3, 4]]")
        assert isinstance(t, PList)
        assert len(t.elements) == 2

    def test_string_in_compound(self):
        t = parse_term('test("hello")')
        assert isinstance(t, PCompound)
        assert isinstance(t.args[0], PString)

    def test_predicate_indicator(self):
        t = parse_term("foo/2")
        assert isinstance(t, PCompound) and t.functor == "/"
        assert t.args == (PAtom("foo"), PNumber(2))
