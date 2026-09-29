"""The ``.pl`` translator reads with Scryer's operator table by default
(ruling R11, 2026-09-28): ISO Table 7 plus Scryer's own defaults.  It used to
read with SWI's table."""
import pytest

from clausal.tools.prolog_dialect import Dialect
from clausal.tools.prolog_operators import OperatorTable
from clausal.tools.prolog_parser import ParseError
from clausal.tools.prolog_to_clausal import prolog_to_clausal

#: ``current_op/3`` in Scryer's toplevel with no library loaded (local
#: scryer-prolog, 2026-09-28), minus Scryer's internal
#: ``op(700, fx, non_counted_backtracking)``.
SCRYER_OPS = {
    (1000, "xfy", ","), (1050, "xfy", "->"), (1100, "xfy", ";"),
    (1200, "fx", ":-"), (1200, "fx", "?-"), (1200, "xfx", "-->"),
    (1200, "xfx", ":-"), (200, "fy", "+"), (200, "fy", "-"), (200, "fy", "\\"),
    (200, "xfx", "**"), (200, "xfy", "^"), (400, "yfx", "*"),
    (400, "yfx", "/"), (400, "yfx", "//"), (400, "yfx", "<<"),
    (400, "yfx", ">>"), (400, "yfx", "div"), (400, "yfx", "mod"),
    (400, "yfx", "rdiv"), (400, "yfx", "rem"), (500, "yfx", "+"),
    (500, "yfx", "-"), (500, "yfx", "/\\"), (500, "yfx", "\\/"),
    (600, "xfy", ":"), (700, "xfx", "<"), (700, "xfx", "="),
    (700, "xfx", "=.."), (700, "xfx", "=:="), (700, "xfx", "=<"),
    (700, "xfx", "=="), (700, "xfx", "=\\="), (700, "xfx", ">"),
    (700, "xfx", ">="), (700, "xfx", "@<"), (700, "xfx", "@=<"),
    (700, "xfx", "@>"), (700, "xfx", "@>="), (700, "xfx", "\\="),
    (700, "xfx", "\\=="), (700, "xfx", "is"), (900, "fy", "\\+"),
}


def _ops(table: OperatorTable) -> set:
    return {(e.precedence, e.specifier, e.name)
            for entries in table._ops.values() for e in entries}


def test_the_default_reader_table_is_scryers():
    assert _ops(Dialect.scryer_reader().operator_table) == SCRYER_OPS


@pytest.mark.parametrize("src, expect", [
    ("p(X) :- X is 7 div 2.\n", "'div'(7, 2)"),
    ("p(X) :- X = +(1).\n", "X is +1"),
    (":- dynamic(foo/1).\n", "-dynamic(foo/1)"),
])
def test_scryer_spellings_translate(src, expect):
    assert expect in prolog_to_clausal(src)


@pytest.mark.parametrize("src", [
    ":- dynamic foo/1.\n",            # SWI's 1150 fx prefix directive ops
    "p :- (a *-> b ; c).\n",          # SWI's soft-cut operator
    "p(X) :- X is 3 xor 1.\n",        # SWI's infix xor
])
def test_swi_only_operators_are_syntax_errors_as_in_scryer(src):
    with pytest.raises(ParseError):
        prolog_to_clausal(src)


def test_the_swi_dialect_is_still_available_explicitly():
    out = prolog_to_clausal(":- dynamic foo/1.\n", dialect=Dialect.swi())
    assert "-dynamic(foo/1)" in out
