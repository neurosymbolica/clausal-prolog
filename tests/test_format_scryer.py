"""format/1,2: a port of Scryer's library(format).

It did not exist (existence_error(procedure, format/2)), so a .pl program
using it failed on import and ISO-style Clausal code had no text formatter
(todo/done/implement-iso-format-2-with-tilde-directives-2026-09-07.md).
Every expected string below is Scryer Prolog's output for the same call
(/workspace/scryer-prolog, 2026-09-30); a variable's number is the engine's.
"""
import contextlib
import io
import re

import pytest

from clausal.logic.builtins.io import format_to_text
from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Var

ROWS = [
    ("~s|", [chars("abc")], "abc|"),
    ("~d|", [42], "42|"),
    ("~2d|", [1234], "12.34|"),
    ("~0d|", [5], "5|"),
    ("~d|", [-1234], "-1234|"),
    ("~D|", [1234567], "1,234,567|"),
    ("~2D|", [1234567], "12,345.67|"),
    ("~3D|", [-1234567], "-1,234.567|"),
    ("~f|", [3.14159], "3.141590|"),
    ("~2f|", [2], "2.00|"),
    ("~f|", [1], "1.000000|"),
    ("~1f|", [0.05], "0.1|"),
    ("~1f|", [0.15], "0.2|"),
    ("a~nb~2nc", [], "a\nb\n\nc"),
    ("~~|", [], "~|"),
    ("~i~w|", ["a", "b"], "b|"),
    ("~8r ~16r ~8R|", [64, 255, 64], "100 ff 100|"),
    ("~r", [10], "12"),
    ("~2r", [5], "101"),
    ("~16R|", [255], "FF|"),
    ("~q|", [["a", "B"]], "[a,'B']|"),
    ("~a~t~20|~w|", ["abc", "x"], "abc                 x|"),
    ("~t~w~10||", ["right"], "     right|"),
    ("~t~d~6+|", [42], "    42|"),
    ("~w~30|~w~n", ["a", "b"], "ab\n"),
    ("~w~t~10+~w~t~10+|~n", ["abc", "def"], "abc       def       |\n"),
    ("~t~w~10|~n", ["abc"], "       abc\n"),
    ("~t~w~t~11|~n", ["mid"], "    mid    \n"),
    ("~`*t~t~20|~n", [], "**********          \n"),
    ("~5|abc~n", [], "abc\n"),
    ("~ic|", ["a"], "c|"),
    ("~t~2f~10|~w", [3.14159, "x"], "      3.14x"),
    ("~`-t~30|~n", [], "-" * 30 + "\n"),
    # Scryer's float_with_n_decimal_digits arithmetic (roborev, Medium):
    ("~2f|", [1.005], "1.00|"),
    ("~0f|", [2.5], "3.0|"),
    ("~2f|", [-1.5], "-1.50|"),
    ("~f|", [10 ** 30], "1000000000000000000000000000000.000000|"),
    ("~a|", [[]], "[]|"),
]


@pytest.mark.parametrize("fs,args,want", ROWS, ids=[r[0] for r in ROWS])
def test_matches_scryer(fs, args, want):
    assert format_to_text(chars(fs), args) == want


def test_w_q_a_and_variable_sharing():
    X = Var()
    out = format_to_text(chars("~w ~q ~a|"), [("f", "A b", X, X), "A b", "A b"])
    assert re.sub(r"_\d+", "_V", out) == "f(A b,_V,_V) 'A b' A b|"


ERRORS = [
    ("~c|", [97], ("domain_error", "format_string", ["~", "c", "|"])),
    ("~e|", [1.0], ("domain_error", "format_string", ["~", "e", "|"])),
    ("~w~w|", ["a"], ("domain_error", "non_empty_list", [])),
    ("~w|", ["a", "b"], ("domain_error", "empty_list", ["b"])),
    ("~d|", [1.0], ("type_error", "integer", 1.0)),
    ("~a|", [("f", "x")], ("type_error", "atom", ("f", "x"))),
    ("~w", "hello", ("type_error", "list", "hello")),
    ("~f|", [float("inf")], ("evaluation_error", "undefined")),
    ("~a|", [True], ("type_error", "atom", True)),
    ("~*c|", [3], ("domain_error", "format_string", ["~", "*", "c", "|"])),
]


@pytest.mark.parametrize("fs,args,formal", ERRORS, ids=[r[0] for r in ERRORS])
def test_errors_match_scryer(fs, args, formal):
    with pytest.raises(LogicException) as info:
        format_to_text(chars(fs), args)
    assert info.value.term[1] == formal


def test_format_2_prints_from_a_clausal_body(tmp_path):
    from clausal.import_hook import _load_module
    from clausal.logic.solve import solve
    p = tmp_path / "fmt_body.clausal"
    p.write_text('-private([abc])\n'
                 'go() <- format("~a: ~d items~n", [abc, 3])\n'
                 'go1() <- format("hello~n")\n')
    m = _load_module("fmt_body", str(p))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        list(solve("go", m))
        list(solve("go1", m))
    assert buf.getvalue() == "abc: 3 items\nhello\n"
