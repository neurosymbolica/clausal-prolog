"""Guarded postfix fallback + BAR-as-operator (toklex spec reading)."""
import pytest
from clausal.tools.prolog_parser import parse_term, ParseError
from clausal.tools.prolog_operators import OperatorTable
from clausal.tools.prolog_ast import PAtom, PCompound


def toklex_table():
    t = OperatorTable.iso_default()
    t.define(200, "xf", "*")
    t.define(200, "xf", "+")
    t.define(200, "xf", "?")
    t.define(600, "xfy", "then")
    t.define(700, "xfx", "but_not")
    t.define(700, "xfx", "followed_by")
    t.define(1100, "xfy", "|")
    return t


class TestPostfixFallback:
    def test_postfix_before_rparen(self):
        t = toklex_table()
        term = parse_term("f(a*)", op_table=t)
        assert term == PCompound("f", (PCompound("*", (PAtom("a"),)),))

    def test_postfix_before_infix_only_atom(self):
        # `graphic+ but_not x` — `but_not` is infix-only, so `+` is postfix
        t = toklex_table()
        term = parse_term("g+ but_not x", op_table=t)
        assert term == PCompound("but_not", (PCompound("+", (PAtom("g"),)), PAtom("x")))

    def test_infix_still_wins_when_term_follows(self):
        t = toklex_table()
        term = parse_term("a * b", op_table=t)
        assert term == PCompound("*", (PAtom("a"), PAtom("b")))

    def test_postfix_at_end_of_input(self):
        t = toklex_table()
        term = parse_term("a?", op_table=t)
        assert term == PCompound("?", (PAtom("a"),))

    def test_no_postfix_entry_unchanged_error(self):
        # default table: `a *` stays a parse error, proving no default-path change
        with pytest.raises(ParseError):
            parse_term("a *")

    def test_bare_infix_chain_not_misparsed_as_postfix(self):
        # Task 8 fix round (F041): `+` is declared BOTH infix (500 yfx, ISO
        # default) and postfix (200 xf, toklex's regex one-or-more) here.
        # A bare 3+-way chain `a + b + c` used to break: parsing the right
        # operand of the first `+` at a reduced max_prec (499, since yfx's
        # right side is precedence-1) excludes the 2nd `+`'s infix reading
        # (500 > 499) but not its postfix reading (200 <= 499), and the old
        # code guessed postfix -- silently misparsing `b +` and leaving `c`
        # dangling (`ParseError: Expected '.', got 'atom' ('c')`). The fix:
        # apply the same "next token can't start a term" guard to that
        # elif branch too, deferring the operator to the caller instead of
        # guessing wrong when a term (here, `c`) could still follow.
        t = toklex_table()
        a, b, c = PAtom("a"), PAtom("b"), PAtom("c")
        term = parse_term("a + b + c", op_table=t)
        assert term == PCompound("+", (PCompound("+", (a, b)), c))

        # And nested inside a functor's argument list (arg-priority-999
        # parsing, same reduced-max_prec mechanism), alongside another arg.
        d = PAtom("d")
        term2 = parse_term("f(a + b + c, d)", op_table=t)
        assert term2 == PCompound(
            "f", (PCompound("+", (PCompound("+", (a, b)), c)), d)
        )


class TestBarOperator:
    def test_bar_infix_in_parens(self):
        t = toklex_table()
        term = parse_term("a | b | c", op_table=t)
        assert term == PCompound("|", (PAtom("a"), PCompound("|", (PAtom("b"), PAtom("c")))))

    def test_bar_without_table_entry_unchanged(self):
        # ISO default has no infix '|' in our table: loop breaks unchanged, returning just the left term
        result = parse_term("a | b", op_table=OperatorTable.iso_default())
        assert result == PAtom("a")
