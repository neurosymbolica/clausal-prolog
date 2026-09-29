"""write/1, writeq/1 and write_term/2 print what Scryer prints.

todo/done/writeq-disagrees-with-scryer-on-operators-and-quoting-2026-09-27.md.
The ISO writer family used ``term_str``'s functional notation: operator
terms as ``/(foo,1)``, every variable as ``_`` (``writeq(f(X, Y, X))``
printed ``f(_,_,_)``, losing the sharing), an unquoted functor that does not
re-read (``A b(1)``), ``'/*'`` unquoted, and Python float spelling.  The
expected strings below are Scryer Prolog's output for the same term
(/workspace/scryer-prolog, 2026-09-30), except that a variable's number is
the engine's own.
"""
import contextlib
import io
import re

import pytest

from clausal.logic.cells import chars
from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var


@pytest.fixture
def mod():
    return Module("iso_writers_scryer")


def _out(mod, goal):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        list(solve(goal, mod))
    return buf.getvalue()


def _t():
    A, B = Var(), Var()
    return ("f", A, B, A, "A b", chars("ab"), ["a", "b"], ("+", 1, 2), -1,
            ("-", 1), ("-", ("-", 1)), 1.0e22, "hello world", ("$VAR", 1),
            ("{}", "x"), (":", "a", "b"), (",", "a", "b"), [], "/*",
            ("-", "a"), ("\\+", "a"), ("-", 1, -1), ("=", "a", "b"),
            ("f", ";"), ";", ("f", (":-", "a", "b")))


def _vars_normalised(s):
    return re.sub(r"_\d+", "_V", s)


_TAIL = ("1+2,-1,- (1),- - (1),1.0e22,{hw},{var},{{x}},a:b,(a,b),[],{c},"
         "-a,\\+a,1- -1,a=b,f(;),;,f((a:-b)))")

SCRYER = {
    "write_term []": "f(_V,_V,_V,A b,[a,b],[a,b]," + _TAIL.format(
        hw="hello world", var="$VAR(1)", c="/*"),
    "write_term quoted": "f(_V,_V,_V,'A b',[a,b],[a,b]," + _TAIL.format(
        hw="'hello world'", var="'$VAR'(1)", c="'/*'"),
    "writeq": "f(_V,_V,_V,'A b',[a,b],[a,b]," + _TAIL.format(
        hw="'hello world'", var="B", c="'/*'"),
    "write": "f(_V,_V,_V,A b,[a,b],[a,b]," + _TAIL.format(
        hw="hello world", var="B", c="/*"),
    "write_term quoted double_quotes": 'f(_V,_V,_V,\'A b\',"ab","ab",'
        + _TAIL.format(hw="'hello world'", var="'$VAR'(1)", c="'/*'"),
    "write_term quoted ignore_ops": (
        "f(_V,_V,_V,'A b','.'(a,'.'(b,[])),'.'(a,'.'(b,[])),+(1,2),-1,-(1),"
        "-(-(1)),1.0e22,'hello world','$VAR'(1),{}(x),:(a,b),','(a,b),[],"
        "'/*',-(a),\\+(a),-(1,-1),=(a,b),f(;),;,f(:-(a,b)))"),
}

_GOALS = {
    "write_term []": lambda t: ("write_term", t, []),
    "write_term quoted": lambda t: ("write_term", t, [("quoted", "true")]),
    "writeq": lambda t: ("writeq", t),
    "write": lambda t: ("write", t),
    "write_term quoted double_quotes": lambda t: (
        "write_term", t, [("quoted", "true"), ("double_quotes", "true")]),
    "write_term quoted ignore_ops": lambda t: (
        "write_term", t, [("quoted", "true"), ("ignore_ops", "true")]),
}


@pytest.mark.parametrize("which", list(SCRYER))
def test_matches_scryer(mod, which):
    assert _vars_normalised(_out(mod, _GOALS[which](_t()))) == SCRYER[which]


def test_writeq_shows_variable_sharing(mod):
    X, Y = Var(), Var()
    out = _out(mod, ("writeq", ("f", X, Y, X)))
    a, b, c = re.fullmatch(r"f\((_\d+),(_\d+),(_\d+)\)", out).groups()
    assert a == c and a != b
