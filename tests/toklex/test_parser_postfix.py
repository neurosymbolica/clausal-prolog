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


class TestBarOperator:
    def test_bar_infix_in_parens(self):
        t = toklex_table()
        term = parse_term("a | b | c", op_table=t)
        assert term == PCompound("|", (PAtom("a"), PCompound("|", (PAtom("b"), PAtom("c")))))

    def test_bar_without_table_entry_unchanged(self):
        # ISO default has no infix '|' in our table: loop breaks unchanged, returning just the left term
        result = parse_term("a | b", op_table=OperatorTable.iso_default())
        assert result == PAtom("a")
